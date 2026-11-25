from app.detectors.phone import detector


def test_international_prefix():
    assert len(detector.find_all("+48 601 234 567")) == 1


def test_mobile_dashes():
    assert len(detector.find_all("601-234-567")) == 1


def test_mobile_plain():
    assert len(detector.find_all("601234567")) == 1


def test_landline_with_area_code():
    assert len(detector.find_all("(22) 123 45 67")) == 1


def test_pesel_fragment_not_matched_as_phone():
    assert detector.find_all("PESEL 44051401359 powoda") == []
