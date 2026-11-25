"""NIP: 10 cyfr (z myślnikami lub bez), checksum wag 6,5,7,2,3,4,5,6,7 (mod 11, != 10)."""

from __future__ import annotations

from app.detectors import ocr_tolerance
from app.detectors.base import Detector

_WEIGHTS = (6, 5, 7, 2, 3, 4, 5, 6, 7)
_PATTERN = r"(?<!\d)(?P<value>\d{3}-?\d{3}-?\d{2}-?\d{2}|\d{3}-\d{2}-\d{2}-\d{3})(?!\d)"
_D = ocr_tolerance.FUZZY_DIGIT_CLASS
_FUZZY_PATTERN = (
    rf"(?<!{_D})(?P<value>{_D}{{3}}-?{_D}{{3}}-?{_D}{{2}}-?{_D}{{2}}"
    rf"|{_D}{{3}}-{_D}{{2}}-{_D}{{2}}-{_D}{{3}})(?!{_D})"
)


def is_valid_nip(value: str) -> bool:
    digits_str = value.replace("-", "")
    if len(digits_str) != 10 or not digits_str.isdigit():
        return False
    digits = [int(c) for c in digits_str]
    checksum = sum(w * d for w, d in zip(_WEIGHTS, digits)) % 11
    if checksum == 10:
        return False
    return checksum == digits[9]


detector = Detector(
    name="nip",
    pattern=_PATTERN,
    validate=is_valid_nip,
    ocr_tolerant=True,
    fuzzy_pattern=_FUZZY_PATTERN,
)
