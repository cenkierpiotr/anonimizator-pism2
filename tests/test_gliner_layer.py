"""Testy warstwy GLiNER (`app/pipeline/gliner_layer.py`).

Pakiet `gliner` NIE jest zainstalowany w środowisku testowym (opcjonalna
zależność, patrz requirements.txt) - te testy sprawdzają wyłącznie kontrakt
niezależny od realnego modelu: obsługę brakującego pliku/pakietu przez
`GlinerUnavailableError`, oraz konwersję predykcji na `GlinerCandidate` przy
użyciu prostego fake modelu (bez importu `gliner`)."""

import builtins
import hashlib
import zipfile

import pytest

from app.config import GlinerConfig
from app.pipeline import gliner_layer
from app.pipeline.gliner_layer import (
    GlinerCandidate,
    GlinerChecksumError,
    GlinerUnavailableError,
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


def test_download_gliner_model_requires_checksum_configured(tmp_path):
    config = GlinerConfig(model_path=str(tmp_path / "model_quantized.onnx"), release_sha256="")

    with pytest.raises(GlinerChecksumError):
        download_gliner_model(config=config)


def test_download_gliner_model_rejects_wrong_checksum(tmp_path, monkeypatch):
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
        download_gliner_model(config=config)


def test_download_gliner_model_accepts_correct_checksum_and_extracts(tmp_path, monkeypatch):
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
    result = download_gliner_model(config=config)

    assert result == target_dir / "model_quantized.onnx"
    assert result.exists()
    assert result.read_text() == "fake gliner model"
    assert (target_dir / "gliner_config.json").exists()


def test_download_gliner_model_reports_progress(tmp_path, monkeypatch):
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
    download_gliner_model(
        config=config,
        progress_callback=lambda done, total: progress_calls.append((done, total)),
    )

    assert progress_calls == [(len(archive_bytes), len(archive_bytes))]
