"""Polski dowód osobisty (3 litery + 6 cyfr) i paszport (2 litery + 7 cyfr).

Dowód osobisty: litery zamieniane na wartości (A=10..Z=35), pierwsza cyfra
numeru (zaraz po literach) jest cyfrą kontrolną liczoną z wag 7,3,1 dla trzech
liter (2. litera pomijana w sumie wagowej - waga 0) i 7,3,1,7,3 dla pozostałych
pięciu cyfr numeru.

Paszport: tylko walidacja formatu, bez checksumu (brak publicznie
udokumentowanego, prostego algorytmu kontrolnego).
"""

from __future__ import annotations

from app.detectors import ocr_tolerance
from app.detectors.base import Detector

_ID_CARD_PATTERN = r"\b(?P<value>[A-Z]{3}\d{6})\b"
_PASSPORT_PATTERN = r"\b(?P<value>[A-Z]{2}\d{7})\b"
_D = ocr_tolerance.FUZZY_DIGIT_CLASS
_ID_CARD_FUZZY_PATTERN = rf"\b(?P<value>[A-Z]{{3}}{_D}{{6}})\b"

_ID_WEIGHTS = (7, 3, 1, 0, 7, 3, 1, 7, 3)


def is_valid_id_card(value: str) -> bool:
    if len(value) != 9 or not value[:3].isalpha() or not value[3:].isdigit():
        return False
    vals = [int(c, 36) for c in value[:3]] + [int(c) for c in value[3:]]
    checksum = sum(v * w for v, w in zip(vals, _ID_WEIGHTS)) % 10
    return checksum == vals[3]


def is_valid_passport(value: str) -> bool:
    return len(value) == 9 and value[:2].isalpha() and value[2:].isdigit()


detector = Detector(
    name="id_card",
    pattern=_ID_CARD_PATTERN,
    validate=is_valid_id_card,
    ocr_tolerant=True,
    fuzzy_pattern=_ID_CARD_FUZZY_PATTERN,
)
passport_detector = Detector(name="passport", pattern=_PASSPORT_PATTERN, validate=is_valid_passport)
