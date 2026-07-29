"""Wspólny interfejs dla wszystkich detektorów regex/checksum."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    value: str  # dopasowany surowy tekst (bez normalizacji)


class Detector:
    """Detektor oparty o regex + opcjonalną walidację checksumem.

    `validate` dostaje surowe dopasowanie (grupę 0 lub named group "value")
    i zwraca True/False — pozwala odrzucić np. ciągi cyfr o poprawnym
    kształcie PESEL, ale błędnym checksumie (częste w tekście przypadkowo,
    a NIE chcemy ich anonimizować jako PESEL).
    """

    name: str
    pattern: re.Pattern[str]
    validate: Callable[[str], bool] | None

    def __init__(self, name: str, pattern: str | re.Pattern[str], validate: Callable[[str], bool] | None = None):
        self.name = name
        self.pattern = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern)
        self.validate = validate

    def find_all(self, text: str) -> list[Match]:
        results: list[Match] = []
        for m in self.pattern.finditer(text):
            value = m.group("value") if "value" in m.groupdict() else m.group(0)
            if self.validate is not None and not self.validate(value):
                continue
            results.append(Match(start=m.start(), end=m.end(), value=value))
        return results
