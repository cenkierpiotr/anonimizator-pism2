"""Centralny rejestr detektorów.

`CHECKSUM_DETECTORS` — detektory z pełną walidacją matematyczną (checksum),
bezpieczne do użycia w `leak_check.py` bez kontekstu, bo mają bardzo niską
szansę fałszywego trafienia na przypadkowym ciągu znaków.
"""

from __future__ import annotations

from app.detectors import iban, nip, pesel, regon
from app.detectors.base import Detector

CHECKSUM_DETECTORS: list[Detector] = [
    pesel.detector,
    nip.detector,
    regon.detector,
    iban.detector,
]

BY_NAME: dict[str, Detector] = {d.name: d for d in CHECKSUM_DETECTORS}
