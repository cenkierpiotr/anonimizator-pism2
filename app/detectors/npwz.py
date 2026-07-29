"""Numer Prawa Wykonywania Zawodu lekarza (NPWZ, zwykle 7 cyfr).

Detektor kontekstowy (jak KRS): wymaga słowa "NPWZ" lub frazy
"prawo wykonywania zawodu" w bezpośrednim sąsiedztwie numeru, bo sam
7-cyfrowy ciąg nie ma żadnego checksumu i byłby zbyt niespecyficzny.
"""

from __future__ import annotations

import re

_PATTERN = re.compile(
    r"(?:NPWZ|prawo wykonywania zawodu)\W{0,20}?(?P<value>\d{7})\b",
    re.IGNORECASE,
)


def find_all(text: str) -> list[tuple[int, int]]:
    return [(m.start("value"), m.end("value")) for m in _PATTERN.finditer(text)]
