"""Numer aktu notarialnego: "Rep. A Nr 1234/2026" i warianty."""

from __future__ import annotations

from app.detectors.base import Detector

_PATTERN = (
    r"(?:Rep(?:ertorium)?\.?\s*A\s*(?:Nr|Numer)\.?\s*)"
    r"(?P<value>\d{1,6}/\d{4})"
)

detector = Detector(name="notarial_act", pattern=_PATTERN)
