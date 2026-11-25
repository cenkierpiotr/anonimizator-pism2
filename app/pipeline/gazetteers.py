"""Ładowanie gazetteerów (imiona/nazwiska/miejscowości) z resources/gazetteers.

Nazwiska NIE są samodzielnym sygnałem (pokrywają się ze słownikiem pospolitym:
Kowal, Kot, Wilk...) - liczą się dopiero w połączeniu z drugim sygnałem
(wielka litera nie na początku zdania + sąsiedztwo imienia/tytułu/roli),
sprawdzanym przez wywołującego (np. `legal_roles.py`/`ner.py`), nie tutaj.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_RESOURCES_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "gazetteers"


@lru_cache(maxsize=None)
def _load_set(filename: str) -> frozenset[str]:
    path = _RESOURCES_DIR / filename
    with path.open(encoding="utf-8") as f:
        return frozenset(line.strip().casefold() for line in f if line.strip())


def first_names() -> frozenset[str]:
    return _load_set("imiona_pl.txt")


def surnames() -> frozenset[str]:
    return _load_set("nazwiska_pl.txt")


def cities() -> frozenset[str]:
    return _load_set("cities_pl.txt")


def is_known_first_name(token: str) -> bool:
    return token.casefold() in first_names()


def is_known_surname(token: str) -> bool:
    return token.casefold() in surnames()


def is_known_city(token: str) -> bool:
    return token.casefold() in cities()
