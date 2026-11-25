from app.detectors.regon import detector, is_valid_regon


def test_valid_regon_9():
    assert is_valid_regon("012345675")


def test_invalid_regon_9():
    assert not is_valid_regon("012345676")


def test_find_all_in_text():
    text = "REGON 012345675 nadany przez..."
    matches = detector.find_all(text)
    assert len(matches) == 1
