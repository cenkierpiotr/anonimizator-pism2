"""Przydzielanie etykiet ([Osoba 1], [numer telefonu 2], ...) w ramach pojedynczego
dokumentu. Liczniki i mapowania żyją WYŁĄCZNIE w pamięci procesu na czas
przetwarzania jednego pliku - nigdy nie są zapisywane na dysk (nieodwracalność).

Polityka per kategoria (numerować / usuwać bez numeru / zostawić) pochodzi
z `app.config` - nie jest duplikowana tutaj, żeby `config.py` był jedynym
źródłem prawdy o tym, jak traktowana jest dana kategoria.
"""

from __future__ import annotations

import hashlib
import hmac
import random
import secrets
from typing import Protocol

from app.config import AppConfig, CategoryPolicy
from app.pipeline import date_shift
from app.pipeline.canonicalize import canonicalize

# Zakres losowanego przesunięcia dat w wielokrotnościach 7 dni (konwencja
# PhysioNet/de-identyfikacji medycznej - zachowuje też dzień tygodnia, patrz
# `DateShiftOperator` niżej). 52 * 7 ≈ 364, czyli praktycznie ten sam zakres
# co poprzednio (+/-365 dni), tylko skwantowany do pełnych tygodni.
_DATE_SHIFT_RANGE_WEEKS = 52

CATEGORY_LABELS: dict[str, str] = {
    "phone": "numer telefonu",
    "email": "adres e-mail",
    "address": "adres",
    "pesel": "PESEL",
    "nip": "NIP",
    "regon": "REGON",
    "krs": "KRS",
    "land_register": "numer księgi wieczystej",
    "iban": "numer rachunku",
    "id_card": "dowód osobisty",
    "passport": "paszport",
    "vehicle_vin": "VIN",
    "vehicle_plate": "numer rejestracyjny",
    "npwz": "NPWZ",
    "case_number": "sygnatura akt",
    "notarial_act": "akt notarialny",
    "usc_act": "akt stanu cywilnego",
    "poswiadczenie_dziedziczenia": "poświadczenie dziedziczenia",
    "rejestr_spadkowy": "wpis w Rejestrze Spadkowym",
    "legal_role_person": "Osoba",
    "institution": "instytucja",
    "ip_address": "adres IP",
    "imei": "IMEI",
    "url": "adres URL",
    "birth_date": "data urodzenia",
    "amount": "kwota",
}


class Operator(Protocol):
    """Interfejs operatora Presidio-style: rozdziela "co wykryto" (kategoria +
    wartość) od "co z tym zrobić" (etykieta / usunięcie / pozostawienie).
    Wybór konkretnego operatora dla danej kategorii należy do `IdentityRegistry`
    (patrz `_OPERATORS_BY_POLICY` i `apply_operator` niżej) - żaden detektor
    ani `detect_all.py` nie decyduje o tym samodzielnie."""

    def apply(self, registry: "IdentityRegistry", category: str, value: str) -> str | None:
        """Zwraca tekst zastępczy, albo `None` gdy wartość ma zostać nietknięta."""
        ...


class LeaveOperator:
    def apply(self, registry: "IdentityRegistry", category: str, value: str) -> str | None:
        return None


class NoNumberOperator:
    def apply(self, registry: "IdentityRegistry", category: str, value: str) -> str | None:
        display_name = CATEGORY_LABELS.get(category, category)
        return f"[{display_name}]"


class NumberOperator:
    def apply(self, registry: "IdentityRegistry", category: str, value: str) -> str | None:
        display_name = CATEGORY_LABELS.get(category, category)
        number = registry._number_for(category, value)
        return f"[{display_name} {number}]"


class DateShiftOperator:
    """Tryb "date shifting" (patrz `date_shift.py`) - zamiast usuwać/numerować
    datę, przesuwa ją o stały, losowy dla dokumentu offset. Jeśli wartość nie
    da się sparsować jako data, zwraca ją nietkniętą (bezpieczny fallback)."""

    def apply(self, registry: "IdentityRegistry", category: str, value: str) -> str | None:
        shifted = date_shift.shift_date_string(value, registry.date_shift_offset_days)
        return shifted if shifted != value else None


_OPERATORS_BY_POLICY: dict[CategoryPolicy, Operator] = {
    CategoryPolicy.LEAVE: LeaveOperator(),
    CategoryPolicy.NO_NUMBER: NoNumberOperator(),
    CategoryPolicy.NUMBER: NumberOperator(),
}


class IdentityRegistry:
    """Rejestr numeracji dla jednego dokumentu. Tworzyć nową instancję per plik."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or AppConfig()
        self._counters: dict[str, int] = {}
        self._assigned: dict[str, int] = {}
        # Sól per-dokument, wyłącznie w pamięci procesu, nigdy nie zapisywana -
        # klucze rejestru to HMAC(sól, kategoria:wartość_kanoniczna), nie
        # surowa wartość kanoniczna wprost. Nie zmienia gwarancji nieodwracalności
        # (etykiety i tak żyją tylko w pamięci), ale chroni przed odczytaniem
        # wartości wprost ze zrzutu pamięci/crash dumpa.
        self._salt: bytes = secrets.token_bytes(32)
        # Jeden losowy offset per dokument (nie per data), skwantowany do
        # wielokrotności 7 dni (konwencja PhysioNet - zachowuje dzień tygodnia)
        # - zachowuje odstępy między zdarzeniami w piśmie, patrz plan sekcja
        # "Daty i kwoty".
        self.date_shift_offset_days: int = (
            random.randint(-_DATE_SHIFT_RANGE_WEEKS, _DATE_SHIFT_RANGE_WEEKS) * 7
            if self._config.date_shifting_enabled
            else 0
        )

    @property
    def date_shifting_enabled(self) -> bool:
        return self._config.date_shifting_enabled

    def _hashed_key(self, category: str, canonical_value: str) -> str:
        message = f"{category}:{canonical_value}".encode("utf-8")
        return hmac.new(self._salt, message, hashlib.sha256).hexdigest()

    def _number_for(self, category: str, value: str) -> int:
        canonical_value = canonicalize(category, value)
        key = self._hashed_key(category, canonical_value)
        number = self._assigned.get(key)
        if number is None:
            number = self._counters.get(category, 0) + 1
            self._counters[category] = number
            self._assigned[key] = number
        return number

    def apply_operator(self, category: str, value: str) -> str | None:
        """Punkt wejścia używany przez `detect_all.py`: wybiera operator wg
        polityki kategorii, z wyjątkiem `date` w trybie date-shifting, gdzie
        `DateShiftOperator` ma pierwszeństwo przed zwykłą polityką LEAVE."""
        if category == "date" and self.date_shifting_enabled:
            return DateShiftOperator().apply(self, category, value)
        policy = self._config.policy_for(category)
        operator = _OPERATORS_BY_POLICY[policy]
        return operator.apply(self, category, value)

    def label_for(self, category: str, value: str) -> str | None:
        """Zachowane dla zgodności wstecznej (testy/kod wywołujący bezpośrednio
        etykietowanie bez trybu date-shifting) - deleguje do `apply_operator`
        pomijając specjalny przypadek daty, o którym ta metoda nic nie wie."""
        policy = self._config.policy_for(category)
        return _OPERATORS_BY_POLICY[policy].apply(self, category, value)
