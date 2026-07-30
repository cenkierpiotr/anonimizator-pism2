"""Konfiguracja aplikacji: polityki anonimizacji per kategoria + ustawienia OCR/NER.

Polityki (patrz plan, sekcja "Daty i kwoty..."): numerowanie ma sens tam, gdzie
identyczność wartości oznacza identyczność obiektu (osoba/adres/telefon/PESEL/...).
Daty i kwoty łamią to założenie, więc mają osobną, domyślnie nie-numerowaną
politykę - `identity_cluster.py` czyta te ustawienia stąd, nie duplikuje logiki.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CategoryPolicy(str, Enum):
    NUMBER = "usun_i_numeruj"
    NO_NUMBER = "usun_bez_numeru"
    LEAVE = "zostaw"


DEFAULT_CATEGORY_POLICIES: dict[str, CategoryPolicy] = {
    "phone": CategoryPolicy.NUMBER,
    "email": CategoryPolicy.NUMBER,
    "address": CategoryPolicy.NUMBER,
    "pesel": CategoryPolicy.NUMBER,
    "nip": CategoryPolicy.NUMBER,
    "regon": CategoryPolicy.NUMBER,
    "krs": CategoryPolicy.NUMBER,
    "land_register": CategoryPolicy.NUMBER,
    "iban": CategoryPolicy.NUMBER,
    "id_card": CategoryPolicy.NUMBER,
    "passport": CategoryPolicy.NUMBER,
    "vehicle_vin": CategoryPolicy.NUMBER,
    "vehicle_plate": CategoryPolicy.NUMBER,
    "npwz": CategoryPolicy.NUMBER,
    "case_number": CategoryPolicy.NUMBER,
    "notarial_act": CategoryPolicy.NUMBER,
    "usc_act": CategoryPolicy.NUMBER,
    "legal_role_person": CategoryPolicy.NUMBER,
    "institution": CategoryPolicy.NUMBER,
    "ip_address": CategoryPolicy.NUMBER,
    "imei": CategoryPolicy.NUMBER,
    "url": CategoryPolicy.NUMBER,
    "birth_date": CategoryPolicy.NUMBER,
    # Wyjątki - patrz uzasadnienie w module docstring i w planie.
    "date": CategoryPolicy.LEAVE,
    "amount": CategoryPolicy.NO_NUMBER,
}


@dataclass
class OcrConfig:
    languages: str = "pol+eng"
    dpi: int = 300
    low_confidence_threshold: float = 60.0


@dataclass
class NerConfig:
    model_name: str = "pl_core_news_md"


@dataclass
class AppConfig:
    category_policies: dict[str, CategoryPolicy] = field(
        default_factory=lambda: dict(DEFAULT_CATEGORY_POLICIES)
    )
    ocr: OcrConfig = field(default_factory=OcrConfig)
    ner: NerConfig = field(default_factory=NerConfig)
    # Tryb "date shifting": przesunięcie wszystkich dat o ten sam losowy
    # offset zamiast zostawiania/usuwania - patrz sekcja "Daty i kwoty" w planie.
    date_shifting_enabled: bool = False

    def policy_for(self, category: str) -> CategoryPolicy:
        return self.category_policies.get(category, CategoryPolicy.NUMBER)
