"""PESEL: 11 cyfr, checksum wag 1,3,7,9,1,3,7,9,1,3 (mod 10)."""

from __future__ import annotations

from app.detectors.base import Detector

_WEIGHTS = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
_PATTERN = r"(?<!\d)(?P<value>\d{11})(?!\d)"


def is_valid_pesel(value: str) -> bool:
    if len(value) != 11 or not value.isdigit():
        return False
    digits = [int(c) for c in value]
    checksum = sum(w * d for w, d in zip(_WEIGHTS, digits)) % 10
    control = (10 - checksum) % 10
    return control == digits[10]


detector = Detector(name="pesel", pattern=_PATTERN, validate=is_valid_pesel, ocr_tolerant=True)
