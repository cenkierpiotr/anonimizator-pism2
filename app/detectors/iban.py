"""IBAN (dowolny kraj, priorytet PL): checksum mod 97 wg ISO 7064 (MOD 97-10)."""

from __future__ import annotations

from app.detectors.base import Detector

_PATTERN = r"(?<![A-Za-z0-9])(?P<value>[A-Z]{2}\d{2}(?:[ ]?\d{4}){2,7})(?![A-Za-z0-9])"


def is_valid_iban(value: str) -> bool:
    compact = value.replace(" ", "")
    if len(compact) < 15 or len(compact) > 34:
        return False
    if not compact[:2].isalpha() or not compact[2:4].isdigit():
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(str(int(c, 36)) for c in rearranged)
    return int(numeric) % 97 == 1


detector = Detector(name="iban", pattern=_PATTERN, validate=is_valid_iban)
