from app.detectors.amounts import detector


def test_plain_amount():
    assert len(detector.find_all("1500 zł")) == 1


def test_grouped_amount_with_decimals():
    assert len(detector.find_all("1 500,00 zł")) == 1


def test_pln_with_decimals():
    assert len(detector.find_all("1500,50 PLN")) == 1


def test_dot_grouped_amount():
    assert len(detector.find_all("1.500,00 zł")) == 1


def test_foreign_currency():
    assert len(detector.find_all("5 000 EUR")) == 1


def test_spelled_out_amount():
    assert len(detector.find_all("kwotę 5000 (pięć tysięcy) złotych")) == 1
