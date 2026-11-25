from app.detectors.digital_ids import imei_detector, ip_detector, url_detector


def test_valid_ipv4():
    assert len(ip_detector.find_all("192.168.1.1")) == 1


def test_invalid_ipv4_octet_rejected():
    assert len(ip_detector.find_all("300.300.300.300")) == 0


def test_ipv6():
    assert len(ip_detector.find_all("2001:0db8:85a3:0000:0000:8a2e:0370:7334")) == 1


def test_imei_with_prefix():
    assert len(imei_detector.find_all("IMEI 123456789012345")) == 1


def test_imei_too_short_not_matched():
    assert len(imei_detector.find_all("123")) == 0


def test_url():
    assert len(url_detector.find_all("https://google.com")) == 1


def test_no_url():
    assert len(url_detector.find_all("nie-url")) == 0
