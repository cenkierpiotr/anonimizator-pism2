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
WYŁĄCZONA). Pakiet `gliner` NIE jest obowiązkową zależnością aplikacji (nie
jest w `requirements.txt` jako pozycja domyślna) - import jest wykonywany
leniwie wewnątrz `load_model()`, żeby ten moduł (i reszta aplikacji) dał się
zaimportować bez tego pakietu zainstalowanego, dopóki flaga jest wyłączona."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


class GlinerUnavailableError(RuntimeError):
    """Zgłaszany gdy `gliner_enabled=True`, ale pakiet `gliner` nie jest
    zainstalowany, plik modelu ONNX nie istnieje pod skonfigurowaną ścieżką,
    albo wczytanie/predykcja modelu zawiodło z innego powodu. Wywołujący
    (`app/main.py`) MUSI to złapać i potraktować jako ostrzeżenie dla
    użytkownika (dopisane do `warnings`), NIE jako fatalny błąd całego
    przetwarzania - GLiNER jest opcjonalną warstwą recall, nie fundamentem
    pipeline'u."""


# Taksonomia z planu: Grupa A (kontekstowe, wolnotekstowe, pełny trening) +
# Grupa B (identyfikatory - warstwa odpornościowa na szum OCR, na czystym
# tekście regex+checksum jest bezbłędny i tak wygra priorytetem w resolve()).
DEFAULT_LABELS: tuple[str, ...] = (
    "legal_role_person",
    "institution",
    "address",
    "case_number",
    "notarial_act",
    "usc_act",
    "pesel",
    "nip",
    "regon",
    "iban",
    "id_card",
    "vehicle_vin",
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
