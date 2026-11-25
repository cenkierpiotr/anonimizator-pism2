"""Sygnatury akt sądowych/prokuratorskich/komorniczych, rozbite na podtypy.

Każdy podtyp wymaga twardej kotwicy (prefiks wydziału rzymskimi cyframi,
literalny skrót "Ds."/"RSD"/"Km"/"KIO"...), dzięki czemu zwykłe daty
(np. "12.03.2024") czy numery telefonów nie są dopasowywane.
"""

from __future__ import annotations

import re

from app.detectors.base import Detector, Match

SUBTYPE_PATTERNS: dict[str, re.Pattern[str]] = {
    "cywilne_gospodarcze": re.compile(r"\b[IVX]{1,3}\s+(?:C|Nc|GC|Ns|Co)\s+\d{1,5}/\d{2,4}\b"),
    "karne": re.compile(r"\b[IVX]{1,3}\s+(?:K|Ko|Kp)\s+\d{1,5}/\d{2,4}\b"),
    "prokuratorskie": re.compile(r"\b(?:PR\s+\d+\s+)?Ds\.\s?\d{1,6}\.\d{2,4}\b"),
    "policyjne": re.compile(r"\bRSD[\s-]\d{1,6}[/-]\d{2,4}\b"),
    "administracyjne": re.compile(r"\b(?:[IVX]{1,3}\s+SA/[A-Za-z]{2,3}|[IVX]{1,3}\s+OSK)\s+\d{1,5}/\d{2,4}\b"),
    "sn_kio": re.compile(r"\b(?:[IVX]{1,3}\s+CSK|KIO)\s+\d{1,5}/\d{2,4}\b"),
    "komornicze": re.compile(r"\b(?:G)?Km[p]?\s+\d{1,6}/\d{2,4}\b"),
}

_COMBINED_PATTERN = "|".join(f"(?:{p.pattern})" for p in SUBTYPE_PATTERNS.values())

detector = Detector(name="case_number", pattern=_COMBINED_PATTERN)


def find_all_with_subtype(text: str) -> list[tuple[Match, str]]:
    candidates: list[tuple[Match, str]] = []
    for subtype, pattern in SUBTYPE_PATTERNS.items():
        for m in pattern.finditer(text):
            candidates.append((Match(start=m.start(), end=m.end(), value=m.group(0)), subtype))

    candidates.sort(key=lambda item: (item[0].start, -(item[0].end - item[0].start)))

    results: list[tuple[Match, str]] = []
    last_end = -1
    for match, subtype in candidates:
        if match.start >= last_end:
            results.append((match, subtype))
            last_end = match.end
    return results
