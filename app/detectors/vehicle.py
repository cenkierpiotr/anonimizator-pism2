"""VIN pojazdu (ISO 3779, checksum na pozycji 9) i polski numer rejestracyjny.

VIN: I, O, Q niedozwolone w numerze (mylące z 1/0). Cyfra kontrolna liczona
z tabeli wartości liter i wag pozycyjnych, suma mod 11 (10 -> 'X').

Numer rejestracyjny: tylko walidacja formatu (2-3 litery kodu powiatu + 4-5
znaków), brak checksumu w realnych polskich tablicach rejestracyjnych.
"""

from __future__ import annotations

from app.detectors.base import Detector

# VIN wyklucza I/O/Q z definicji (patrz `is_valid_vin`), więc ścisły wzorzec
# `_VIN_PATTERN` też je wyklucza - ale to znaczy, że gdy OCR podstawi "O" w
# miejsce "0" (typowa pomyłka), dopasowanie w ogóle nie powstanie. Rozmyty
# wzorzec dopuszcza pełny alfanumeryczny zestaw, a właściwą korektę robi
# `ocr_tolerance.validates_with_ocr_correction` (patrz `Detector.find_all`).
_VIN_FUZZY_PATTERN = r"\b(?P<value>[A-Z0-9]{17})\b"

_VIN_TRANSLIT = {
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
    "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
}
_VIN_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)

_VIN_PATTERN = r"\b(?P<value>[A-HJ-NPR-Z0-9]{17})\b"
_PLATE_PATTERN = r"\b(?P<value>[A-Z]{2,3}\s?[A-Z0-9]{4,5})\b"


def _char_value(c: str) -> int:
    return _VIN_TRANSLIT[c] if c.isalpha() else int(c)


def is_valid_vin(value: str) -> bool:
    if len(value) != 17:
        return False
    if any(c in "IOQ" for c in value):
        return False
    checksum = sum(_char_value(c) * w for c, w in zip(value, _VIN_WEIGHTS)) % 11
    expected = "X" if checksum == 10 else str(checksum)
    return value[8] == expected


def is_valid_plate(value: str) -> bool:
    return bool(value) and 5 <= len(value.replace(" ", "")) <= 8


detector = Detector(
    name="vehicle_vin",
    pattern=_VIN_PATTERN,
    validate=is_valid_vin,
    ocr_tolerant=True,
    fuzzy_pattern=_VIN_FUZZY_PATTERN,
)
plate_detector = Detector(name="vehicle_plate", pattern=_PLATE_PATTERN, validate=is_valid_plate)
