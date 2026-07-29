"""Detektor dat: format ogólny (`date`) i kontekstowy dla dat urodzenia
(`birth_date_detector`) — patrz sekcja planu "Daty i kwoty" dot. odmiennej
polityki anonimizacji (daty domyślnie zostają, daty urodzenia numerowane).
"""

from __future__ import annotations

from app.detectors.base import Detector

_MONTHS = (
    "stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia"
    "|września|października|listopada|grudnia"
)

_DATE_CORE = (
    rf"(?:\d{{1,2}}[./-]\d{{1,2}}[./-]\d{{4}})"
    rf"|(?:\d{{4}}-\d{{2}}-\d{{2}})"
    rf"|(?:\d{{1,2}}\s+(?:{_MONTHS})\s+\d{{4}}\s*(?:r\.|roku)?)"
)

_DATE_PATTERN = rf"(?P<value>{_DATE_CORE})"
_BIRTH_DATE_PATTERN = (
    rf"(?:urodzon[ay]|ur\.|data urodzenia|urodzony w dniu)\s+(?P<value>{_DATE_CORE})"
)

detector = Detector(name="date", pattern=_DATE_PATTERN)
birth_date_detector = Detector(name="birth_date", pattern=_BIRTH_DATE_PATTERN)
