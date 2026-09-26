from app.detectors.pesel import detector, is_valid_pesel


def test_valid_pesel():
    assert is_valid_pesel("44051401359")


def test_invalid_checksum():
    assert not is_valid_pesel("44051401358")


def test_wrong_length():
    assert not is_valid_pesel("123")


def test_find_all_in_text():
    text = "Zamawiający, PESEL 44051401359, oświadcza że..."
    matches = detector.find_all(text)
    assert len(matches) == 1
    assert matches[0].value == "44051401359"


def test_ignores_invalid_pesel_shaped_number():
    text = "kwota 12345678901 zł"
    matches = detector.find_all(text)
    assert matches == []
