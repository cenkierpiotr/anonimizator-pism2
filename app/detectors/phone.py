"""Polskie numery telefonów: komórkowe (3-3-3, +48/0048) i stacjonarne
(kod strefowy 2 cyfry + 3-2-2), z granicami `\b`-podobnymi (lookaround),
żeby nie łapać fragmentu dłuższego ciągu cyfr (np. PESEL/NIP/REGON).

Dodatkowe zabezpieczenia przed fałszywymi trafieniami na identyfikatorach
(realny przypadek z umowy demo: REGON o błędnej sumie kontrolnej — 9 cyfr —
łapany jako "[numer telefonu]"):

- goła forma bez separatorów (9 cyfr z rzędu) jest telefonem tylko, gdy
  zaczyna się od realnego prefiksu komórkowego (5-8xx) — identyfikatory
  mogą zaczynać się dowolną cyfrą;
- forma stacjonarna musi mieć nawias wokół kierunkowego albo separator
  zaraz po nim — "221234567" z rzędu to prawie nigdy nie telefon;
- trafienie poprzedzone w promieniu kilku znaków słowem-kluczem
  identyfikatora (REGON, KRS, NIP, PESEL, NPWZ, "numer wpisu") NIE jest
  telefonem — bo identyfikator odrzucony przez checksum (np. literówka w
  REGON) ma identyczny "telefoniczny" kształt 9 cyfr.
"""

from __future__ import annotations

import re

from app.detectors.base import Detector, Match

# Formy z separatorami/prefixem pozostają bez ograniczeń prefiksu (układ
# 3-3-3 / +48 sam w sobie jest mocno "telefoniczny"); forma goła tylko z
# prefiksem komórkowym 5-8.
_MOBILE = (
    r"(?:(?:\+48|0048)[\s-]?)?\d{3}[\s-]\d{3}[\s-]\d{3}"
    r"|(?:\+48|0048)\d{9}"
    r"|[5-8]\d{8}"
)
# Stacjonarny: nawias wokół kierunkowego (opcjonalny separator po nim)
# LUB kierunkowy z separatorem — forma w pełni zlepiona nie jest telefonem.
_LANDLINE = r"(?:\(\d{2}\)[\s-]?|\d{2}[\s-])\d{3}[\s-]?\d{2}[\s-]?\d{2}"

_PATTERN = rf"(?<!\d)(?:{_MOBILE}|{_LANDLINE})(?!\d)"

# Słowa-klucze oznaczające, że następująca liczba to identyfikator, nie telefon.
_IDENTIFIER_CONTEXT = re.compile(
    r"(?i)\b(?:regon|krs|nip|pesel|npwz|numer\s+wpisu)\W{0,6}$"
)


class PhoneDetector(Detector):
    """Detektor telefonu z kontekstowym filtrem identyfikatorów (opis wyżej)."""

    def find_all(self, text: str) -> list[Match]:
        matches = super().find_all(text)
        return [
            m
            for m in matches
            if not _IDENTIFIER_CONTEXT.search(text, 0, m.start)
        ]


detector = PhoneDetector(name="phone", pattern=_PATTERN)
