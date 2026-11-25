from app.detectors.iban import detector, is_valid_iban


def test_valid_pl_iban():
    assert is_valid_iban("PL61109010140000071219812874")


def test_valid_pl_iban_with_spaces():
    assert is_valid_iban("PL61 1090 1014 0000 0712 1981 2874")


def test_invalid_checksum():
    assert not is_valid_iban("PL61109010140000071219812875")


def test_find_all_in_text():
    text = "Proszę o przelew na rachunek PL61 1090 1014 0000 0712 1981 2874 tytułem..."
    matches = detector.find_all(text)
    assert len(matches) == 1
