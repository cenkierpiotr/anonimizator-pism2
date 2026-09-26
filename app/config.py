"""Konfiguracja aplikacji: polityki anonimizacji per kategoria + ustawienia OCR/NER.

Polityki (patrz plan, sekcja "Daty i kwoty..."): numerowanie ma sens tam, gdzie
identyczność wartości oznacza identyczność obiektu (osoba/adres/telefon/PESEL/...).
Daty i kwoty łamią to założenie, więc mają osobną, domyślnie nie-numerowaną
politykę - `identity_cluster.py` czyta te ustawienia stąd, nie duplikuje logiki.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


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
    "poswiadczenie_dziedziczenia": CategoryPolicy.NUMBER,
    "rejestr_spadkowy": CategoryPolicy.NUMBER,
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


def _default_gliner_model_path() -> str:
    """Domyślna ścieżka pliku modelu ONNX GLiNER w katalogu danych aplikacji -
    ta sama konwencja co `legacy_convert._cache_root` dla LibreOffice
    (`%LOCALAPPDATA%\\AnonimizatorPism\\...` na Windows,
    `~/.cache/AnonimizatorPism/...` na Linuksie w dev/CI). Plik pod tą ścieżką
    NIE jest częścią repo/instalatora - jest pobierany "na żądanie" przez
    `gliner_layer.download_gliner_model()` (patrz GUI: przycisk "Pobierz model
    GLiNER"), analogicznie do mechanizmu LibreOffice w `LibreOfficeConfig`.
    Dzięki temu domyślna wartość nie jest zahardkodowaną ścieżką specyficzną
    dla jednej maszyny deweloperskiej."""
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        # Ścieżka używana tylko w dev/CI na Linuksie - na Windows zawsze LOCALAPPDATA.
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return str(Path(base) / "AnonimizatorPism" / "gliner" / "model_quantized.onnx")


@dataclass
class GlinerConfig:
    """Ustawienia opcjonalnej warstwy GLiNER (zero-shot NER) - patrz
    `app/pipeline/gliner_layer.py` i plan
    `.claude/plans/encapsulated-splashing-panda.md`. Aktywna tylko gdy
    `AppConfig.gliner_enabled` jest `True` (domyślnie WŁĄCZONE od Fazy 5).

    `model_path` wskazuje domyślnie na katalog danych aplikacji
    (`_default_gliner_model_path()`) - plik modelu (eksport ONNX, wariant
    `anonPL-300M`: mniejszy/szybszy, wybrany bo aplikacja jest desktopowa i
    czas ładowania/inferencji ma znaczenie) jest pobierany "na żądanie" przez
    `gliner_layer.download_gliner_model()`, analogicznie do mechanizmu
    LibreOffice (`LibreOfficeConfig` + `legacy_convert.download_libreoffice`)
    - URL do archiwum ZIP na GitHub Releases tego repo + weryfikacja SHA-256.
    Jeśli plik pod tą ścieżką nie istnieje (świeża instalacja, model jeszcze
    nie pobrany), `gliner_layer.load_model` zgłasza czytelny
    `GlinerUnavailableError` zamiast crashować aplikację - ścieżka jest w
    pełni konfigurowalna, żeby dało się wskazać inny eksport (np.
    `anonPL-494M`) bez zmiany kodu."""

    model_path: str = field(default_factory=_default_gliner_model_path)
    # Archiwum ZIP z eksportem ONNX (plik modelu + config.json/tokenizer -
    # `GLiNER.from_pretrained` wymaga całego katalogu, nie tylko samego
    # .onnx) hostowane w GitHub Releases TEGO SAMEGO repo, wzorem
    # `LibreOfficeConfig.release_url`.
    release_url: str = (
        "https://github.com/cenkierpiotr/anonimizator-pism/releases/"
        "download/gliner-anonpl-300m-onnx-v1/anonPL-300M-onnx.zip"
    )
    # Placeholder - MUSI zostać podmieniony na realny SHA-256 artefaktu przed
    # pierwszym wydaniem, inaczej download_gliner_model() odmówi weryfikacji
    # (patrz LibreOfficeConfig.release_sha256 - identyczny wzorzec/TODO).
    release_sha256: str = ""
    # Próg pewności predykcji [0, 1] - trafienia poniżej progu są odrzucane
    # przed dopisaniem do uncertain_collector (patrz detect_all.detect_in_text).
    confidence_threshold: float = 0.5


@dataclass
class LibreOfficeConfig:
    """Ustawienia pobierania LibreOffice "na żądanie" (obsługa .doc, patrz plan
    sekcja "Pobieranie LibreOffice na żądanie"). URL/checksum wskazują na
    artefakt hostowany we własnym repo GitHub Releases - do wypełnienia po
    zbudowaniu i opublikowaniu portable LibreOffice dla Windows (Faza 4)."""

    release_url: str = (
        "https://github.com/cenkierpiotr/anonimizator-pism/releases/"
        "download/libreoffice-portable-v1/libreoffice-portable-win64.zip"
    )
    # Placeholder - MUSI zostać podmieniony na realny SHA-256 artefaktu przed
    # pierwszym wydaniem, inaczej download_libreoffice() odmówi weryfikacji.
    release_sha256: str = ""


@dataclass
class AppConfig:
    category_policies: dict[str, CategoryPolicy] = field(
        default_factory=lambda: dict(DEFAULT_CATEGORY_POLICIES)
    )
    ocr: OcrConfig = field(default_factory=OcrConfig)
    ner: NerConfig = field(default_factory=NerConfig)
    libreoffice: LibreOfficeConfig = field(default_factory=LibreOfficeConfig)
    gliner: GlinerConfig = field(default_factory=GlinerConfig)
    # Tryb "date shifting": przesunięcie wszystkich dat o ten sam losowy
    # offset zamiast zostawiania/usuwania - patrz sekcja "Daty i kwoty" w planie.
    date_shifting_enabled: bool = False
    # Feature flag GLiNER (patrz app/pipeline/gliner_layer.py) - domyślnie
    # WŁĄCZONE od Fazy 5 (23.09.2026): ewaluacja na 40 dok. wykazała +69,6pp
    # recall na Grupie B (identyfikatory) przy zaszumionym OCR, 0/8 naruszeń
    # zasady bezpieczeństwa w teście rollout (patrz
    # gliner-anonimizator-pl-finetune/results/gliner_recall_eval.md). Trafienia
    # GLiNER NIGDY nie trafiają bezpośrednio do resolve()/Replacement -
    # wyłącznie do uncertain_collector z prefiksem "[GLiNER]", zawsze do
    # ręcznej weryfikacji w ReviewWindow. Jeśli plik modelu ONNX pod
    # `GlinerConfig.model_path` nie istnieje (np. świeża instalacja, model
    # jeszcze nie pobrany przyciskiem "Pobierz model GLiNER" - patrz
    # `gliner_layer.download_gliner_model()`, albo pakiet `gliner` nie jest
    # zainstalowany) - `GlinerUnavailableError` jest łapany w app/main.py i
    # zamieniany na ostrzeżenie, NIE crash.
    gliner_enabled: bool = True

    def policy_for(self, category: str) -> CategoryPolicy:
        return self.category_policies.get(category, CategoryPolicy.NUMBER)
