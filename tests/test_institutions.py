from app.detectors.institutions import detector


def test_sad_rejonowy():
    assert len(detector.find_all("Sąd Rejonowy w Warszawie")) == 1


def test_komenda_miejska_policji():
    assert len(detector.find_all("Komenda Miejska Policji w Krakowie")) == 1


def test_prokuratura_okregowa():
    assert len(detector.find_all("Prokuratura Okręgowa w Gdańsku")) == 1


def test_no_match_for_unrelated_phrase():
    assert len(detector.find_all("Sklep w Warszawie")) == 0
