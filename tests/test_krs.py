from app.detectors.krs import find_all


def test_find_krs_with_prefix():
    text = "wpisana do rejestru przedsiębiorców pod numerem KRS: 0000123456."
    matches = find_all(text)
    assert len(matches) == 1
    start, end = matches[0]
    assert text[start:end] == "0000123456"


def test_no_match_without_prefix():
    text = "numer 0000123456 bez kontekstu"
    assert find_all(text) == []
