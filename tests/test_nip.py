from app.detectors.nip import detector, is_valid_nip


def test_valid_nip():
    assert is_valid_nip("526-000-12-46")


def test_valid_nip_no_dashes():
    assert is_valid_nip("5260001246")


def test_invalid_checksum():
    assert not is_valid_nip("5260001247")


def test_find_all_in_text():
    text = "Sprzedawca NIP: 526-000-12-46 z siedzibą w..."
    matches = detector.find_all(text)
    assert len(matches) == 1
