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

    `fuzzy_pattern` (tylko z `ocr_tolerant=True`): wzorzec-bliźniak `pattern`,
    w którym pozycje cyfrowe (`\\d`) są zastąpione klasą znaków tolerującą
    typowe pomyłki OCR (`ocr_tolerance.FUZZY_DIGIT_CLASS`). Jest potrzebny,
    bo samo podstawienie znaków w `ocr_tolerance.validates_with_ocr_correction`
    działa dopiero NA JUŻ ZNALEZIONYM dopasowaniu - a ściśle cyfrowy `pattern`
    (np. `\\d{11}` dla PESEL) w ogóle nie dopasuje tekstu, w którym OCR
    podstawił literę w miejscu cyfry, więc bez osobnego, "rozmytego" przebiegu
    dopasowania takie przypadki nigdy nie trafiają nawet do walidacji.
    """

    name: str
    pattern: re.Pattern[str]
    validate: Callable[[str], bool] | None
    ocr_tolerant: bool
    fuzzy_pattern: re.Pattern[str] | None

    def __init__(
        self,
        name: str,
        pattern: str | re.Pattern[str],
        validate: Callable[[str], bool] | None = None,
        ocr_tolerant: bool = False,
        fuzzy_pattern: str | re.Pattern[str] | None = None,
    ):
        self.name = name
        self.pattern = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern)
        self.validate = validate
        self.ocr_tolerant = ocr_tolerant
        self.fuzzy_pattern = (
            None
            if fuzzy_pattern is None
            else fuzzy_pattern
            if isinstance(fuzzy_pattern, re.Pattern)
            else re.compile(fuzzy_pattern)
        )

    def find_all(self, text: str) -> list[Match]:
        results: list[Match] = []
        strict_spans: set[tuple[int, int]] = set()
        for m in self.pattern.finditer(text):
            value = m.group("value") if "value" in m.groupdict() else m.group(0)
            span = (m.start(), m.end())
            if self.validate is None or self.validate(value):
                results.append(Match(start=m.start(), end=m.end(), value=value))
                strict_spans.add(span)
                continue
            if self.ocr_tolerant and ocr_tolerance.validates_with_ocr_correction(value, self.validate):
                results.append(Match(start=m.start(), end=m.end(), value=value, score=_OCR_CORRECTED_SCORE))
                strict_spans.add(span)
        if self.ocr_tolerant and self.fuzzy_pattern is not None and self.validate is not None:
            for m in self.fuzzy_pattern.finditer(text):
                span = (m.start(), m.end())
                if span in strict_spans:
                    continue
                value = m.group("value") if "value" in m.groupdict() else m.group(0)
                if ocr_tolerance.validates_with_ocr_correction(value, self.validate):
                    results.append(Match(start=m.start(), end=m.end(), value=value, score=_OCR_CORRECTED_SCORE))
        return results
