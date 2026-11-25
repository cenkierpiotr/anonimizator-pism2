"""Warstwa GLiNER (zero-shot NER) - DODATKOWA warstwa recall, NIE zamiennik
regex+checksum. Patrz też architektura ogólna w `docs/PLAN.md`.

Zasada bezpieczeństwa (nienaruszalna): trafienia GLiNER NIGDY nie trafiają
bezpośrednio do `merge.resolve()`/`detect_all.Replacement`. Błąd modelu
neuronowego bez ludzkiej weryfikacji per-span trafiłby wprost do finalnego
dokumentu - nieakceptowalne ryzyko wycieku danych klienta kancelarii.
`detect_all.detect_in_text` dopisuje trafienia GLiNER WYŁĄCZNIE do
`uncertain_collector` (ten sam mechanizm co niepewne trafienia po korekcie
OCR), z prefiksem "[GLiNER]", i tylko te, które nie pokrywają się z żadną już
zaakceptowaną (regex+checksum/NER) detekcją - te zawsze wygrywają.

Model jest lazy-loaded RAZ per proces (wzorem `app/pipeline/ner.py::load_nlp`,
`lru_cache`) - wywołujący (`app/main.py`) woła `load_model()` raz na start
przetwarzania dokumentu, nie w pętli per-blok.

Cała warstwa jest za feature flagiem `AppConfig.gliner_enabled` (domyślnie
WŁĄCZONA od Fazy 5). Pakiet `gliner` NIE jest obowiązkową zależnością
aplikacji w tym sensie, że import jest wykonywany leniwie wewnątrz
`load_model()`, żeby ten moduł (i reszta aplikacji) dał się zaimportować bez
tego pakietu zainstalowanego.

Plik modelu ONNX (`GlinerConfig.model_path`, binarka ~150-300MB) JEST teraz
częścią instalatora domyślnie: pobierany authenticated (`gh release
download`) w CI i zvendorowany build-time do `build/vendor/gliner_model/`
(patrz `build/anonimizator.spec` i `.github/workflows/build-windows.yml`)
- w zbudowanej aplikacji `app/config.py::_default_gliner_model_path()`
wskazuje na ten zvendorowany katalog obok głównego .exe (`sys.frozen`).
Powód zmiany z runtime download-on-demand: repo jest prywatne, więc
anonimowy `urllib`/`curl` na `browser_download_url` Release'u zwraca 404 -
`download_gliner_model()` poniżej NIE działał dla realnego użytkownika
końcowego bez tokenu GitHub.

`download_gliner_model()` pobiera model "na żądanie" (GUI: przycisk
"Pobierz model GLiNER", dev na Linuksie gdzie `sys.frozen` nie jest
ustawione, oraz CI-fallback w publicznym forku repo) z DWÓCH źródeł:

- PRIMARY: publiczne repo Hugging Face (`GlinerConfig.hf_repo_id`)
  - pliki pobierane PER-PLIK (tylko brakujące), każdy weryfikowany
  (SHA-256 z API tree dla plików LFS, rozmiar dla pozostałych), pobierane
  do `*.part` i atomowo rename'owane po weryfikacji;
- FALLBACK (`_download_gliner_model_zip()`): archiwum ZIP z GitHub
  Releases tego samego repo, weryfikacja SHA-256, rozpakowanie do
  katalogu docelowego - analogicznie do mechanizmu LibreOffice
  (`legacy_convert.download_libreoffice()`). Działa w prywatnym repo
  (authenticated), używane gdy Hugging Face zawiedzie po retry, np. do
  podmiany na wariant `anonPL-494M`. Wymaga niepustych
  `GlinerConfig.release_url` + `release_sha256`.

Świeża instalacja bez modelu (zbundlowanego ani pobranego fallbackiem)
nie crashuje - `load_model()` zgłasza czytelny `GlinerUnavailableError`,
złapany w `app/main.py` jako ostrzeżenie."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

from app.config import GlinerConfig

ProgressCallback = Callable[[int, int], None]  # (bytes_pobrane, bytes_razem)

# Retry na pojedyncze zapytanie HTTP do Hugging Face: 3 próby (początkowa
# + 2 powtórzenia), wykładniczy backoff 1s/2s/4s między próbami. Dotyczy
# TYMCZASOWYCH błędów (timeout/429/5xx/ConnectionError) - trwałe błędy
# (404 na pliku w API tree,checksum mismatch) NIE są retryowane, bo
# powtórzenie da ten sam wynik.
_HF_RETRY_ATTEMPTS = 3
_HF_RETRY_DELAYS_S = (1.0, 2.0, 4.0)
_HF_REQUEST_TIMEOUT_S = 30
_HF_CHUNK_SIZE = 1024 * 1024


class GlinerUnavailableError(RuntimeError):
    """Zgłaszany gdy `gliner_enabled=True`, ale pakiet `gliner` nie jest
    zainstalowany, plik modelu ONNX nie istnieje pod skonfigurowaną ścieżką,
    albo wczytanie/predykcja modelu zawiodło z innego powodu. Wywołujący
    (`app/main.py`) MUSI to złapać i potraktować jako ostrzeżenie dla
    użytkownika (dopisane do `warnings`), NIE jako fatalny błąd całego
    przetwarzania - GLiNER jest opcjonalną warstwą recall, nie fundamentem
    pipeline'u."""


class GlinerChecksumError(RuntimeError):
    """Pobrany plik/archiwum modelu GLiNER nie zgadza się z oczekiwaną
    sumą kontrolną (SHA-256 dla plików LFS z Hugging Face / archiwum ZIP
    z Releases) albo z oczekiwanym rozmiarem - odrzucone, nie używamy
    niezweryfikowanego pliku binarnego (patrz `legacy_convert.
    LibreOfficeChecksumError` - identyczny wzorzec). Zgłaszany też, gdy
    weryfikacja jest niemożliwa: `GlinerConfig.release_sha256` to pusty
    placeholder (release nie został opublikowany), a jednocześnie HF
    nie dostarczył sumy kontrolnej w API tree."""


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hf_is_transient_error(exc: Exception) -> bool:
    """Czy błąd HTTP/retu Hugging Face jest tymczasowy (warto ponowić
    próbę)? Tak dla timeoutów, 429 (rate limit) i 5xx (CDN/serwer);
    NIE dla 401/403/404 (trwały - brak pliku/repo, powtórka nic nie da)."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or 500 <= exc.code < 600
    if isinstance(exc, urllib.error.URLError):
        # URLError bez kodu HTTP = timeout/DNS/connection reset zagnieżdżone
        # w `reason` - traktowane jako tymczasowe (retry może trafić w inny
        # węzeł CDN). Kody HTTP przechodzą przez HTTPError wyżej.
        return True
    return isinstance(exc, (ConnectionError, TimeoutError, OSError))


def _hf_open_with_retry(url: str) -> object:
    """Otwiera URL (manifest API albo plik) z retry x3 (1s/2s/4s) na
    timeout/429/5xx/ConnectionError. Zwraca obiekt response zgodny z
    `urllib.request.urlopen` (kontekst-menadżer + `.read()`).

    Trwałe błędy (404 itp.) są rzucane natychmiast - bez sensownego celu
    retry. Rzucony po ostatniej próbie wyjątek zawiera w `__notes__`
    kontekst wszystkich prób, żeby komunikat dla użytkownika był czytelny."""
    last_exc: Exception | None = None
    for attempt in range(_HF_RETRY_ATTEMPTS):
        if attempt > 0:
            time.sleep(_HF_RETRY_DELAYS_S[min(attempt - 1, len(_HF_RETRY_DELAYS_S) - 1)])
        try:
            return urllib.request.urlopen(url, timeout=_HF_REQUEST_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 - klasyfikacja niżej
            if not _hf_is_transient_error(exc):
                raise
            last_exc = exc
    assert last_exc is not None  # pętla wykonała się min. raz
    raise last_exc


def _hf_fetch_manifest(repo_id: str) -> dict[str, dict]:
    """Pobiera manifest (listę plików) z API tree Hugging Face
    (`https://huggingface.co/api/models/<repo_id>/tree/main`) - RAZ na
    wywołanie `download_gliner_model()`, wszystkie pliki weryfikujemy
    przeciwko temu samemu manifestowi.

    Zwraca słownik `ścieżka_pliku -> wpis manifestu` z polami `size`
    (wszystkie pliki) i `lfs.oid` = SHA-256 (tylko pliki LFS - binaria;
    pliki nie-LFS, np. JSON-y, nie mają sumy kontrolnej w API, więc są
    weryfikowane wyłącznie rozmiarem).

    Rzuca `GlinerUnavailableError` z czytelnym komunikatem, gdy repo nie
    istnieje (404) albo manifest nie da się pobrać po retry."""
    url = f"https://huggingface.co/api/models/{repo_id}/tree/main"
    try:
        with _hf_open_with_retry(url) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise GlinerUnavailableError(
            f"Repozytorium Hugging Face '{repo_id}' nie jest dostępne "
            f"(HTTP {exc.code}) - sprawdź GlinerConfig.hf_repo_id."
        ) from exc
    except Exception as exc:  # noqa: BLE001 - sieć/CSDN po retry
        raise GlinerUnavailableError(
            f"Nie udało się pobrać manifestu z Hugging Face ({url}) po "
            f"{_HF_RETRY_ATTEMPTS} próbach: {exc}"
        ) from exc

    try:
        entries = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise GlinerUnavailableError(
            f"Manifest Hugging Face '{repo_id}' nie jest poprawnym JSON-em - "
            f"odpowiedź: {raw[:200]!r}"
        ) from exc
    if not isinstance(entries, list):
        raise GlinerUnavailableError(
            f"Manifest Hugging Face '{repo_id}' ma nieoczekiwany format "
            f"(oczekiwano listy plików, dostało {type(entries).__name__})."
        )
    return {entry["path"]: entry for entry in entries if "path" in entry}


def _hf_download_file(
    repo_id: str,
    filename: str,
    manifest_entry: dict,
    dest_dir: Path,
    progress_callback: ProgressCallback | None,
    bytes_before: int,
    bytes_total_all: int,
) -> None:
    """Pobiera JEDEN plik z Hugging Face do `dest_dir/<filename>` (przez
    plik tymczasowy `*.part` + atomowy `rename` PO weryfikacji), z pełną
    weryfikacją: rozmiar dla wszystkich plików, SHA-256 dla plików LFS
    (z `lfs.oid` manifestu). NIE sprawdza tu plików już istniejących -
    odfiltrowanie istniejących robi wywołujący (`download_gliner_model`),
    który najpierw liczy `bytes_before` dla poprawnego łącznego progresu.

    `progress_callback(bytes, total)` raportuje narastająco: suma bajtów
    plików pobranych wcześniej (`bytes_before`) + bieżący plik, względem
    łącznego `bytes_total_all` - GUI widzi jeden ciągły progres jak w
    starej ścieżce ZIP, a nie resetujące się paski per-plik.

    Rzuca `GlinerChecksumError` przy niezgodności sumy/rozmiaru (plik
    `.part` jest wtedy usuwany - uszkodzony plik NIE zostaje na dysku),
    `GlinerUnavailableError` gdy pobranie zawodzi po retry."""
    url = f"https://huggingface.co/{repo_id}/resolve/main/{filename}"
    part_path = dest_dir / f"{filename}.part"
    expected_size = manifest_entry.get("size")
    lfs_oid = (manifest_entry.get("lfs") or {}).get("oid")

    try:
        with _hf_open_with_retry(url) as response:
            # Content-Length bywa nieobecny (chunked) - wtedy rozmiar z
            # manifestu jest jedynym źródłem prawdy dla totalu.
            header_total = response.headers.get("Content-Length")
            expected_total = int(header_total) if header_total else expected_size

            digest = hashlib.sha256()
            downloaded = 0
            with open(part_path, "wb") as f:
                while True:
                    chunk = response.read(_HF_CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    if progress_callback is not None and expected_total:
                        progress_callback(
                            min(bytes_before + downloaded, bytes_total_all),
                            bytes_total_all,
                        )
    except Exception as exc:  # noqa: BLE001 - sieć/CDN po retry
        part_path.unlink(missing_ok=True)
        raise GlinerUnavailableError(
            f"Nie udało się pobrać pliku '{filename}' z Hugging Face "
            f"({url}) po {_HF_RETRY_ATTEMPTS} próbach: {exc}"
        ) from exc

    # Weryfikacja rozmiaru (wszystkie pliki) - po kompletnym pobraniu,
    # żeby wykryć ucięte transfery przy braku Content-Length.
    if expected_size is not None and downloaded != expected_size:
        part_path.unlink(missing_ok=True)
        raise GlinerChecksumError(
            f"Plik '{filename}' pobrany z Hugging Face ma rozmiar "
            f"{downloaded} B zamiast oczekiwanych {expected_size} B "
            "(manifest API tree) - transfer ucięty, plik odrzucony."
        )

    # Weryfikacja SHA-256 (tylko pliki LFS - manifest podaje lfs.oid).
    # Pliki nie-LFS (gliner_config.json, tokenizer_config.json) nie mają
    # sumy kontrolnej w API - dla nich rozmiar jest jedyną dostępną
    # weryfikacją integralności.
    if lfs_oid is not None:
        actual_sha256 = digest.hexdigest()
        if actual_sha256 != lfs_oid:
            part_path.unlink(missing_ok=True)
            raise GlinerChecksumError(
                f"Suma kontrolna pliku '{filename}' pobranego z Hugging "
                f"Face ({actual_sha256}) nie zgadza się z oczekiwaną z "
                f"manifestu ({lfs_oid}) - plik odrzucony."
            )

    # Atomowe rename po udanej weryfikacji - w katalogu docelowym nigdy
    # nie ma częściowo pobranego pliku, `load_model()` nie zobaczy śmiecia.
    part_path.replace(dest_dir / filename)


def _download_gliner_model_zip(
    config: GlinerConfig,
    progress_callback: ProgressCallback | None,
) -> Path:
    """Stara ścieżka pobierania: archiwum ZIP z eksportem ONNX modelu
    GLiNER (plik modelu + pliki konfiguracyjne/tokenizera wymagane przez
    `GLiNER.from_pretrained`, patrz `load_model()` poniżej) z GitHub
    Releases TEGO SAMEGO repo, weryfikacja SHA-256, rozpakowanie do
    katalogu nadrzędnego `config.model_path`.

    Używana jako FALLBACK `download_gliner_model()` gdy Hugging Face
    zawiedzie po retry - działa tylko, gdy `release_url`/`release_sha256`
    są skonfigurowane i release jest dostępny dla klienta (prywatne repo
    = authenticated/CI, publiczne = każdy). Zwraca ścieżkę do rozpakowanego
    pliku modelu."""
    if not config.release_sha256:
        raise GlinerChecksumError(
            "Brak skonfigurowanego SHA-256 dla artefaktu modelu GLiNER - "
            "release jeszcze nie został opublikowany (patrz app/config.py: "
            "GlinerConfig.release_sha256)."
        )

    target_path = Path(config.model_path)
    target_dir = target_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="gliner-download-") as tmp_dir:
        archive_path = Path(tmp_dir) / "gliner-model.zip"

        def _reporthook(block_num: int, block_size: int, total_size: int) -> None:
            if progress_callback is not None:
                progress_callback(min(block_num * block_size, total_size), total_size)

        urllib.request.urlretrieve(config.release_url, archive_path, reporthook=_reporthook)

        actual_sha256 = _sha256_of_file(archive_path)
        if actual_sha256 != config.release_sha256:
            raise GlinerChecksumError(
                f"Suma kontrolna pobranego archiwum ({actual_sha256}) nie zgadza się "
                f"z oczekiwaną ({config.release_sha256}) - plik odrzucony."
            )

        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(target_dir)

    if not target_path.exists():
        raise RuntimeError(
            f"Rozpakowano archiwum modelu GLiNER, ale nie znaleziono {target_path} - "
            "sprawdź strukturę archiwum wydania."
        )
    return target_path


def download_gliner_model(
    config: GlinerConfig | None = None,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    """Pobiera eksport ONNX modelu GLiNER (plik modelu + pliki
    konfiguracyjne/tokenizera wymagane przez `GLiNER.from_pretrained`,
    patrz `load_model()` poniżej) do katalogu nadrzędnego `config.model_path`.
    Zwraca ścieżkę do pliku modelu.

    PRIMARY: publiczne repo Hugging Face (`GlinerConfig.hf_repo_id`,
    domyślnie "cenkierpiotr/anonPL-300M") - działa dla anonimowego
    użytkownika końcowego bez żadnych tokenów, w przeciwieństwie do
    browser_download_url prywatnego GitHub Release (404). Manifest API
    tree pobierany raz, pliki z `GlinerConfig.hf_required_files`
    pobierane per-plik (tylko brakujące - istniejące z zgodnym rozmiarem
    są pomijane, co pozwala wznowić przerwane pobieranie), każdy przez
    plik tymczasowy `*.part` i atomowy rename PO weryfikacji (SHA-256 z
    `lfs.oid` dla plików LFS, rozmiar dla pozostałych). Retry x3
    (1s/2s/4s) na timeout/429/5xx/ConnectionError.

    FALLBACK: gdy Hugging Face zawiedzie (po retry) i config ma niepuste
    `release_url` + `release_sha256`, stara ścieżka ZIP z GitHub Releases
    tego samego repo (`_download_gliner_model_zip()`) - działa w prywatnym
    repo (authenticated/CI).

    `progress_callback(bytes_pobrane, bytes_razem)` raportuje łączny
    narastający progres wszystkich plików (GUI pokazuje jeden pasek).
    Wymaga jednorazowego połączenia z siecią; użytkownik bez internetu
    może zamiast tego ręcznie skopiować gotowy eksport ONNX pod
    `config.model_path` (ścieżka jest w pełni konfigurowalna)."""
    config = config or GlinerConfig()
    target_path = Path(config.model_path)
    target_dir = target_path.parent

    # (1) Idempotentność na poziomie wywołania: gdy WSZYSTKIE wymagane pliki
    # istnieją lokalnie z niezerowym rozmiarem - nie dotykamy sieci w ogóle
    # (GUI nie pobiera 172MB od nowa przy każdym kliknięciu przycisku).
    # Uwaga: to wstępne sprawdzenie rozmiaru != 0 jest celowo luźniejsze niż
    # pełna zgodność z manifestem - dokładną zgodność weryfikujemy niżej
    # względem manifestu, po ewentualnym pobraniu.
    if all(
        (target_dir / f).exists() and (target_dir / f).stat().st_size > 0
        for f in config.hf_required_files
    ):
        if not target_path.exists():
            raise GlinerUnavailableError(
                f"Wszystkie pliki modelu GLiNER są obecne w {target_dir}, ale "
                f"nie znaleziono {target_path} - sprawdź spójność "
                "GlinerConfig.model_path z hf_required_files."
            )
        return target_path

    try:
        # (2) Manifest API tree - RAZ dla wszystkich plików (retry x3).
        manifest = _hf_fetch_manifest(config.hf_repo_id)

        # Wszystkie wymagane pliki MUSZĄ być w manifeście - brak któregokolwiek
        # oznacza zły repo/albo zmienioną strukturę, nie pół-rozwiązanie.
        missing_in_manifest = [
            f for f in config.hf_required_files if f not in manifest
        ]
        if missing_in_manifest:
            raise GlinerUnavailableError(
                f"Repozytorium Hugging Face '{config.hf_repo_id}' nie zawiera "
                f"wymaganych plików: {', '.join(missing_in_manifest)} - sprawdź "
                "GlinerConfig.hf_repo_id / hf_required_files."
            )

        target_dir.mkdir(parents=True, exist_ok=True)

        # (3) Faza planowania: total = suma rozmiarów brakujących plików
        # (manifest = źródło prawdy), bytes_before narasta po każdym pliku -
        # stąd łączny progres GUI liczy TYLKO to, co faktycznie jest do
        # pobrania (pominięte pliki nie zafałszowują paska).
        files_to_download: list[str] = []
        for filename in config.hf_required_files:
            size = manifest[filename].get("size") or 0
            if not (target_dir / filename).exists() or (target_dir / filename).stat().st_size != size:
                files_to_download.append(filename)
        bytes_total_all = sum(
            (manifest[f].get("size") or 0) for f in files_to_download
        )

        # (4) Pobranie brakujących plików per-plik (każdy: retry x3, *.part,
        # weryfikacja, atomowy rename). Gdy wszystkie istniały z zgodnym
        # rozmiarem - pętla po prostu nic nie zrobi.
        bytes_done = 0
        for filename in files_to_download:
            _hf_download_file(
                config.hf_repo_id,
                filename,
                manifest[filename],
                target_dir,
                progress_callback,
                bytes_done,
                bytes_total_all,
            )
            bytes_done += manifest[filename].get("size") or 0

        if not target_path.exists():
            raise GlinerUnavailableError(
                f"Pobrano pliki modelu GLiNER z Hugging Face, ale nie "
                f"znaleziono {target_path} - sprawdź spójność "
                "GlinerConfig.model_path z hf_required_files."
            )
        return target_path
    except GlinerChecksumError:
        # Błąd INTEGRALNOŚCI (suma/rozmiar pliku nie zgadza się z manifestem)
        # NIE idzie w fallback ZIP: to nie jest problem dostępności HF, a
        # archiwum ZIP byłoby drugim, niezależnym artefaktem tego samego
        # modelu - użytkownik MUSI zobaczyć, że dane w repo HF są uszkodzone,
        # zanim zaufamy czemukolwiek innemu. GUI łapie ten wyjątek osobno.
        raise
    except Exception as hf_error:  # noqa: BLE001 - klasyfikacja niżej
        # (5) FALLBACK: HF nieosiągalny/zawodził po retry - stara ścieżka ZIP
        # z GitHub Releases, tylko gdy skonfigurowana (niepuste URL+sha256).
        # W prywatnym repo nadal działa (CI/dev authenticated); w publicznym
        # forku anonimowy URL da 404 i dostaniemy łączony komunikat niżej.
        if config.release_url and config.release_sha256:
            try:
                return _download_gliner_model_zip(config, progress_callback)
            except Exception as zip_exc:  # noqa: BLE001 - łączony komunikat
                raise GlinerUnavailableError(
                    f"Nie udało się pobrać modelu GLiNER z Hugging Face "
                    f"({config.hf_repo_id}): {hf_error}. Fallback na archiwum "
                    f"ZIP z GitHub Releases ({config.release_url}) też "
                    f"zawiódł: {zip_exc}"
                ) from zip_exc

        # Fallback nieskonfigurowany (pusty placeholder) - czytelny błąd
        # z kontekstem, że próbowaliśmy Hugging Face i nic więcej nie ma.
        raise GlinerUnavailableError(
            f"Nie udało się pobrać modelu GLiNER z Hugging Face "
            f"({config.hf_repo_id}): {hf_error}. Fallback na GitHub Releases "
            "nie jest skonfigurowany (pusty release_url/release_sha256)."
        ) from hf_error


# Taksonomia z planu: Grupa A (kontekstowe, wolnotekstowe, pełny trening) +
# Grupa B (identyfikatory - warstwa odpornościowa na szum OCR, na czystym
# tekście regex+checksum jest bezbłędny i tak wygra priorytetem w resolve()).
#
# UWAGA: to MUSZĄ być dosłownie te same frazy, którymi model był trenowany
# (patrz `ALL_LABELS` w `scripts/convert_to_gliner_format.py` repo treningowego
# `gliner-anonimizator-pl-finetune`) - GLiNER po fine-tuningu wiąże znaczenie
# encji z konkretnym tekstem etykiety, nie z jej nazwą kategorii. Zweryfikowane
# empirycznie na żywym modelu (anonPL-300M): błędne krótkie etykiety
# ("legal_role_person" itd.) dawały 1 trafienie na przykładowym tekście,
# poprawne opisowe frazy PL - 6 trafień na tym samym tekście.
DEFAULT_LABELS: tuple[str, ...] = (
    "osoba fizyczna (strona lub uczestnik postępowania)",
    "instytucja lub sąd",
    "adres",
    "sygnatura sprawy",
    "numer aktu notarialnego",
    "numer aktu stanu cywilnego lub poświadczenia dziedziczenia",
    "numer wpisu w rejestrze spadkowym",
    "numer PESEL",
    "numer NIP",
    "numer REGON",
    "numer rachunku bankowego IBAN",
    "numer dowodu osobistego",
    "numer VIN pojazdu",
)


@dataclass(frozen=True)
class GlinerCandidate:
    start: int
    end: int
    text: str
    label: str
    score: float


@lru_cache(maxsize=2)
def load_model(model_path: str):
    """Wczytuje model GLiNER (eksport ONNX) z podanej ścieżki, raz per proces
    (`lru_cache` - analogicznie do `ner.load_nlp`). Rzuca `GlinerUnavailableError`
    z czytelnym komunikatem (brak pakietu / brak pliku / błąd wczytania)
    zamiast pozwolić wyjątkowi zaimportowanemu z `gliner`/`onnxruntime`
    przebić się gołym tracebackiem do GUI.

    Uwaga: `lru_cache` NIE cache'uje wyjątków - nieudane wczytanie (np. brak
    pliku, bo użytkownik jeszcze nie skonfigurował ścieżki) będzie próbowane
    ponownie przy każdym kolejnym wywołaniu z tym samym argumentem. To
    zamierzone: gdy administrator dogra plik modelu w trakcie sesji, kolejne
    wywołanie odzyska działanie bez restartu aplikacji."""
    path = Path(model_path)
    if not path.exists():
        raise GlinerUnavailableError(
            f"Plik modelu GLiNER nie istnieje: {model_path}. "
            "Skonfiguruj poprawną ścieżkę w AppConfig.gliner.model_path albo "
            "wyłącz warstwę (AppConfig.gliner_enabled = False)."
        )

    try:
        from gliner import GLiNER
    except ImportError as exc:
        raise GlinerUnavailableError(
            "Pakiet 'gliner' nie jest zainstalowany. To OPCJONALNA zależność "
            "(nie ma jej domyślnie w requirements.txt) - zainstaluj ręcznie "
            "`pip install gliner onnxruntime` albo wyłącz AppConfig.gliner_enabled."
        ) from exc

    try:
        return GLiNER.from_pretrained(
            str(path.parent), load_onnx_model=True, onnx_model_file=path.name
        )
    except Exception as exc:  # noqa: BLE001 - błąd trzeciej strony nie może crashować GUI
        raise GlinerUnavailableError(
            f"Nie udało się wczytać modelu GLiNER z '{model_path}': {exc}"
        ) from exc


def find_gliner_candidates(
    text: str,
    model,
    labels: tuple[str, ...] = DEFAULT_LABELS,
    threshold: float = 0.5,
) -> list[GlinerCandidate]:
    """Uruchamia zero-shot predykcję GLiNER na blok tekstu. Zwraca WYŁĄCZNIE
    surowych kandydatów - `detect_all.detect_in_text` decyduje, które trafiają
    do `uncertain_collector` (te niepokrywające się z już zaakceptowaną
    detekcją). Ta funkcja NIGDY nie zwraca `merge.Detection`/`Replacement` -
    to celowe rozdzielenie typów pilnuje zasady bezpieczeństwa z docstringu
    modułu na poziomie systemu typów, nie tylko konwencji."""
    if not text or not text.strip():
        return []

    try:
        predictions = model.predict_entities(text, list(labels), threshold=threshold)
    except Exception as exc:  # noqa: BLE001 - błąd predykcji nie może crashować pipeline'u
        raise GlinerUnavailableError(f"Błąd predykcji GLiNER: {exc}") from exc

    candidates: list[GlinerCandidate] = []
    for pred in predictions:
        start = pred["start"]
        end = pred["end"]
        candidates.append(
            GlinerCandidate(
                start=start,
                end=end,
                text=pred.get("text", text[start:end]),
                label=pred.get("label", ""),
                score=float(pred.get("score", 0.0)),
            )
        )
    return candidates
