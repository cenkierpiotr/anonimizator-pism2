"""Kwoty pieniężne: `1500 zł`, `1 500,00 zł`, `1500,50 PLN`, `1.500,00 zł`,
`5 000 EUR`, `kwotę 5000 (pięć tysięcy) złotych` itp.

Kwoty NIE są numerowane jak inne kategorie (patrz plan, sekcja "Daty i kwoty")
- polityka anonimizacji jest osobną decyzją `canonicalize.py`, ten moduł tylko
wykrywa span.
"""

from __future__ import annotations

from app.detectors.base import Detector

_INTEGER_PART = r"\d+(?:[ .]\d{3})*"
_CURRENCY = r"(?:zł|PLN|EUR|USD)"

_PATTERN = (
    rf"(?i)(?<!\d)(?P<value>"
    rf"(?:{_INTEGER_PART},\d{{2}}\s*{_CURRENCY})"
    rf"|(?:{_INTEGER_PART}\s*{_CURRENCY})"
    rf"|(?:kwotę\s+\d+\s*\([^)]+\)\s+złotych)"
    rf")"
)

detector = Detector(name="amount", pattern=_PATTERN, validate=None)
