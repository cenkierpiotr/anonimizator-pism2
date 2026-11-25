"""Wspólne tokeny wizualne GUI - paleta i style wypracowane w Stitchu
(projekt "Anonimizator Dokumentów - Desktop", motyw jasny, głęboki teal jako
kolor marki zamiast domyślnego niebieskiego - kojarzy się z prywatnością i
bezpieczeństwem, pasuje do odbiorcy kancelaryjnego). Trzymane osobno, żeby
`main_window.py` nie mieszał logiki interfejsu z liczbami/kolorami na
sztywno wpisanymi w kod.
"""

from __future__ import annotations

# Paleta bazowa (potwierdzona w Stitch design system, projekt 17412276859376663856)
PRIMARY = "#3A8187"
PRIMARY_DARK = "#2C6266"
PRIMARY_LIGHT = "#E4F0F0"
SECONDARY = "#627C7E"
NEUTRAL = "#737878"
NEUTRAL_LIGHT = "#F4F6F6"
NEUTRAL_BORDER = "#DCE3E3"
TEXT_MUTED = "#5B6666"

DANGER = "#B3261E"
DANGER_LIGHT = "#FBEAE9"
SUCCESS = "#1E7A46"
SUCCESS_LIGHT = "#E8F5EC"
WARNING = "#B5650D"
WARNING_LIGHT = "#FCF0DF"

FONT_HEADLINE = "Segoe UI Semibold"
FONT_BODY = "Segoe UI"
CORNER_RADIUS = 8
CARD_CORNER_RADIUS = 10

# Styl plakietki statusu: (tło, tekst, etykieta). Kolejność zgodna z
# `FileStatus` w main_window.py - trzymana jako zwykły str-klucz (nie enum),
# żeby uniknąć zależności cyklicznej między modułami.
STATUS_BADGE_STYLE: dict[str, tuple[str, str, str]] = {
    "oczekuje": (NEUTRAL_LIGHT, TEXT_MUTED, "Oczekuje"),
    "przetwarzanie...": (PRIMARY_LIGHT, PRIMARY_DARK, "Przetwarzanie..."),
    "do weryfikacji": (WARNING_LIGHT, WARNING, "Do weryfikacji"),
    "zapisany": (SUCCESS_LIGHT, SUCCESS, "Zapisany"),
    "błąd": (DANGER_LIGHT, DANGER, "Błąd"),
    "pominięty": (NEUTRAL_LIGHT, TEXT_MUTED, "Pominięty"),
}

# Etykieta typu pliku wg rozszerzenia - krótki, kolorowy "chip" zamiast ikony
# (bez zależności od zasobów graficznych).
FILE_TYPE_STYLE: dict[str, tuple[str, str]] = {
    ".docx": ("#2B579A", "DOCX"),
    ".doc": ("#2B579A", "DOC"),
    ".odt": ("#3A8187", "ODT"),
    ".pdf": ("#B3261E", "PDF"),
    ".txt": ("#5B6666", "TXT"),
    ".png": ("#627C7E", "PNG"),
    ".jpg": ("#627C7E", "JPG"),
    ".jpeg": ("#627C7E", "JPG"),
    ".tif": ("#627C7E", "TIF"),
    ".tiff": ("#627C7E", "TIF"),
    ".bmp": ("#627C7E", "BMP"),
}
DEFAULT_FILE_TYPE_STYLE = (NEUTRAL, "PLIK")


def file_type_style(suffix: str) -> tuple[str, str]:
    return FILE_TYPE_STYLE.get(suffix.lower(), DEFAULT_FILE_TYPE_STYLE)


def status_badge_style(status_value: str) -> tuple[str, str, str]:
    return STATUS_BADGE_STYLE.get(status_value, (NEUTRAL_LIGHT, TEXT_MUTED, status_value))
