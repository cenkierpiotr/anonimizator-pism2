from app.detectors.notarial_act import detector


def test_rep_a_nr():
    assert len(detector.find_all("Rep. A Nr 123/2024")) == 1


def test_repertorium_variant():
    assert len(detector.find_all("Repertorium A Numer 5/2023")) == 1


def test_no_context_no_match():
    assert len(detector.find_all("zwykły zapis 123/2024")) == 0
