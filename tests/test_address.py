from app.detectors.address import find_addresses
from app.pipeline.ner import NerEntity


def test_street_and_postal_code_merged_into_one_span():
    text = "Powod zamieszkuje przy ul. Polnej 5, 00-950 Warszawa i wnosi o..."
    results = find_addresses(text)
    assert len(results) == 1
    assert "Polnej 5" in results[0].value
    assert "00-950 Warszawa" in results[0].value
    assert results[0].confidence == "high"


def test_anchor_phrase_without_street_prefix():
    text = "Pozwany zamieszkały w Marszałkowska 10/12 nie stawił się."
    results = find_addresses(text)
    assert len(results) == 1
    assert "Marszałkowska 10/12" in results[0].value
    assert results[0].confidence == "medium"


def test_z_siedziba_w_anchor():
    text = "Spolka z siedziba w Krakowie, ul. Dluga 3."
    # bez polskich znakow w "siedziba" test nie zlapie - test uzywa poprawnych znakow ponizej
    text2 = "Spółka z siedzibą w Krakowie, wpisana do rejestru."
    results = find_addresses(text2)
    assert len(results) == 1
    assert "Krakowie" in results[0].value


def test_no_false_positive_on_plain_sentence():
    text = "Sad wydal wyrok w sprawie o zaplate kwoty."
    results = find_addresses(text)
    assert results == []


def test_ner_location_confirmed_by_gazetteer_is_low_confidence():
    # Sygnał NER+gazetteer jest celowo ścisły (dopasowanie dokładne, forma
    # mianownikowa) - to najsłabszy z sygnałów, formy odmienione łapie
    # zamiast tego warstwa fraz-kotwic (średnia pewność).
    text = "Miejsce zamieszkania strony: Warszawa."
    loc = NerEntity(start=text.index("Warszawa"), end=text.index("Warszawa") + len("Warszawa"), text="Warszawa", label="LOC")
    results = find_addresses(text, ner_locations=[loc])
    assert any(r.confidence == "low" for r in results)


def test_ner_location_not_in_gazetteer_is_ignored():
    text = "Swiadek widzial go w Zmyslonymgrodzie wczoraj."
    fake_city = "Zmyslonymgrodzie"
    loc = NerEntity(start=text.index(fake_city), end=text.index(fake_city) + len(fake_city), text=fake_city, label="LOC")
    results = find_addresses(text, ner_locations=[loc])
    assert results == []
