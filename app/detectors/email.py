"""Adresy e-mail (uproszczony regex, wystarczający do anonimizacji)."""

from __future__ import annotations

from app.detectors.base import Detector

_PATTERN = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"

detector = Detector(name="email", pattern=_PATTERN)
