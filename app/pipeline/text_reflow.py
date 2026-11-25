"""Rekonstrukcja akapitów z tekstu wyekstrahowanego z PDF/OCR.

Zarówno `pypdfium2` (`pdf_reader.py`), jak i Tesseract (`ocr.py`) zwracają
tekst z pojedynczym znakiem nowej linii przy KAŻDYM wizualnym złamaniu
wiersza (zawijanie w oryginalnym układzie strony), nie tylko na granicach
faktycznych akapitów - i (sprawdzone empirycznie na obu silnikach) nie dają
żadnego niezawodnego sygnału (np. podwójnego newline) odróżniającego jedno
od drugiego. Bez tej rekonstrukcji jedno zdanie zawinięte na trzech liniach
ekranu trafiało do wyniku jako trzy osobne, urwane w połowie akapity .docx -
to była bezpośrednia przyczyna zgłoszonego błędu "poourywane kawałki".

Heurystyka: linia kończy się realnym końcem akapitu, jeśli kończy się
znakiem interpunkcyjnym kończącym zdanie (`.`, `:`, `;`, `!`, `?`, ewent. w
cudzysłowie/nawiasie) albo jest pusta (prawdziwy pusty wiersz - niektóre
generatory PDF/silniki OCR go jednak wstawiają). W przeciwnym razie kolejna
linia jest tylko kontynuacją zawiniętego wiersza i jest doklejana spacją (z
wyjątkiem słowa rozdzielonego łącznikiem na końcu linii - wtedy łącznik jest
usuwany i słowo sklejane bez spacji). To nie jest rozwiązanie doskonałe
(skrót "ul." czy "Nr." w środku zdania też kończy się kropką), ale to
drastyczna poprawa względem stanu poprzedniego, gdzie KAŻDA linia stawała
się osobnym akapitem bezwarunkowo.
"""

from __future__ import annotations

import re

_HYPHEN_LINE_END = re.compile(r"-\s*$")
_SENTENCE_END = re.compile(r"[.:;!?…”\"'\)\]]\s*$")


def reflow_lines(text: str) -> str:
    """Zwraca tekst z prawdziwymi akapitami rozdzielonymi `\\n\\n` i bez
    pojedynczych `\\n` wewnątrz akapitu (zawinięte linie sklejone spacją)."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = normalized.split("\n")

    paragraphs: list[str] = []
    current = ""

    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line:
            if current:
                paragraphs.append(current)
                current = ""
            continue

        if not current:
            current = line
        elif _HYPHEN_LINE_END.search(current):
            current = _HYPHEN_LINE_END.sub("", current) + line
        else:
            current = current + " " + line

        if _SENTENCE_END.search(line):
            paragraphs.append(current)
            current = ""

    if current:
        paragraphs.append(current)

    return "\n\n".join(paragraphs)
