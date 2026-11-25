"""Sprzątanie osieroconych katalogów tymczasowych (patrz plan, sekcja "Higiena
plików tymczasowych i logów"). `process_to_staging` (`app/main.py`) tworzy per
plik katalog `anonimizator_staging_*` w systemowym temp - normalnie usuwany
przez `finalize_staged`/`discard_staged`, ale przy twardym crashu (zabicie
procesu, awaria zasilania) może zostać osierocony z nieanonimizowaną
zawartością dokumentu na dysku. Wołane raz przy starcie aplikacji.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

STAGING_DIR_PREFIX = "anonimizator_staging_"
_DEFAULT_MAX_AGE_HOURS = 24


def cleanup_stale_staging_dirs(
    max_age_hours: float = _DEFAULT_MAX_AGE_HOURS,
    base_dir: str | Path | None = None,
) -> int:
    """Usuwa katalogi `anonimizator_staging_*` starsze niż `max_age_hours`.
    Zwraca liczbę usuniętych katalogów. Błędy pojedynczych katalogów (np. plik
    otwarty przez inny proces) nie przerywają sprzątania reszty."""
    base = Path(base_dir) if base_dir is not None else Path(tempfile.gettempdir())
    if not base.is_dir():
        return 0

    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    for entry in base.glob(f"{STAGING_DIR_PREFIX}*"):
        try:
            if not entry.is_dir():
                continue
            if entry.stat().st_mtime >= cutoff:
                continue
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
        except OSError:
            continue
    return removed
