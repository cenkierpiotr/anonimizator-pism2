"""Kanonikalizacja wartości przed przydzieleniem numeru w ramach kategorii.

Bez tego "+48 601 234 567" i "601-234-567" dostałyby dwa różne numery mimo
że to ten sam telefon - a to psuje sens numeracji (czytelnik ma widzieć
"to ciągle ten sam obiekt").
"""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_NON_DIGITS = re.compile(r"\D+")
_NON_ALNUM = re.compile(r"[^0-9A-Za-z]+")

# Końcówki polskiej fleksji dla imion i nazwisk, posortowane od najdłuższej -
# żeby np. "kowalskiego" trafiło w "skiego", a nie przedwcześnie w krótsze "ego".
# Bez tego dwa niezależne wykrycia NER tej samej osoby w różnych przypadkach
# (np. celownik "Annie Nowak" vs mianownik "Anna Nowak") dostawały różne klucze
# kanoniczne i różne numery [Osoba N] - odkryte i zgłoszone podczas projektowania
# testów interfejsu. Celowo uproszczone (prawdziwa polska fleksja ma liczne
# wyjątki, np. zmiękczenia "Piotr" -> "Piotrze") - tania warstwa podnosząca
# spójność klastrowania, nie próba pełnej poprawności językoznawczej (ten sam
# kompromis co `app/detectors/inflect.py`).
_NAME_CASE_SUFFIXES = tuple(
    sorted(
        {
            "skiego", "skiemu", "skimi", "skich", "skiej", "ska", "ski", "skim",
            "ckiego", "ckiemu", "ckimi", "ckich", "ckiej", "cka", "cki", "ckim",
            "owi", "ego", "emu", "ie", "em", "om", "y", "a", "e",
        },
        key=len,
        reverse=True,
    )
)


def _stem_name_token(token: str) -> str:
    for suffix in _NAME_CASE_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def _strip_diacritics(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _canonical_phone(value: str) -> str:
    digits = _NON_DIGITS.sub("", value)
    # Ujednolicenie prefiksu kraju: +48/0048/48 -> zostaje 9 cyfr lokalnych,
    # bo to one identyfikują numer, nie zapis prefiksu.
    if digits.startswith("0048"):
        digits = digits[4:]
    elif digits.startswith("48") and len(digits) == 11:
        digits = digits[2:]
    return digits


def _canonical_email(value: str) -> str:
    return value.strip().lower()


def _canonical_digits_only(value: str) -> str:
    return _NON_DIGITS.sub("", value)


def _canonical_alnum_upper(value: str) -> str:
    return _NON_ALNUM.sub("", value).upper()


def _canonical_person(value: str) -> str:
    collapsed = _WHITESPACE.sub(" ", value).strip()
    normalized = _strip_diacritics(collapsed).casefold()
    return " ".join(_stem_name_token(token) for token in normalized.split(" "))


def _canonical_default(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip().casefold()


_CANONICALIZERS = {
    "phone": _canonical_phone,
    "email": _canonical_email,
    "pesel": _canonical_digits_only,
    "nip": _canonical_digits_only,
    "regon": _canonical_digits_only,
    "iban": _canonical_alnum_upper,
    "land_register": _canonical_alnum_upper,
    "id_card": _canonical_alnum_upper,
    "passport": _canonical_alnum_upper,
    "vehicle_vin": _canonical_alnum_upper,
    "vehicle_plate": _canonical_alnum_upper,
    "case_number": _canonical_alnum_upper,
    "krs": _canonical_digits_only,
    "npwz": _canonical_digits_only,
    "notarial_act": _canonical_alnum_upper,
    "usc_act": _canonical_alnum_upper,
    "legal_role_person": _canonical_person,
    "ip_address": _canonical_default,
    "imei": _canonical_digits_only,
    "url": _canonical_default,
}


def canonicalize(category: str, value: str) -> str:
    canonicalizer = _CANONICALIZERS.get(category, _canonical_default)
    return canonicalizer(value)
