"""Numer KRS: 10 cyfr, zwykle poprzedzony "KRS". Brak oficjalnego checksumu
(w odróżnieniu od PESEL/NIP/REGON) — precyzję podnosi wymóg kontekstu "KRS"
w sąsiedztwie, więc nie jest w CHECKSUM_DETECTORS (nie nadaje się do leak-check
bez kontekstu, żeby nie dawać fałszywych alarmów na dowolne 10 cyfr)."""

from __future__ import annotations

import re

from app.detectors.base import Detector

_PATTERN = re.compile(r"\bKRS[:\s]*?(?P<value>\d{10})\b", re.IGNORECASE)

detector = Detector(name="krs", pattern=_PATTERN)
