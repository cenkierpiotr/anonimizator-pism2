"""Detekcja adresów - hybryda kilku sygnałów o różnej pewności.

spaCy PL nie ma natywnej encji adresu, więc łączymy:
  1. kod pocztowy (`NN-NNN`) + miejscowość - najsilniejsza kotwica (wysoka pewność)
  2. prefiks ulicy (`ul./al./pl./os.`) + nazwa + numer budynku (wysoka pewność)
  3. frazy-kotwice ("zamieszkały w", "z siedzibą w", "legitymujący się"...) -
     kolejny fragment tekstu do najbliższej interpunkcji (średnia pewność,
     łapie adresy bez formalnego prefiksu ulicy, częste w skróconym zapisie)
  4. sam NER LOC potwierdzony gazetteerem miejscowości, bez żadnej kotwicy -
     najniższa pewność (przekazywane z zewnątrz, patrz `merge_with_ner_locations`)

Sąsiadujące dopasowania (np. "ul. Polna 5" tuż przed ", 00-950 Warszawa") są
scalane w jeden span adresu, żeby nie anonimizować kawałków osobno.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.pipeline import gazetteers
from app.pipeline.ner import NerEntity

_STREET_PREFIX = r"(?:ul(?:ica|icy)?|al(?:eja|ei)?|pl(?:ac|acu)?|os(?:iedle|iedlu)?)\.?"
_WORD = r"[A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ.\-]*"
_STREET_NAME = rf"{_WORD}(?:\s+{_WORD})*"
_BUILDING_NO = r"\d+[A-Za-z]?(?:/\d+[A-Za-z]?)?"

_STREET_PATTERN = re.compile(
    rf"(?P<value>{_STREET_PREFIX}\s+{_STREET_NAME}\s+{_BUILDING_NO})"
)

_POSTAL_CODE = r"\d{2}-\d{3}"
_CITY_NAME = r"[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:[\s-][A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)*"
_POSTAL_WITH_CITY_PATTERN = re.compile(rf"(?P<value>{_POSTAL_CODE}\s+{_CITY_NAME})")

_ANCHOR_PHRASE = (
    r"(?:zamieszkał[ay]?|zamieszkując[ay]?|zameldowan[ayi]+|z siedzibą|"
    r"adres(?:em)?(?:\s+zamieszkania|\s+do korespondencji)?|"
    r"legitymując(?:y|a)? się|działając(?:y|a)?\s+w imieniu)\s+w\s+"
)
_ANCHOR_PATTERN = re.compile(
    rf"(?:{_ANCHOR_PHRASE})(?P<value>[A-ZĄĆĘŁŃÓŚŹŻ][^.,;\n]{{2,80}}?)(?=[.,;\n]|$)"
)

# Odstęp między dwoma sąsiadującymi span-ami adresowymi, który wciąż liczy się
# jako "ten sam adres" (np. przecinek + spacja między ulicą a kodem pocztowym).
_GAP_PATTERN = re.compile(r"^[\s,]*$")


@dataclass(frozen=True)
class AddressCandidate:
    start: int
    end: int
    value: str
    confidence: str  # "high" | "medium" | "low"


def _street_candidates(text: str) -> list[AddressCandidate]:
    return [
        AddressCandidate(m.start(), m.end(), m.group("value"), "high")
        for m in _STREET_PATTERN.finditer(text)
    ]


def _postal_candidates(text: str) -> list[AddressCandidate]:
    return [
        AddressCandidate(m.start(), m.end(), m.group("value"), "high")
        for m in _POSTAL_WITH_CITY_PATTERN.finditer(text)
    ]


def _anchor_candidates(text: str) -> list[AddressCandidate]:
    return [
        AddressCandidate(m.start(), m.end(), m.group("value"), "medium")
        for m in _ANCHOR_PATTERN.finditer(text)
    ]


_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def _merge_adjacent(candidates: list[AddressCandidate], text: str) -> list[AddressCandidate]:
    ordered = sorted(candidates, key=lambda c: c.start)
    merged: list[AddressCandidate] = []
    for candidate in ordered:
        if merged and candidate.start <= merged[-1].end:
            # Nakładanie się - scal, biorąc szerszy zasięg i wyższą pewność.
            previous = merged[-1]
            new_end = max(previous.end, candidate.end)
            confidence = previous.confidence if _CONFIDENCE_RANK[previous.confidence] >= _CONFIDENCE_RANK[candidate.confidence] else candidate.confidence
            merged[-1] = AddressCandidate(previous.start, new_end, text[previous.start:new_end], confidence)
            continue

        if merged and _GAP_PATTERN.match(text[merged[-1].end:candidate.start]):
            previous = merged[-1]
            confidence = previous.confidence if _CONFIDENCE_RANK[previous.confidence] >= _CONFIDENCE_RANK[candidate.confidence] else candidate.confidence
            merged[-1] = AddressCandidate(previous.start, candidate.end, text[previous.start:candidate.end], confidence)
            continue

        merged.append(candidate)

    return merged


def find_addresses(text: str, ner_locations: list[NerEntity] | None = None) -> list[AddressCandidate]:
    candidates = _street_candidates(text) + _postal_candidates(text) + _anchor_candidates(text)

    if ner_locations:
        for entity in ner_locations:
            if gazetteers.is_known_city(entity.text):
                candidates.append(AddressCandidate(entity.start, entity.end, entity.text, "low"))

    return _merge_adjacent(candidates, text)
