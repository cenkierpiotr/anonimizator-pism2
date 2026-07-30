"""Przydzielanie etykiet ([Osoba 1], [numer telefonu 2], ...) w ramach pojedynczego
dokumentu. Liczniki i mapowania żyją WYŁĄCZNIE w pamięci procesu na czas
przetwarzania jednego pliku - nigdy nie są zapisywane na dysk (nieodwracalność).

Polityka per kategoria (numerować / usuwać bez numeru / zostawić) pochodzi
z `app.config` - nie jest duplikowana tutaj, żeby `config.py` był jedynym
źródłem prawdy o tym, jak traktowana jest dana kategoria.
"""

from __future__ import annotations

from app.config import AppConfig, CategoryPolicy
from app.pipeline.canonicalize import canonicalize

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


class IdentityRegistry:
    """Rejestr numeracji dla jednego dokumentu. Tworzyć nową instancję per plik."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or AppConfig()
        self._counters: dict[str, int] = {}
        self._assigned: dict[tuple[str, str], int] = {}

    def label_for(self, category: str, value: str) -> str | None:
        policy = self._config.policy_for(category)
        display_name = CATEGORY_LABELS.get(category, category)

        if policy is CategoryPolicy.LEAVE:
            return None
        if policy is CategoryPolicy.NO_NUMBER:
            return f"[{display_name}]"

        canonical_value = canonicalize(category, value)
        key = (category, canonical_value)
        number = self._assigned.get(key)
        if number is None:
            number = self._counters.get(category, 0) + 1
            self._counters[category] = number
            self._assigned[key] = number

        return f"[{display_name} {number}]"
