"""Numer księgi wieczystej (KW): WWWW/NNNNNNNN/C.

WWWW - 4-znakowy kod sądu wieczystoksięgowego (litery+cyfry), NNNNNNNN - 8-cyfrowy
numer, C - cyfra kontrolna. Implementacja checksumu: litery kodu sądu zamieniane
na wartości (A=10..Z=35), połączone z numerem (18 cyfr), ważone cyklicznie
wagami 1,3,7 licząc od najmniej znaczącej cyfry, suma mod 10 = cyfra kontrolna.

Uwaga: to best-effort odwzorowanie opublikowanego algorytmu MS, nie zweryfikowane
na próbce realnych numerów KW z rejestru - traktować jako filtr obniżający liczbę
fałszywych trafień, nie jako formalną walidację prawną.
"""

from __future__ import annotations

from app.detectors.base import Detector

_PATTERN = r"\b(?P<value>[A-Z0-9]{4}/\d{8}/\d)\b"

_WEIGHTS_CYCLE = (1, 3, 7)


def is_valid_kw(value: str) -> bool:
    parts = value.split("/")
    if len(parts) != 3:
        return False
    code, num, check = parts
    if len(code) != 4 or len(num) != 8 or not check.isdigit():
        return False
    try:
        code_digits = "".join(str(int(c, 36)) for c in code)
    except ValueError:
        return False
    digits = [int(d) for d in code_digits + num]
    digits.reverse()
    weights = [_WEIGHTS_CYCLE[i % 3] for i in range(len(digits))]
    checksum = sum(d * w for d, w in zip(digits, weights)) % 10
    return checksum == int(check)


detector = Detector(name="land_register", pattern=_PATTERN, validate=is_valid_kw, ocr_tolerant=True)
