"""Przydzielanie etykiet ([Osoba 1], [numer telefonu 2], ...) w ramach pojedynczego
dokumentu. Liczniki i mapowania żyją WYŁĄCZNIE w pamięci procesu na czas
przetwarzania jednego pliku - nigdy nie są zapisywane na dysk (nieodwracalność).
"""

from __future__ import annotations

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
    "legal_role_person": "Osoba",
    "institution": "instytucja",
    "ip_address": "adres IP",
    "imei": "IMEI",
    "url": "adres URL",
    "birth_date": "data urodzenia",
}

# Kategorie usuwane bez numeru (ta sama etykieta dla wszystkich wystąpień).
NO_NUMBER_LABELS: dict[str, str] = {
    "amount": "[kwota]",
}

# Kategorie domyślnie pozostawiane w tekście bez żadnej zmiany.
LEAVE_CATEGORIES: frozenset[str] = frozenset({"date"})


class IdentityRegistry:
    """Rejestr numeracji dla jednego dokumentu. Tworzyć nową instancję per plik."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._assigned: dict[tuple[str, str], int] = {}

    def label_for(self, category: str, value: str) -> str | None:
        if category in LEAVE_CATEGORIES:
            return None
        if category in NO_NUMBER_LABELS:
            return NO_NUMBER_LABELS[category]

        canonical_value = canonicalize(category, value)
        key = (category, canonical_value)
        number = self._assigned.get(key)
        if number is None:
            number = self._counters.get(category, 0) + 1
            self._counters[category] = number
            self._assigned[key] = number

        display_name = CATEGORY_LABELS.get(category, category)
        return f"[{display_name} {number}]"
