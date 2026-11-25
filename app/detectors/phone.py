"""Polskie numery telefonów: komórkowe (3-3-3, +48/0048) i stacjonarne
(kod strefowy 2 cyfry + 3-2-2), z granicami `\b`-podobnymi (lookaround),
żeby nie łapać fragmentu dłuższego ciągu cyfr (np. PESEL/NIP/REGON).
"""

from __future__ import annotations

from app.detectors.base import Detector

_MOBILE = r"(?:(?:\+48|0048)[\s-]?)?\d{3}[\s-]\d{3}[\s-]\d{3}|(?:\+48|0048)\d{9}|\d{9}"
_LANDLINE = r"\(?\d{2}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}"

_PATTERN = rf"(?<!\d)(?:{_MOBILE}|{_LANDLINE})(?!\d)"

detector = Detector(name="phone", pattern=_PATTERN)
