"""Wspólny interfejs dla wszystkich detektorów regex/checksum."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from app.detectors import ocr_tolerance

# Pewność przypisywana trafieniu, które przeszło walidację checksumem dopiero
# po podstawieniu typowych pomyłek OCR (O/0, l/1/I, S/5, B/8, Z/2) - patrz
# `ocr_tolerance.py`. Celowo niska ("niepewne") - surowy tekst NIE przeszedł
# checksumu wprost, więc trafienie ma trafić do ekranu weryfikacji jako
# "sprawdź ręcznie", a nie zostać po cichu potraktowane jak pewne.
_OCR_CORRECTED_SCORE = 0.4


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    value: str  # dopasowany surowy tekst (bez normalizacji)
    score: float = 1.0


class Detector:
    """Detektor oparty o regex + opcjonalną walidację checksumem.

    `validate` dostaje surowe dopasowanie (grupę 0 lub named group "value")
    i zwraca True/False — pozwala odrzucić np. ciągi cyfr o poprawnym
    kształcie PESEL, ale błędnym checksumie (częste w tekście przypadkowo,
    a NIE chcemy ich anonimizować jako PESEL).

    `ocr_tolerant=True` (tylko dla detektorów z `validate` checksumowym):
    gdy surowe dopasowanie NIE przechodzi walidacji, próbuje podstawień
    typowych pomyłek OCR i ponownie waliduje. Jeśli poprawiona wartość
    przechodzi checksum, dopasowanie jest mimo to zwracane (z surową,
    niepoprawioną wartością tekstu - nie podmieniamy tego, co realnie jest
    w dokumencie), ale z obniżonym `score`, żeby trafiło do ekranu
    weryfikacji jako "niepewne" zamiast zniknąć bez śladu (patrz plan,
    ryzyko "PESEL odczytany przez OCR jako '8O1231O1234' nie przejdzie
    checksumu i cicho nie zostanie zanonimizowany").
    """

    name: str
    pattern: re.Pattern[str]
    validate: Callable[[str], bool] | None
    ocr_tolerant: bool

    def __init__(
        self,
        name: str,
        pattern: str | re.Pattern[str],
        validate: Callable[[str], bool] | None = None,
        ocr_tolerant: bool = False,
    ):
        self.name = name
        self.pattern = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern)
        self.validate = validate
        self.ocr_tolerant = ocr_tolerant

    def find_all(self, text: str) -> list[Match]:
        results: list[Match] = []
        for m in self.pattern.finditer(text):
            value = m.group("value") if "value" in m.groupdict() else m.group(0)
            if self.validate is None or self.validate(value):
                results.append(Match(start=m.start(), end=m.end(), value=value))
                continue
            if self.ocr_tolerant and ocr_tolerance.validates_with_ocr_correction(value, self.validate):
                results.append(Match(start=m.start(), end=m.end(), value=value, score=_OCR_CORRECTED_SCORE))
        return results
