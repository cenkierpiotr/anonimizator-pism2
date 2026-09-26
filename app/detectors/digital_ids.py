"""Identyfikatory cyfrowe: adres IP (v4/v6), IMEI, URL/profile social media."""

from __future__ import annotations

from app.detectors.base import Detector


def _is_valid_ipv4(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def _validate_ip(value: str) -> bool:
    return _is_valid_ipv4(value) if "." in value else True


_IP_PATTERN = r"(?P<value>(?:\d{1,3}\.){3}\d{1,3}|(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4})"
_IMEI_PATTERN = r"(?:IMEI[:\s]?)?(?P<value>\d{15})"
_URL_PATTERN = r"(?P<value>https?://\S+|(?:\w+\.com/\w+)|(?:@\w+))"

ip_detector = Detector(name="ip_address", pattern=_IP_PATTERN, validate=_validate_ip)
imei_detector = Detector(name="imei", pattern=_IMEI_PATTERN)
url_detector = Detector(name="url", pattern=_URL_PATTERN)
