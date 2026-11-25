"""Testy wpięcia warstwy GLiNER w `detect_all.detect_in_text` (patrz plan,
sekcja "Integracja z pipeline'em"). Kluczowa zasada bezpieczeństwa pod testem:
GLiNER NIGDY nie trafia do zwracanych `Replacement` - wyłącznie do
`uncertain_collector`, z prefiksem "[GLiNER]", i tylko gdy nie pokrywa się z
żadną już zaakceptowaną detekcją."""

from app.pipeline.detect_all import detect_in_text
from app.pipeline.identity_cluster import IdentityRegistry


class _FakeGlinerModel:
    def __init__(self, predictions):
        self._predictions = predictions

    def predict_entities(self, text, labels, threshold=0.5):
        return self._predictions


def test_gliner_none_by_default_no_extra_uncertain_entries():
    text = "Zwykły tekst bez żadnych danych osobowych."
    uncertain: list[str] = []

    detect_in_text(text, IdentityRegistry(), uncertain_collector=uncertain)

    assert uncertain == []


def test_gliner_hit_not_overlapping_existing_detection_goes_to_uncertain():
    # Fikcyjna nazwa, celowo nierozpoznawalna przez żaden istniejący detektor
    # (regex/checksum/NER/gazetteer - zweryfikowane empirycznie: `detect_in_text`
    # na tym tekście bez `gliner_model` zwraca pustą listę) - to właśnie
    # przypadek, w którym warstwa GLiNER ma sens (patrz plan: kontekstowe
    # encje wolnotekstowe pominięte przez pozostałe warstwy).
    text = "Wniosek dotyczy nieruchomości zwanej lokalnie Wichrowe Zaświaty."
    start = text.index("Wichrowe Zaświaty")
    end = start + len("Wichrowe Zaświaty")
    model = _FakeGlinerModel(
        [{"start": start, "end": end, "text": "Wichrowe Zaświaty", "label": "institution", "score": 0.61}]
    )
    uncertain: list[str] = []

    replacements = detect_in_text(
        text, IdentityRegistry(), uncertain_collector=uncertain, gliner_model=model
    )

    assert any(note.startswith("[GLiNER]") for note in uncertain)
    assert any("institution" in note and "61%" in note for note in uncertain)
    # Zasada bezpieczeństwa: GLiNER nigdy nie trafia do finalnych podmian.
    assert not any(r.category == "institution" and r.start == start for r in replacements)


def test_gliner_hit_overlapping_existing_detection_is_suppressed():
    """Instytucja "Sąd Rejonowy w Krakowie" jest już wykrywana przez
    deterministyczny detektor `institutions` - GLiNER trafiający w ten sam
    (lub pokrywający się) fragment NIE powinien tworzyć duplikatu w
    uncertain_collector, bo istniejąca detekcja już wygrała priorytetem."""
    text = "Sprawa toczy się przed Sądem Rejonowym w Krakowie, Wydział I Cywilny."
    start = text.index("Sądem Rejonowym w Krakowie")
    end = start + len("Sądem Rejonowym w Krakowie")
    model = _FakeGlinerModel(
        [{"start": start, "end": end, "text": "Sądem Rejonowym w Krakowie", "label": "institution", "score": 0.55}]
    )
    uncertain: list[str] = []

    detect_in_text(text, IdentityRegistry(), uncertain_collector=uncertain, gliner_model=model)

    assert not any(note.startswith("[GLiNER]") for note in uncertain)


def test_gliner_prediction_error_is_reported_not_raised():
    class _BrokenModel:
        def predict_entities(self, text, labels, threshold=0.5):
            raise RuntimeError("awaria silnika ONNX")

    text = "Jakiś tekst dokumentu."
    uncertain: list[str] = []

    # Nie może rzucić wyjątku - błąd warstwy GLiNER trafia do uncertain_collector.
    detect_in_text(text, IdentityRegistry(), uncertain_collector=uncertain, gliner_model=_BrokenModel())

    assert any("[GLiNER]" in note and "Błąd" in note for note in uncertain)


def test_gliner_ignored_without_uncertain_collector():
    """Gdy wywołujący nie podał uncertain_collector, warstwa GLiNER jest po
    prostu pomijana (nie ma gdzie odłożyć wyniku) - nie powinno to wywołać
    żadnego wyjątku."""
    model = _FakeGlinerModel([{"start": 0, "end": 4, "text": "Test", "label": "institution", "score": 0.9}])

    replacements = detect_in_text("Test tekst.", IdentityRegistry(), gliner_model=model)

    assert isinstance(replacements, list)
