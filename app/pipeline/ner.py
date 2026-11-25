"""Wrapper na spaCy NER dla polskich modeli (`pl_core_news_*`).

Modele NKJP-owe (`pl_core_news_sm/md/lg`) używają własnego zestawu etykiet
(`persName`, `orgName`, `placeName`, `geogName`, ...), nie standardowego
`PERSON/ORG/LOC` ze schematu OntoNotes - `_LABEL_MAP` tłumaczy je na wspólny
zestaw kategorii używany w reszcie pipeline'u.

Żaden model NER nie daje 100% skuteczności - to tylko JEDNA z kilku warstw
detekcji (patrz `legal_roles.py`, drugi przebieg literalny w warstwie wyższej).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import spacy
from spacy.language import Language

_LABEL_MAP: dict[str, str] = {
    "persName": "PERSON",
    "orgName": "ORG",
    "placeName": "LOC",
    "geogName": "LOC",
    # Schemat OntoNotes (na wypadek użycia modelu spoza rodziny pl_core_news,
    # np. w testach z modelem angielskim) mapowany 1:1.
    "PERSON": "PERSON",
    "ORG": "ORG",
    "LOC": "LOC",
    "GPE": "LOC",
}

DEFAULT_MODEL = "pl_core_news_md"


@dataclass(frozen=True)
class NerEntity:
    start: int
    end: int
    text: str
    label: str  # "PERSON" | "ORG" | "LOC"


@lru_cache(maxsize=4)
def load_nlp(model_name: str = DEFAULT_MODEL) -> Language:
    return spacy.load(model_name, exclude=["parser"])


def find_entities(text: str, nlp: Language | None = None) -> list[NerEntity]:
    if nlp is None:
        nlp = load_nlp()

    doc = nlp(text)
    entities: list[NerEntity] = []
    for ent in doc.ents:
        label = _LABEL_MAP.get(ent.label_)
        if label is None:
            continue
        entities.append(NerEntity(start=ent.start_char, end=ent.end_char, text=ent.text, label=label))
    return entities
