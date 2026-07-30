from app.pipeline import gazetteers


def test_known_first_name_case_insensitive():
    assert gazetteers.is_known_first_name("Jan")
    assert gazetteers.is_known_first_name("jan")
    assert gazetteers.is_known_first_name("ANNA")


def test_unknown_first_name():
    assert not gazetteers.is_known_first_name("Xzyzyx123")


def test_known_surname():
    assert gazetteers.is_known_surname("Kowalski")
    assert gazetteers.is_known_surname("nowak")


def test_known_city():
    assert gazetteers.is_known_city("Warszawa")
    assert gazetteers.is_known_city("kraków")


def test_multiword_city_lookup():
    assert gazetteers.is_known_city("Nowy Sącz")


def test_unknown_city():
    assert not gazetteers.is_known_city("Nienazwane Miasto Zmyslone")


def test_gazetteer_sets_are_non_empty():
    assert len(gazetteers.first_names()) > 100
    assert len(gazetteers.surnames()) > 30
    assert len(gazetteers.cities()) > 200
