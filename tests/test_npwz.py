from app.detectors.npwz import detector


def test_npwz_keyword():
    matches = detector.find_all("Lekarz posiada NPWZ 1234567")
    assert len(matches) == 1


def test_npwz_full_phrase():
    matches = detector.find_all("prawo wykonywania zawodu 7654321")
    assert len(matches) == 1


def test_npwz_no_context():
    assert detector.find_all("zwykły numer 1234567") == []
