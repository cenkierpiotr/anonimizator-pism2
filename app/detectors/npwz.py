"""Numer Prawa Wykonywania Zawodu lekarza (NPWZ, zwykle 7 cyfr).

Detektor kontekstowy (jak KRS): wymaga słowa "NPWZ" lub frazy
"prawo wykonywania zawodu" w bezpośrednim sąsiedztwie numeru, bo sam
7-cyfrowy ciąg nie ma żadnego checksumu i byłby zbyt niespecyficzny.

Dodatkowo łapie numery wpisu na listę izb zawodowych z prefiksem
województwa (np. "numer wpisu WA-1423" - Warszawa, adwokaci/radcowie):
"WA", "WR", "GD" itd. bez checksumu są publicznie wyszukiwalne w
rejestrach izb, więc realnie identyfikują osobę i MUSZĄ zostać
zanonimizowane. Format: 2 litery, myślnik, 4-6 cyfr.
"""

from __future__ import annotations

import re

from app.detectors.base import Detector

_PATTERN = re.compile(
    r"(?:NPWZ|prawo wykonywania zawodu)\W{0,20}?(?P<value>\d{7})\b",
    re.IGNORECASE,
)

# Numer wpisu na listę izby zawodowej: prefiks województwa + myślnik + cyfry,
# poprzedzony frazą "numer wpisu" (bez kontekstu dwie litery + cyfry to
# zbyt często np. numery rejestracyjne/skróty w tekście).
_ENTRY_NUMBER_PATTERN = re.compile(
    r"numer\s+wpisu\W{0,10}(?P<value>[A-Z]{2}-\d{4,6})\b",
    re.IGNORECASE,
)


class _NpwzDetector(Detector):
    """Detektor NPWZ + numerów wpisu na listę izb zawodowych."""

    def find_all(self, text: str) -> list["Match"]:
        from app.detectors.base import Match

        results = super().find_all(text)
        for m in _ENTRY_NUMBER_PATTERN.finditer(text):
            results.append(Match(start=m.start("value"), end=m.end("value"), value=m.group("value")))
        return results


detector = _NpwzDetector(name="npwz", pattern=_PATTERN)
