"""Detektory kontekstowe: akt stanu cywilnego (USC), poświadczenie dziedziczenia,
wpis w Rejestrze Spadkowym (NORS).
"""

from __future__ import annotations

from app.detectors.base import Detector

usc_detector = Detector(
    name="usc_act",
    pattern=r"(?:akt(?:u)?\s+(?:urodzenia|małżeństwa|zgonu)\s+nr\s*)(?P<value>\d+/\d{4})",
)

apd_detector = Detector(
    name="poswiadczenie_dziedziczenia",
    pattern=r"poświadczenie dziedziczenia\W{0,30}?(?:Rep\.\s*A\s*Nr\s*)(?P<value>\d+/\d{4})",
)

nors_detector = Detector(
    name="rejestr_spadkowy",
    pattern=r"(?:Rejestr Spadkowy|NORS)\W{0,15}?(?P<value>[A-Z0-9-/]+/\d{4})",
)
