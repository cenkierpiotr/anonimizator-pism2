"""Testy warstwy GLiNER (`app/pipeline/gliner_layer.py`).

Pakiet `gliner` NIE jest zainstalowany w środowisku testowym (opcjonalna
zależność, patrz requirements.txt) - te testy sprawdzają wyłącznie kontrakt
niezależny od realnego modelu: obsługę brakującego pliku/pakietu przez
`GlinerUnavailableError`, oraz konwersję predykcji na `GlinerCandidate` przy
użyciu prostego fake modelu (bez importu `gliner`)."""

import builtins
import hashlib
import io
import json
import urllib.error
import zipfile

import pytest

from app.config import GlinerConfig
from app.pipeline import gliner_layer
from app.pipeline.gliner_layer import (
    GlinerCandidate,
    GlinerChecksumError,
    GlinerUnavailableError,
    _download_gliner_model_zip,
    download_gliner_model,
    find_gliner_candidates,
)


def test_load_model_missing_file_raises_clear_error(tmp_path):
    missing_path = tmp_path / "nie_istnieje" / "model.onnx"

    with pytest.raises(GlinerUnavailableError, match="nie istnieje"):
        gliner_layer.load_model(str(missing_path))


def test_load_model_missing_package_raises_clear_error(tmp_path, monkeypatch):
    """Gdy plik modelu istnieje, ale pakiet `gliner` nie jest zainstalowany -
    czytelny błąd, nie goły ModuleNotFoundError.

    Symulujemy brak pakietu przez monkeypatch `builtins.__import__` (zamiast
    liczyć na to, że `gliner` faktycznie nie jest zainstalowany w środowisku,
    w którym testy są odpalane) - test musi dawać ten sam wynik niezależnie
    od tego, czy `gliner` jest czy nie jest zainstalowany lokalnie."""
    model_file = tmp_path / "model_quantized.onnx"
    model_file.write_bytes(b"nie prawdziwy model, tylko test pliku")
    gliner_layer.load_model.cache_clear()

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "gliner":
            raise ImportError("No module named 'gliner'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    with pytest.raises(GlinerUnavailableError, match="nie jest zainstalowany"):
        gliner_layer.load_model(str(model_file))


class _FakeGlinerModel:
    """Symuluje interfejs `GLiNER.predict_entities` bez importu prawdziwego
    pakietu - wystarczające do przetestowania konwersji wyników przez
    `find_gliner_candidates`, niezależnie od tego, czy `gliner` jest
    zainstalowany w środowisku, w którym odpalane są testy."""

    def __init__(self, predictions):
        self._predictions = predictions

    def predict_entities(self, text, labels, threshold=0.5):
        return self._predictions


def test_find_gliner_candidates_converts_predictions():
    text = "Umowę zawarto pomiędzy Janem Kowalskim a Fundacją Alfa."
    start = text.index("Janem Kowalskim")
    end = start + len("Janem Kowalskim")
    model = _FakeGlinerModel(
        [{"start": start, "end": end, "text": "Janem Kowalskim", "label": "legal_role_person", "score": 0.87}]
    )

    candidates = find_gliner_candidates(text, model)

    assert candidates == [
        GlinerCandidate(start=start, end=end, text="Janem Kowalskim", label="legal_role_person", score=0.87)
    ]


def test_find_gliner_candidates_empty_text_returns_empty_list():
    model = _FakeGlinerModel([{"start": 0, "end": 1, "text": "x", "label": "y", "score": 1.0}])

    assert find_gliner_candidates("   ", model) == []


def test_find_gliner_candidates_wraps_prediction_errors():
    class _BrokenModel:
        def predict_entities(self, text, labels, threshold=0.5):
            raise RuntimeError("silnik ONNX się wywalił")

    with pytest.raises(GlinerUnavailableError, match="Błąd predykcji"):
        find_gliner_candidates("jakiś tekst", _BrokenModel())


# -- download_gliner_model (mechanizm "na żądanie", wzorem download_libreoffice) --
#
# Nowa logika (od przebudowy na Hugging Face jako PRIMARY): testy monkeypatchują
# `urllib.request.urlopen` (manifest + pobrania plików) i `time.sleep` (retry
# backoff - bez czekania w testach), wzorzec analogiczny do monkeypatch
# `urlretrieve` w testach starej ścieżki ZIP poniżej. Testy MUSZĄ być w pełni
# offline - żaden nie dotyka realnego Hugging Face/GitHubu.


class _FakeHfResponse:
    """Symuluje response `urllib.request.urlopen` - kontekst-menadżer,
    `.read(n)`, `.headers.get('Content-Length')`. Trzyma treść w pamięci,
    więc testy są szybkie i offline."""

    def __init__(self, content: bytes, content_length: int | None = None):
        self._stream = io.BytesIO(content)
        # None = symulacja chunked (brak Content-Length) - total z manifestu.
        self.headers = {"Content-Length": str(content_length)} if content_length is not None else {}

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size if size > 0 else -1)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _hf_config(model_path, hf_required_files=("plik.bin",), hf_repo_id="test/repo"):
    """GlinerConfig z minimalnym jedno-plikowym repo HF do testów logiki
    pobierania (bez zbędnego hałasu z realną listą 4 plików)."""
    return GlinerConfig(
        model_path=str(model_path),
        hf_repo_id=hf_repo_id,
        hf_required_files=hf_required_files,
        # Pusty fallback - testy logiki HF NIE muszą go dotykać.
        release_url="",
        release_sha256="",
    )


def _patch_sleep(monkeypatch):
    """Zamockowany time.sleep (retry backoff HF) - testy nie czekają
    realnie 1s/2s/4s; zwraca listę zapisanych opóźnień do asercji."""
    sleeps: list[float] = []
    monkeypatch.setattr(gliner_layer.time, "sleep", lambda s: sleeps.append(s))
    return sleeps


def test_download_gliner_model_hf_all_files_present_skips_network(tmp_path, monkeypatch):
    """(a) Wszystkie pliki już istnieją lokalnie z zgodnym rozmiarem -
    żadne zapytanie sieciowe nie jest wykonane (monkeypatch urlopen rzuca,
    gdyby zostało wywołane)."""
    def _fail_urlopen(*args, **kwargs):
        raise AssertionError("urlopen nie powinien być wywołany - pliki istnieją")

    monkeypatch.setattr(gliner_layer.urllib.request, "urlopen", _fail_urlopen)

    target_dir = tmp_path / "gliner"
    target_dir.mkdir()
    (target_dir / "plik.bin").write_bytes(b"x" * 100)

    config = _hf_config(target_dir / "plik.bin")
    result = download_gliner_model(config=config)

    assert result == target_dir / "plik.bin"
    assert result.exists()


def test_download_gliner_model_hf_downloads_and_verifies_sha256(tmp_path, monkeypatch):
    """(b) Pobranie z weryfikacją SHA-256 OK - plik LFS z lfs.oid w manifeście
    pobierany do *.part i atomowo rename'owany PO weryfikacji."""
    content = b"zawartosc pliku binarnego modelu"
    sha = hashlib.sha256(content).hexdigest()

    urls_called = []

    def fake_urlopen(url, timeout=None):
        urls_called.append(url)
        if url.endswith("/tree/main"):
            manifest = [{"type": "file", "path": "plik.bin", "size": len(content), "lfs": {"oid": sha, "size": len(content)}}]
            raw = json.dumps(manifest).encode()
            return _FakeHfResponse(raw, len(raw))
        if url.endswith("/plik.bin"):
            return _FakeHfResponse(content, len(content))
        raise AssertionError(f"nieoczekiwany URL: {url}")

    monkeypatch.setattr(gliner_layer.urllib.request, "urlopen", fake_urlopen)

    target_dir = tmp_path / "gliner"
    config = _hf_config(target_dir / "plik.bin")
    progress_calls: list[tuple[int, int]] = []
    result = download_gliner_model(
        config=config,
        progress_callback=lambda done, total: progress_calls.append((done, total)),
    )

    assert result == target_dir / "plik.bin"
    assert result.read_bytes() == content
    # Po udanym rename'ie plik .part nie zostaje.
    assert not (target_dir / "plik.bin.part").exists()
    # Progres narastająco zakończony na (total, total).
    assert progress_calls[-1] == (len(content), len(content))
    # Manifest raz + plik raz = 2 zapytania.
    assert len(urls_called) == 2
    assert urls_called[0].endswith("api/models/test/repo/tree/main")
    assert urls_called[1].endswith("test/repo/resolve/main/plik.bin")


def test_download_gliner_model_hf_sha256_mismatch_raises_and_removes_part(tmp_path, monkeypatch):
    """(c) SHA-256 mismatch - GlinerChecksumError, plik .part usunięty
    (uszkodzony plik NIE zostaje na dysku)."""
    content = b"przypadkowa zawartosc"
    zla_suma = "0" * 64

    def fake_urlopen(url, timeout=None):
        if url.endswith("/tree/main"):
            manifest = [{"type": "file", "path": "plik.bin", "size": len(content), "lfs": {"oid": zla_suma, "size": len(content)}}]
            raw = json.dumps(manifest).encode()
            return _FakeHfResponse(raw, len(raw))
        return _FakeHfResponse(content, len(content))

    monkeypatch.setattr(gliner_layer.urllib.request, "urlopen", fake_urlopen)

    target_dir = tmp_path / "gliner"
    config = _hf_config(target_dir / "plik.bin")
    with pytest.raises(GlinerChecksumError, match="nie zgadza się"):
        download_gliner_model(config=config)

    assert not (target_dir / "plik.bin.part").exists()
    assert not (target_dir / "plik.bin").exists()


def test_download_gliner_model_hf_size_mismatch_raises(tmp_path, monkeypatch):
    """(c2) Rozmiar pobranego pliku != rozmiaru z manifestu (transfer
    ucięty) - GlinerChecksumError, .part usunięty. Weryfikacja rozmiaru
    działa też dla plików nie-LFS (bez sha256 w API)."""
    content = b"za krotka zawartosc"

    def fake_urlopen(url, timeout=None):
        if url.endswith("/tree/main"):
            manifest = [
                {"type": "file", "path": "plik.bin", "size": 999999}
            ]  # brak lfs -> weryfikacja tylko rozmiarem
            raw = json.dumps(manifest).encode()
            return _FakeHfResponse(raw, len(raw))
        # Content-Length zgodny z realną treścią, ale manifest obiecuje więcej.
        return _FakeHfResponse(content, len(content))

    monkeypatch.setattr(gliner_layer.urllib.request, "urlopen", fake_urlopen)

    config = _hf_config(tmp_path / "gliner" / "plik.bin")
    with pytest.raises(GlinerChecksumError, match="rozmiar"):
        download_gliner_model(config=config)

    assert not (tmp_path / "gliner" / "plik.bin.part").exists()


def test_download_gliner_model_hf_retries_on_429_then_succeeds(tmp_path, monkeypatch):
    """(d) Retry na 429 (rate limit) - pierwsze zapytanie o manifest
    dostaje 429, po backoff (zamockowany time.sleep) drugie się udaje."""
    content = b"model"
    sha = hashlib.sha256(content).hexdigest()

    manifest_raw = json.dumps(
        [{"type": "file", "path": "plik.bin", "size": len(content), "lfs": {"oid": sha, "size": len(content)}}]
    ).encode()

    manifest_attempts = {"n": 0}

    def fake_urlopen(url, timeout=None):
        if url.endswith("/tree/main"):
            manifest_attempts["n"] += 1
            if manifest_attempts["n"] == 1:
                raise urllib.error.HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=None)
            return _FakeHfResponse(manifest_raw, len(manifest_raw))
        return _FakeHfResponse(content, len(content))

    monkeypatch.setattr(gliner_layer.urllib.request, "urlopen", fake_urlopen)
    sleeps = _patch_sleep(monkeypatch)

    config = _hf_config(tmp_path / "gliner" / "plik.bin")
    result = download_gliner_model(config=config)

    assert result.read_bytes() == content
    assert manifest_attempts["n"] == 2
    # Backoff po pierwszej (udanej retry-kompetycznej) próbie: 1s.
    assert sleeps == [1.0]


def test_download_gliner_model_hf_retry_exhausted_raises_unavailable(tmp_path, monkeypatch):
    """(d2) Retry wyczerpany (timeout przy każdej próbie) - czytelny
    GlinerUnavailableError, NIE goły socket.timeout; fallback nie
    skonfigurowany (pusty release_url), więc błąd HF jest kontekstem."""
    import socket

    def fake_urlopen(url, timeout=None):
        raise urllib.error.URLError(socket.timeout("timed out"))

    monkeypatch.setattr(gliner_layer.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(gliner_layer, "_HF_RETRY_DELAYS_S", (0.0, 0.0, 0.0))
    # time.sleep patch tak, żeby retry pętla nie czekała realnie.
    monkeypatch.setattr(gliner_layer.time, "sleep", lambda s: None)

    config = _hf_config(tmp_path / "gliner" / "plik.bin")
    with pytest.raises(GlinerUnavailableError, match="Hugging Face"):
        download_gliner_model(config=config)


def test_download_gliner_model_hf_missing_required_file_in_manifest(tmp_path, monkeypatch):
    """Manifest nie zawiera wymaganego pliku (zły repo/zmieniona struktura)
    - czytelny GlinerUnavailableError zamiast późniejszego cichego braku."""
    manifest_raw = json.dumps([{"type": "file", "path": "inny-plik.onnx", "size": 5}]).encode()

    def fake_urlopen(url, timeout=None):
        return _FakeHfResponse(manifest_raw, len(manifest_raw))

    monkeypatch.setattr(gliner_layer.urllib.request, "urlopen", fake_urlopen)

    config = _hf_config(tmp_path / "gliner" / "plik.bin")
    with pytest.raises(GlinerUnavailableError, match="nie zawiera wymaganych plików"):
        download_gliner_model(config=config)


def test_download_gliner_model_falls_back_to_zip_when_hf_down(tmp_path, monkeypatch):
    """(e) Hugging Face pada (po retry), fallback na stary ZIP działa -
    archiwum pobrane urlretrieve, zweryfikowane, rozpakowane."""
    def fail_urlopen(url, timeout=None):
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", hdrs=None, fp=None)

    monkeypatch.setattr(gliner_layer.urllib.request, "urlopen", fail_urlopen)
    monkeypatch.setattr(gliner_layer.time, "sleep", lambda s: None)

    source_zip = tmp_path / "source.zip"
    with zipfile.ZipFile(source_zip, "w") as zf:
        zf.writestr("model_quantized.onnx", "fake gliner model")
    archive_bytes = source_zip.read_bytes()
    expected_sha256 = hashlib.sha256(archive_bytes).hexdigest()

    def fake_urlretrieve(url, filename, reporthook=None):
        with open(filename, "wb") as f:
            f.write(archive_bytes)
        if reporthook:
            reporthook(1, len(archive_bytes), len(archive_bytes))

    monkeypatch.setattr(gliner_layer.urllib.request, "urlretrieve", fake_urlretrieve)

    target_dir = tmp_path / "gliner"
    config = GlinerConfig(
        model_path=str(target_dir / "model_quantized.onnx"),
        hf_repo_id="test/padajacy-repo",
        release_url="https://example.invalid/gliner-model.zip",
        release_sha256=expected_sha256,
    )
    result = download_gliner_model(config=config)

    assert result == target_dir / "model_quantized.onnx"
    assert result.read_text() == "fake gliner model"


def test_download_gliner_model_both_sources_down_raises_with_context(tmp_path, monkeypatch):
    """(e2) HF pada i fallback ZIP też pada (zła checksum archiwum) -
    łączony komunikat z kontekstem obu źródeł, oryginalne wyjątki jako
    przyczyny."""
    def fail_urlopen(url, timeout=None):
        raise urllib.error.URLError("brak sieci")

    monkeypatch.setattr(gliner_layer.urllib.request, "urlopen", fail_urlopen)
    monkeypatch.setattr(gliner_layer.time, "sleep", lambda s: None)

    def fake_urlretrieve(url, filename, reporthook=None):
        with open(filename, "wb") as f:
            f.write(b"zepsute archiwum")

    monkeypatch.setattr(gliner_layer.urllib.request, "urlretrieve", fake_urlretrieve)

    config = GlinerConfig(
        model_path=str(tmp_path / "model_quantized.onnx"),
        release_url="https://example.invalid/gliner-model.zip",
        release_sha256="0" * 64,
    )
    with pytest.raises(GlinerUnavailableError, match="Fallback"):
        download_gliner_model(config=config)


def test_download_gliner_model_hf_empty_zip_placeholder_is_not_required(tmp_path, monkeypatch):
    """Stary kontrakt "pusty release_sha256 => GlinerChecksumError na wejściu"
    NIE dotyczy już wejścia do download_gliner_model (PRIMARY to HF, fallback
    ZIP jest opcjonalny): pusty placeholder NIE powoduje odrzucenia zanim
    w ogóle spróbujemy Hugging Face. Pełny happy-path HF z manifestem patrz
    test (b) - tu weryfikujemy tylko, że ścieżka HF rusza mimo pustego
    fallbacku (wywołuje urlopen po manifest, a nie pada na checksum)."""
    def fake_urlopen(url, timeout=None):
        raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setattr(gliner_layer.urllib.request, "urlopen", fake_urlopen)

    config = GlinerConfig(
        model_path=str(tmp_path / "gliner" / "model_quantized.onnx"),
        release_url="",
        release_sha256="",
    )
    # HTTPError 404 z manifestu = trwały błąd HF, fallback nie skonfigurowany.
    # DOWÓD, że przeszliśmy przez stare wczesne raise na pustym sha256:
    # wyjątek mówi o repozytorium HF, a nie o braku skonfigurowanego SHA-256.
    with pytest.raises(GlinerUnavailableError, match="nie jest dostępne"):
        download_gliner_model(config=config)


# -- stara ścieżka ZIP (fallback, `_download_gliner_model_zip`) --


def test_download_gliner_model_zip_requires_checksum_configured(tmp_path):
    config = GlinerConfig(model_path=str(tmp_path / "model_quantized.onnx"), release_sha256="")

    with pytest.raises(GlinerChecksumError):
        _download_gliner_model_zip(config=config, progress_callback=None)


def test_download_gliner_model_zip_rejects_wrong_checksum(tmp_path, monkeypatch):
    fake_archive_content = b"nie prawdziwe archiwum modelu"

    def fake_urlretrieve(url, filename, reporthook=None):
        with open(filename, "wb") as f:
            f.write(fake_archive_content)
        if reporthook:
            reporthook(1, len(fake_archive_content), len(fake_archive_content))

    monkeypatch.setattr(gliner_layer.urllib.request, "urlretrieve", fake_urlretrieve)

    config = GlinerConfig(
        model_path=str(tmp_path / "model_quantized.onnx"),
        release_url="https://example.invalid/gliner-model.zip",
        release_sha256="0" * 64,
    )
    with pytest.raises(GlinerChecksumError):
        _download_gliner_model_zip(config=config, progress_callback=None)


def test_download_gliner_model_zip_accepts_correct_checksum_and_extracts(tmp_path, monkeypatch):
    source_zip = tmp_path / "source.zip"
    with zipfile.ZipFile(source_zip, "w") as zf:
        zf.writestr("model_quantized.onnx", "fake gliner model")
        zf.writestr("gliner_config.json", "{}")
    archive_bytes = source_zip.read_bytes()
    expected_sha256 = hashlib.sha256(archive_bytes).hexdigest()

    def fake_urlretrieve(url, filename, reporthook=None):
        with open(filename, "wb") as f:
            f.write(archive_bytes)
        if reporthook:
            reporthook(1, len(archive_bytes), len(archive_bytes))

    monkeypatch.setattr(gliner_layer.urllib.request, "urlretrieve", fake_urlretrieve)

    target_dir = tmp_path / "gliner"
    config = GlinerConfig(
        model_path=str(target_dir / "model_quantized.onnx"),
        release_url="https://example.invalid/gliner-model.zip",
        release_sha256=expected_sha256,
    )
    result = _download_gliner_model_zip(config=config, progress_callback=None)

    assert result == target_dir / "model_quantized.onnx"
    assert result.exists()
    assert result.read_text() == "fake gliner model"
    assert (target_dir / "gliner_config.json").exists()


def test_download_gliner_model_zip_reports_progress(tmp_path, monkeypatch):
    source_zip = tmp_path / "source.zip"
    with zipfile.ZipFile(source_zip, "w") as zf:
        zf.writestr("model_quantized.onnx", "fake gliner model")
    archive_bytes = source_zip.read_bytes()
    expected_sha256 = hashlib.sha256(archive_bytes).hexdigest()

    def fake_urlretrieve(url, filename, reporthook=None):
        with open(filename, "wb") as f:
            f.write(archive_bytes)
        if reporthook:
            reporthook(1, len(archive_bytes), len(archive_bytes))

    monkeypatch.setattr(gliner_layer.urllib.request, "urlretrieve", fake_urlretrieve)

    progress_calls: list[tuple[int, int]] = []
    config = GlinerConfig(
        model_path=str(tmp_path / "out" / "model_quantized.onnx"),
        release_url="https://example.invalid/gliner-model.zip",
        release_sha256=expected_sha256,
    )
    _download_gliner_model_zip(
        config=config,
        progress_callback=lambda done, total: progress_calls.append((done, total)),
    )

    assert progress_calls == [(len(archive_bytes), len(archive_bytes))]
