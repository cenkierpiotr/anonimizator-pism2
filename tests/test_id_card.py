from app.detectors.id_card import detector, is_valid_id_card, is_valid_passport, passport_detector


def test_valid_id_card():
    assert is_valid_id_card("AAT923456")


def test_invalid_id_card_checksum():
    assert not is_valid_id_card("AAT523456")


def test_find_all_in_text():
    text = "Dowód osobisty nr AAT923456 wydany przez..."
    matches = detector.find_all(text)
    assert len(matches) == 1


def test_valid_passport_format():
    assert is_valid_passport("AB1234567")


def test_passport_find_all():
    matches = passport_detector.find_all("Paszport AB1234567")
    assert len(matches) == 1
