"""Nazwy sądów, prokuratur i jednostek policji wraz z miejscowością."""

from __future__ import annotations

from app.detectors.base import Detector

_PATTERN = (
    r"(?P<value>(?:Sąd|Prokuratura|Komenda)\s+"
    r"(?:Rejonowy|Rejonowa|Okręgowy|Okręgowa|Apelacyjny|Powiatowa|Miejska|Wojewódzka)\s+"
    r"(?:Policji\s+)?w\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)"
)

detector = Detector(name="institution", pattern=_PATTERN)
