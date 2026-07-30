"""Tryb "date shifting" (opcjonalny, patrz plan sekcja "Daty i kwoty"):
przesunięcie wszystkich dat w dokumencie o ten sam losowy offset zamiast
zostawiania ich bez zmian. Zachowuje odstępy między zdarzeniami (terminy,
przedawnienia zostają czytelne w relatywnym sensie), a jednocześnie nie
ujawnia rzeczywistych dat - standardowa technika de-identyfikacji medycznej,
tu zaadaptowana 1:1. Nieodwracalne bez znajomości offsetu (żyje wyłącznie
w pamięci procesu, per dokument - tak samo jak numeracja etykiet)."""

from __future__ import annotations

import re
from datetime import date, timedelta

_MONTHS_PL = {
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5,
    "czerwca": 6, "lipca": 7, "sierpnia": 8, "września": 9,
    "października": 10, "listopada": 11, "grudnia": 12,
}
_MONTHS_PL_BY_NUM = {v: k for k, v in _MONTHS_PL.items()}

_DOTTED_RE = re.compile(r"^(?P<d>\d{1,2})(?P<sep>[./-])(?P<m>\d{1,2})(?P=sep)(?P<y>\d{4})$")
_ISO_RE = re.compile(r"^(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})$")
_TEXTUAL_RE = re.compile(
    r"^(?P<d>\d{1,2})\s+(?P<month>\w+)\s+(?P<y>\d{4})\s*(?P<suffix>r\.|roku)?$"
)


def parse_date(value: str) -> date | None:
    """Rozpoznaje jeden z formatów obsługiwanych przez `detectors/dates.py` i
    zwraca obiekt `date`, albo `None` jeśli wartość jest nieprawidłowa
    kalendarzowo (np. `31.02.2026`) - w takim przypadku wołający powinien
    zostawić oryginalny tekst nietknięty zamiast ryzykować błędną podmianę."""
    value = value.strip()

    match = _DOTTED_RE.match(value)
    if match:
        try:
            return date(int(match["y"]), int(match["m"]), int(match["d"]))
        except ValueError:
            return None

    match = _ISO_RE.match(value)
    if match:
        try:
            return date(int(match["y"]), int(match["m"]), int(match["d"]))
        except ValueError:
            return None

    match = _TEXTUAL_RE.match(value)
    if match:
        month = _MONTHS_PL.get(match["month"].lower())
        if month is None:
            return None
        try:
            return date(int(match["y"]), month, int(match["d"]))
        except ValueError:
            return None

    return None


def _format_like(original: str, shifted: date) -> str:
    match = _DOTTED_RE.match(original.strip())
    if match:
        sep = match["sep"]
        return f"{shifted.day:02d}{sep}{shifted.month:02d}{sep}{shifted.year:04d}"

    if _ISO_RE.match(original.strip()):
        return f"{shifted.year:04d}-{shifted.month:02d}-{shifted.day:02d}"

    match = _TEXTUAL_RE.match(original.strip())
    if match:
        month_name = _MONTHS_PL_BY_NUM[shifted.month]
        suffix = f" {match['suffix']}" if match["suffix"] else ""
        return f"{shifted.day} {month_name} {shifted.year}{suffix}"

    return original


def shift_date_string(value: str, offset_days: int) -> str:
    """Przesuwa datę zapisaną w `value` o `offset_days`, zachowując oryginalny
    styl zapisu. Jeśli `value` nie da się rozpoznać/sparsować, zwraca ją
    nietkniętą (bezpieczny fallback zamiast rzucania wyjątku w środku
    pipeline'u)."""
    parsed = parse_date(value)
    if parsed is None:
        return value
    return _format_like(value, parsed + timedelta(days=offset_days))
