"""REGON: 9 lub 14 cyfr, checksum wag mod 11 (!= 10 -> 0)."""

from __future__ import annotations

from app.detectors import ocr_tolerance
from app.detectors.base import Detector

_WEIGHTS_9 = (8, 9, 2, 3, 4, 5, 6, 7)
_WEIGHTS_14 = (2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8)
_PATTERN = r"(?<!\d)(?P<value>\d{9}|\d{14})(?!\d)"
_D = ocr_tolerance.FUZZY_DIGIT_CLASS
_FUZZY_PATTERN = rf"(?<!{_D})(?P<value>{_D}{{9}}|{_D}{{14}})(?!{_D})"


def _checksum(digits: list[int], weights: tuple[int, ...]) -> int:
    total = sum(w * d for w, d in zip(weights, digits))
    control = total % 11
    return 0 if control == 10 else control


def is_valid_regon(value: str) -> bool:
    if not value.isdigit():
        return False
    digits = [int(c) for c in value]
    if len(digits) == 9:
        return _checksum(digits, _WEIGHTS_9) == digits[8]
    if len(digits) == 14:
        # 14-cyfrowy REGON: pierwsze 9 cyfr musi być poprawnym REGON-em bazowym.
        if _checksum(digits[:9], _WEIGHTS_9) != digits[8]:
            return False
        return _checksum(digits, _WEIGHTS_14) == digits[13]
    return False


detector = Detector(
    name="regon",
    pattern=_PATTERN,
    validate=is_valid_regon,
    ocr_tolerant=True,
    fuzzy_pattern=_FUZZY_PATTERN,
)
