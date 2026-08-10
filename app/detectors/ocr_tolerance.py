"""Tolerancja na typowe pomyłki OCR w wartościach walidowanych checksumem.

Punkt 8 planu, sekcja "Jakość detekcji i warstwa bezpieczeństwa": Tesseract
regularnie myli wizualnie podobne znaki (litera/cyfra). Bez tego moduły takie
jak PESEL/NIP/IBAN po prostu odrzucają dopasowanie, gdy checksum nie zgadza
się choćby o jeden znak - a to najgorszy scenariusz: człowiek czytający wynik
odczyta numer bez trudu, ale narzędzie cicho nic nie zanonimizuje.

Celowo generujemy tylko kombinacje z OGRANICZONĄ liczbą jednoczesnych
podstawień (`_MAX_SUBSTITUTIONS`) - przy typowej długości identyfikatora
(11-26 znaków) pełny iloczyn kartezjański wszystkich podstawialnych pozycji
rósłby wykładniczo i byłby bezużytecznie wolny, podczas gdy w praktyce OCR
myli pojedynczy, rzadko dwa znaki w jednym identyfikatorze.
"""

from __future__ import annotations

from itertools import combinations
from typing import Callable

# Tylko podstawienia jednoznaczne z punktu widzenia wizualnego podobieństwa w
# obu kierunkach (litera<->cyfra) - nie próbujemy odgadywać całych alfabetów,
# tylko najczęstsze, udokumentowane pomyłki Tesseracta.
_CONFUSABLES: dict[str, tuple[str, ...]] = {
    "O": ("0",), "0": ("O",),
    "I": ("1", "l"), "l": ("1", "I"), "1": ("I", "l"),
    "S": ("5",), "5": ("S",),
    "B": ("8",), "8": ("B",),
    "Z": ("2",), "2": ("Z",),
}

_MAX_SUBSTITUTIONS = 2

# Klasa znaków do budowania "rozmytych" wzorców regex w detektorach z
# `ocr_tolerant=True` - patrz `Detector.fuzzy_pattern` w `base.py`. Bez tego
# regex czysto cyfrowy (np. `\d{11}` dla PESEL) w ogóle nie dopasuje kandydata,
# jeśli OCR podstawił literę w miejscu cyfry (np. "8O1231O1234") - checksum
# tolerancyjny (wyżej w tym module) nigdy nie dostaje szansy zadziałać, bo nie
# ma nawet surowego dopasowania do sprawdzenia.
FUZZY_DIGIT_CLASS = "[0-9OoIiLlSsBbZz]"


def generate_variants(value: str) -> list[str]:
    """Zwraca warianty `value` z podstawionymi znakami-myłkami OCR (bez
    oryginału), ograniczone do co najwyżej `_MAX_SUBSTITUTIONS` jednoczesnych
    podstawień, żeby liczba wariantów zostawała praktycznie liniowa względem
    długości wartości zamiast wykładniczej."""
    positions = [i for i, ch in enumerate(value) if ch in _CONFUSABLES]
    if not positions:
        return []

    variants: set[str] = set()
    max_k = min(_MAX_SUBSTITUTIONS, len(positions))
    for k in range(1, max_k + 1):
        for combo in combinations(positions, k):
            for replacement_set in _replacement_products(value, combo):
                variants.add(replacement_set)
    variants.discard(value)
    return list(variants)


def _replacement_products(value: str, positions: tuple[int, ...]) -> list[str]:
    results = [value]
    for pos in positions:
        next_results = []
        for candidate in results:
            for repl in _CONFUSABLES[value[pos]]:
                next_results.append(candidate[:pos] + repl + candidate[pos + 1 :])
        results = next_results
    return results


def validates_with_ocr_correction(value: str, validate: Callable[[str], bool]) -> bool:
    """True jeśli którykolwiek wariant OCR-poprawiony przechodzi `validate`."""
    return any(validate(variant) for variant in generate_variants(value))
