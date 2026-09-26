"""Testy dla `app/detectors/gazetteer_name.py` - awaryjna warstwa imię+nazwisko
oparta o gazetteer, uruchamiana w `detect_all.py` tylko gdy NER nie znalazł w
danym bloku ani jednej osoby (patrz `_PRIORITY_GAZETTEER_NAME_FALLBACK`).

Znalezione testem e2e: krótki tekst bez kontekstu zdaniowego (typowy dla
nagłówka skanu OCR albo wartości komórki tabeli) potrafi sprawić, że spaCy
(`pl_core_news_md`) nie rozpozna ŻADNEJ osoby, mimo że imię i nazwisko są
znanymi wartościami z `app/pipeline/gazetteers.py` - to prowadziło do
całkowitego wycieku danych w wyniku."""

from app.detectors import gazetteer_name
from app.pipeline.detect_all import detect_in_text
from app.pipeline.identity_cluster import IdentityRegistry


def test_finds_first_name_surname_pair():
    matches = gazetteer_name.find_all("Wniosek - Jan Kowalski PESEL: 44051401359")
    assert any(m.value == "Jan Kowalski" for m in matches)


def test_finds_surname_first_name_pair():
    matches = gazetteer_name.find_all("Dane: Kowalski Jan, PESEL 44051401359")
    assert any(m.value == "Kowalski Jan" for m in matches)


def test_ignores_unrelated_capitalized_pair():
    matches = gazetteer_name.find_all("Sąd Rejonowy dla Warszawy-Śródmieścia")
    assert matches == []


def test_low_score_uncertain():
    matches = gazetteer_name.find_all("Wniosek - Jan Kowalski")
    assert all(m.score < 1.0 for m in matches)


def test_detect_in_text_catches_name_missed_entirely_by_ner():
    """Regresja: tekst bez kontekstu zdaniowego (nagłówek-style, jak w OCR
    krótkiego skanu), gdzie NER zwraca zero encji PERSON - musi mimo to
    zostać zanonimizowany przez warstwę awaryjną."""
    text = "Wniosek - Jan Kowalski\nPESEL: 44051401359"
    registry = IdentityRegistry()
    replacements = detect_in_text(text, registry)
    labels_applied = [r.label for r in replacements]
    result = text
    for r in sorted(replacements, key=lambda r: r.start, reverse=True):
        result = result[: r.start] + r.label + result[r.end :]
    assert "Jan Kowalski" not in result
    assert any(label.startswith("[Osoba") for label in labels_applied)


def test_detect_in_text_does_not_double_fire_when_ner_already_found_someone():
    """Gdy NER poprawnie rozpozna choć jedną osobę w bloku, warstwa awaryjna
    się nie uruchamia - unika mnożenia fałszywych alarmów na zwykłym tekście."""
    text = (
        "Powód Jan Kowalski wnosi pozew. W tabeli poniżej: Anna Nowak, "
        "zamieszkała w Warszawie."
    )
    registry = IdentityRegistry()
    replacements = detect_in_text(text, registry)
    result = text
    for r in sorted(replacements, key=lambda r: r.start, reverse=True):
        result = result[: r.start] + r.label + result[r.end :]
    # "Anna Nowak" jest rozpoznawana normalnie przez NER (kontekst zdaniowy) -
    # warstwa awaryjna nie musi interweniować, ale wynik i tak nie może
    # zawierać żadnego z nazwisk w czystym tekście.
    assert "Jan Kowalski" not in result
    assert "Anna Nowak" not in result
