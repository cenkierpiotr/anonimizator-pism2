"""Awaryjna warstwa: para sąsiednich tokenów pisanych wielką literą, gdzie
jeden jest znanym imieniem a drugi znanym nazwiskiem z `app.pipeline.gazetteers`
(w dowolnej kolejności - "Jan Kowalski" i "Kowalski Jan" oba występują w
realnych pismach, np. w tabelach/formularzach).

Uzupełnia `app/detectors/legal_roles.py` (wymaga tytułu/roli przed imieniem)
i `app/pipeline/ner.py` (statystyczny model spaCy) - oba mogą NIE rozpoznać
nazwiska w bardzo krótkim, pozbawionym kontekstu zdaniowego tekście (np.
nagłówek skanu OCR "Wniosek - Jan Kowalski" albo wartość komórki tabeli
"Jan Kowalski" bez żadnego otaczającego zdania). Zweryfikowane testem e2e na
syntetycznym skanie OCR: dla tekstu "Wniosek - Gilliane Johansson PESEL: ..."
spaCy (`pl_core_news_md`) zwróciło ZERO encji PERSON, mimo że oba tokeny są
w gazetteer - imię/nazwisko wyciekło w całości do wyniku.

Ten moduł to właśnie "wywołujący" opisany w docstringu
`gazetteers.py` ("nazwiska NIE są samodzielnym sygnałem... liczą się dopiero
w połączeniu z drugim sygnałem, sprawdzanym przez wywołującego (np.
legal_roles.py/ner.py)") - do tej pory żaden faktyczny kod tego nie robił,
mimo że `is_known_first_name`/`is_known_surname` już istniały.

Celowo używany w `detect_all.py` TYLKO gdy warstwa NER nie znalazła w danym
bloku tekstu ANI JEDNEJ osoby (patrz `_PRIORITY_GAZETTEER_NAME_FALLBACK`) -
na zwykłym tekście z choć jednym rozpoznanym PERSON ta warstwa się nie
uruchamia, żeby nie mnożyć fałszywych alarmów na dokumentach, gdzie NER i tak
działa poprawnie (duże listy - 36k imion, 286k nazwisk - część nazwisk
pokrywa się ze słownikiem pospolitym). Niski `score` (jak korekta OCR) - trafia
do ekranu weryfikacji jako "sprawdź ręcznie" zamiast być cicho pominięte."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.pipeline import gazetteers

_PATTERN = re.compile(
    r"(?P<a>[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)\s+(?P<b>[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)"
)

GAZETTEER_SCORE = 0.5


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    value: str
    score: float = GAZETTEER_SCORE


def find_all(text: str) -> list[Match]:
    results: list[Match] = []
    for m in _PATTERN.finditer(text):
        a, b = m.group("a"), m.group("b")
        first_last = gazetteers.is_known_first_name(a) and gazetteers.is_known_surname(b)
        last_first = gazetteers.is_known_surname(a) and gazetteers.is_known_first_name(b)
        if not (first_last or last_first):
            continue
        results.append(Match(start=m.start(), end=m.end(), value=m.group(0)))
    return results
