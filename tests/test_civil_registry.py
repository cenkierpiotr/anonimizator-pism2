from app.detectors.civil_registry import apd_detector, nors_detector, usc_detector


def test_usc_act():
    assert len(usc_detector.find_all("akt urodzenia nr 12/2022")) == 1
    assert len(usc_detector.find_all("akt małżeństwa nr 7/2020")) == 1


def test_apd():
    assert len(apd_detector.find_all("poświadczenie dziedziczenia Rep. A Nr 100/2024")) == 1


def test_nors():
    assert len(nors_detector.find_all("NORS/123/2024")) == 1
    assert len(nors_detector.find_all("brak numeru")) == 0
