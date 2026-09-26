from app.detectors.email import detector


def test_email_basic():
    assert len(detector.find_all("kontakt@example.com")) == 1


def test_email_dotted_domain():
    assert len(detector.find_all("test.user@domena.pl")) == 1


def test_no_email():
    assert len(detector.find_all("to nie jest email")) == 0
