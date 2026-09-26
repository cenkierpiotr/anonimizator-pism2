from app.detectors.legal_roles import detector


def test_mec_prefix():
    matches = detector.find_all("Mec. Jan Kowalski prowadzi sprawę")
    assert len(matches) == 1
    assert matches[0].value == "Jan Kowalski"


def test_powod_capitalized():
    matches = detector.find_all("Powód Adam Nowak złożył pozew")
    assert len(matches) == 1
    assert matches[0].value == "Adam Nowak"


def test_lowercase_name_not_matched():
    assert detector.find_all("Mec. jan kowalski") == []
