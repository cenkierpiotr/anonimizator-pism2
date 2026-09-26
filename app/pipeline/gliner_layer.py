"""Warstwa GLiNER (zero-shot NER) - DODATKOWA warstwa recall, NIE zamiennik
regex+checksum. Patrz plan `.claude/plans/encapsulated-splashing-panda.md`.

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

Plik modelu ONNX (`GlinerConfig.model_path`) NIE jest częścią repo/instalatora
(binarka ~150-300MB) - jest pobierany "na żądanie" przez
`download_gliner_model()` poniżej, analogicznie do mechanizmu LibreOffice
(`legacy_convert.download_libreoffice()`): archiwum ZIP z GitHub Releases
tego samego repo, weryfikacja SHA-256, rozpakowanie do katalogu docelowego.
Świeża instalacja bez pobranego modelu nie crashuje - `load_model()` zgłasza
czytelny `GlinerUnavailableError`, złapany w `app/main.py` jako ostrzeżenie."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

from app.config import GlinerConfig

ProgressCallback = Callable[[int, int], None]  # (bytes_pobrane, bytes_razem)


class GlinerUnavailableError(RuntimeError):
    """Zgłaszany gdy `gliner_enabled=True`, ale pakiet `gliner` nie jest
    zainstalowany, plik modelu ONNX nie istnieje pod skonfigurowaną ścieżką,
    albo wczytanie/predykcja modelu zawiodło z innego powodu. Wywołujący
    (`app/main.py`) MUSI to złapać i potraktować jako ostrzeżenie dla
    użytkownika (dopisane do `warnings`), NIE jako fatalny błąd całego
    przetwarzania - GLiNER jest opcjonalną warstwą recall, nie fundamentem
    pipeline'u."""


class GlinerChecksumError(RuntimeError):
    """Pobrane archiwum modelu GLiNER nie zgadza się z oczekiwanym SHA-256 -
    odrzucone, nie rozpakowujemy niezweryfikowanego pliku binarnego (patrz
    `legacy_convert.LibreOfficeChecksumError` - identyczny wzorzec). Zgłaszany
    też, gdy `GlinerConfig.release_sha256` jest jeszcze pustym placeholderem
    (release nie został opublikowany)."""


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_gliner_model(
    config: GlinerConfig | None = None,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    """Pobiera archiwum ZIP z eksportem ONNX modelu GLiNER (plik modelu +
    pliki konfiguracyjne/tokenizera wymagane przez `GLiNER.from_pretrained`,
    patrz `load_model()` poniżej) z GitHub Releases TEGO SAMEGO repo,
    weryfikuje SHA-256 archiwum i rozpakowuje do katalogu nadrzędnego
    `config.model_path`. Zwraca ścieżkę do rozpakowanego pliku modelu.

    Mechanizm analogiczny do `legacy_convert.download_libreoffice()` - patrz
    tam po pełne uzasadnienie wzorca (artefakt hostowany we własnym repo
    Releases, weryfikacja checksum, czytelny błąd gdy sha256 nie jest jeszcze
    skonfigurowany). Wymaga jednorazowego połączenia z siecią; użytkownik bez
    internetu może zamiast tego ręcznie skopiować gotowy eksport ONNX pod
    `config.model_path` (ścieżka jest w pełni konfigurowalna)."""
    config = config or GlinerConfig()
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
