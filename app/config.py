"""Konfiguracja aplikacji: polityki anonimizacji per kategoria + ustawienia OCR/NER.

Polityki (patrz plan, sekcja "Daty i kwoty..."): numerowanie ma sens tam, gdzie
identyczność wartości oznacza identyczność obiektu (osoba/adres/telefon/PESEL/...).
Daty i kwoty łamią to założenie, więc mają osobną, domyślnie nie-numerowaną
politykę - `identity_cluster.py` czyta te ustawienia stąd, nie duplikuje logiki.
"""

from __future__ import annotations

import os
import platform
import sys
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
    """Domyślna ścieżka pliku modelu ONNX GLiNER.

    W zbudowanej aplikacji (`sys.frozen`, patrz PyInstaller) model jest teraz
    vendorowany w BUILD-TIME (CI pobiera authenticated `gh release download` z
    prywatnego repo do `build/vendor/gliner_model/`, `build/anonimizator.spec`
    podłącza ten katalog jako dane), więc domyślna ścieżka wskazuje na
    podkatalog `gliner_model/` obok głównego .exe - analogicznie do
    `ocr._configure_bundled_tesseract()` dla Tesseracta.

    W dev/CI (nie zbudowany .exe) wraca do starej konwencji katalogu danych
    aplikacji (`%LOCALAPPDATA%\\AnonimizatorPism\\...` na Windows,
    `~/.cache/AnonimizatorPism/...` na Linuksie) - tam plik nie jest częścią
    repo i trzeba go dograć ręcznie albo przez opcjonalny fallback
    `gliner_layer.download_gliner_model()` (patrz GUI: przycisk "Pobierz model
    GLiNER"), analogicznie do mechanizmu LibreOffice w `LibreOfficeConfig`."""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).parent / "gliner_model" / "model_quantized.onnx")

    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        # Ścieżka używana tylko w dev/CI na Linuksie - na Windows zawsze LOCALAPPDATA.
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return str(Path(base) / "AnonimizatorPism" / "gliner" / "model_quantized.onnx")


@dataclass
class GlinerConfig:
    """Ustawienia opcjonalnej warstwy GLiNER (zero-shot NER) - patrz
    `app/pipeline/gliner_layer.py`. Aktywna tylko gdy
    `AppConfig.gliner_enabled` jest `True` (domyślnie WŁĄCZONE od Fazy 5).

    `model_path` wskazuje domyślnie (`_default_gliner_model_path()`) na
    katalog vendorowany w BUILD-TIME obok głównego .exe (`sys.frozen` ==
    True) - plik modelu (eksport ONNX, wariant `anonPL-300M`: mniejszy/
    szybszy, wybrany bo aplikacja jest desktopowa i czas ładowania/inferencji
    ma znaczenie) jest teraz PRIMARY pobierany authenticated `gh release
    download` w CI (patrz `.github/workflows/build-windows.yml`) i
    zbundlowany do instalatora - bo anonimowy `urllib`/`curl` na
    `browser_download_url` prywatnego repo zwraca 404, więc runtime
    download-on-demand nie działał dla realnego użytkownika końcowego.

    `gliner_layer.download_gliner_model()` (URL do archiwum ZIP na GitHub
    Releases tego repo + weryfikacja SHA-256, analogicznie do LibreOffice
    - `LibreOfficeConfig` + `legacy_convert.download_libreoffice`) ZOSTAJE
    jako OPCJONALNY manualny fallback - np. do podmiany na wariant
    `anonPL-494M`, albo do użycia w dev na Linuksie, gdzie `sys.frozen` nie
    jest ustawione. Jeśli plik pod tą ścieżką nie istnieje (świeża
    instalacja bez zbundlowanego modelu, model jeszcze nie pobrany
    fallbackiem), `gliner_layer.load_model` zgłasza czytelny
    `GlinerUnavailableError` zamiast crashować aplikację - ścieżka jest w
    pełni konfigurowalna, żeby dało się wskazać inny eksport bez zmiany
    kodu."""

    model_path: str = field(default_factory=_default_gliner_model_path)
    # Archiwum ZIP z eksportem ONNX (plik modelu + config.json/tokenizer -
    # `GLiNER.from_pretrained` wymaga całego katalogu, nie tylko samego
    # .onnx) hostowane w GitHub Releases TEGO SAMEGO repo, wzorem
    # `LibreOfficeConfig.release_url`.
    release_url: str = (
        "https://github.com/cenkierpiotr/anonimizator-pism/releases/"
        "download/gliner-anonpl-300m-onnx-v1/anonPL-300M-onnx.zip"
    )
    # SHA-256 archiwum opublikowanego jako GitHub Release "gliner-anonpl-300m-onnx-v1"
    # (repo prywatne, 26.09.2026) - eksport ONNX anonPL-300M + config/tokenizer.
    release_sha256: str = (
        "ae3ac4200a2a922eae16aefa044c373282cdd33a215a684fd1766b3e7d029ed7"
    )
    # Próg pewności predykcji [0, 1] - trafienia poniżej progu są odrzucane
    # przed dopisaniem do uncertain_collector (patrz detect_all.detect_in_text).
    confidence_threshold: float = 0.5


@dataclass
class LibreOfficeConfig:
    """Ustawienia OPCJONALNEGO manualnego fallbacku pobierania LibreOffice
    "na żądanie" (obsługa .doc). PRIMARY ścieżka w zbudowanej aplikacji jest
    teraz build-time vendoring przez Chocolatey w CI (`choco install
    libreoffice-still`, patrz `.github/workflows/build-windows.yml` +
    `build/anonimizator.spec`) - `legacy_convert.find_soffice()` sprawdza
    najpierw zvendorowaną instalację obok .exe, więc ten mechanizm URL/
    checksum jest potrzebny tylko gdy ktoś chce podmienić/dograć LibreOffice
    ręcznie (np. wersja portable ZIP bez instalatora, albo gdyby zbundlowana
    instalacja została usunięta)."""

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
