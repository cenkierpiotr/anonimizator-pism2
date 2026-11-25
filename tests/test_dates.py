from app.detectors.dates import birth_date_detector, detector


def test_general_date_formats():
    text = "12.03.2024, 2024-03-12, 12 marca 2024 r., 12.03.2024 roku"
    assert len(detector.find_all(text)) == 4


def test_birth_date_context():
    text = "urodzony 12.03.1990 oraz data urodzenia 15 maja 2000"
    matches = birth_date_detector.find_all(text)
    assert len(matches) == 2
    assert matches[0].value == "12.03.1990"


def test_plain_date_not_birth_date():
    assert birth_date_detector.find_all("Data to 12.03.2024") == []
