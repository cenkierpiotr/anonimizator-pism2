from app.detectors.npwz import find_all


def test_npwz_keyword():
    matches = find_all("Lekarz posiada NPWZ 1234567")
    assert len(matches) == 1


def test_npwz_full_phrase():
    matches = find_all("prawo wykonywania zawodu 7654321")
    assert len(matches) == 1


def test_npwz_no_context():
    assert find_all("zwykły numer 1234567") == []
