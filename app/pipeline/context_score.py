"""Wzmocnienie kontekstowe pewności trafienia (Presidio: `ContextAwareEnhancer`).

Punkt 3 planu: dla każdej kategorii definiujemy listę słów-wyzwalaczy, których
obecność w oknie N tokenów wokół dopasowania podnosi pewność trafienia. W tym
projekcie używane głównie do rozstrzygania trafień OCR-poprawionych (patrz
`app/detectors/ocr_tolerance.py`) - startują z niskim, "niepewnym" score
(0.4) i dopiero sąsiedztwo słowa-wyzwalacza podnosi je do poziomu, przy
którym warto pokazać je użytkownikowi jako "prawdopodobnie poprawne", a nie
tylko "sprawdź ręcznie".
"""

from __future__ import annotations

import re

_WINDOW_CHARS = 40  # przybliżenie okna +/-5 tokenów bez potrzeby tokenizacji
_BOOSTED_SCORE = 0.85

_WORD_RE = re.compile(r"\w+", re.UNICODE)

TRIGGER_WORDS: dict[str, tuple[str, ...]] = {
    "pesel": ("pesel", "ur.", "urodzony", "urodzona", "zamieszkały", "zamieszkała"),
    "nip": ("nip", "podatnik", "vat"),
    "regon": ("regon",),
    "iban": ("iban", "rachunek", "konto", "przelew", "nr rachunku"),
    "land_register": ("kw", "księga wieczysta", "nr księgi"),
    "id_card": ("dowód", "dowodu", "seria i numer", "legitymujący"),
    "passport": ("paszport", "paszportu"),
    "vehicle_vin": ("vin", "nadwozia", "pojazd"),
    "vehicle_plate": ("rej.", "rejestracyjny", "tablica"),
}


def _tokenize_positions(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _WORD_RE.finditer(text)]


def context_boost(text: str, start: int, end: int, category: str, base_score: float) -> float:
    """Podnosi `base_score` do `_BOOSTED_SCORE`, jeśli w oknie znaków wokół
    [start, end) znajdzie się jedno ze słów-wyzwalaczy kategorii. Nie obniża
    nigdy score poniżej wejściowego - brak wyzwalacza to brak zmiany, nie kara."""
    triggers = TRIGGER_WORDS.get(category)
    if not triggers:
        return base_score

    window_start = max(0, start - _WINDOW_CHARS)
    window_end = min(len(text), end + _WINDOW_CHARS)
    context = text[window_start:window_end].casefold()

    if any(trigger in context for trigger in triggers):
        return max(base_score, _BOOSTED_SCORE)
    return base_score
