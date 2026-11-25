import pytest

from app.pipeline import ner


@pytest.fixture(scope="module")
def nlp():
    return ner.load_nlp()


def test_finds_person_entity(nlp):
    text = "Powod Jan Kowalski wniosl pozew przeciwko Annie Nowak."
    entities = ner.find_entities(text, nlp=nlp)
    persons = [e for e in entities if e.label == "PERSON"]
    assert any("Kowalski" in e.text for e in persons)


def test_finds_location_entity(nlp):
    text = "Pozwany zamieszkuje w Warszawie przy ulicy Marszalkowskiej."
    entities = ner.find_entities(text, nlp=nlp)
    assert any(e.label == "LOC" for e in entities)


def test_entity_offsets_map_back_to_source_text(nlp):
    text = "Swiadek Piotr Zielinski zeznal przed sadem."
    entities = ner.find_entities(text, nlp=nlp)
    for e in entities:
        assert text[e.start:e.end] == e.text


def test_only_known_labels_are_returned(nlp):
    text = "Umowa zawarta dnia 5 maja 2024 roku pomiedzy stronami."
    entities = ner.find_entities(text, nlp=nlp)
    assert all(e.label in {"PERSON", "ORG", "LOC"} for e in entities)
