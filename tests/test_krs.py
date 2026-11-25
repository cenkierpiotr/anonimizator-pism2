from app.detectors.krs import detector


def test_find_krs_with_prefix():
    text = "wpisana do rejestru przedsiębiorców pod numerem KRS: 0000123456."
    matches = detector.find_all(text)
    assert len(matches) == 1
    assert matches[0].value == "0000123456"


def test_no_match_without_prefix():
    text = "numer 0000123456 bez kontekstu"
    assert detector.find_all(text) == []
