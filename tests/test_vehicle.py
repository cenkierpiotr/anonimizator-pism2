from app.detectors.vehicle import detector, is_valid_vin, plate_detector


def test_valid_vin():
    assert is_valid_vin("1M8GDM9A4KP042768")


def test_invalid_vin_checksum():
    assert not is_valid_vin("1M8GDM9A4KP042769")


def test_vin_find_all_in_text():
    text = "Pojazd o numerze VIN 1M8GDM9A4KP042768 uczestniczył w kolizji."
    matches = detector.find_all(text)
    assert len(matches) == 1


def test_plate_find_all_in_text():
    matches = plate_detector.find_all("Numer rejestracyjny WA12345 pojazdu.")
    assert len(matches) == 1
