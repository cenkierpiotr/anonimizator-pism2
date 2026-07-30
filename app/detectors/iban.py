"""IBAN (dowolny kraj, priorytet PL): checksum mod 97 wg ISO 7064 (MOD 97-10).

Oprócz pełnego IBAN-u z prefiksem kraju (`PL61 1090...`) obsługiwany jest też
krajowy format NRB (26 cyfr, bez `PL`) - w polskich pismach/fakturach numer
rachunku jest niemal zawsze zapisywany właśnie tak, bez prefiksu. NRB dla
Polski ma tę własność, że dwie pierwsze cyfry to te same cyfry kontrolne, co
w pełnym IBAN-ie po `PL`, więc walidacja to ten sam checksum na `"PL" + NRB`.
"""

from __future__ import annotations

from app.detectors.base import Detector

_PATTERN = (
    r"(?<![A-Za-z0-9])(?P<value>"
    r"[A-Z]{2}\d{2}(?:[ ]?\d{4}){2,7}"  # pełny IBAN z prefiksem kraju
    r"|\d{2}(?:[ ]?\d{4}){6}"  # polski NRB bez prefiksu (26 cyfr)
    r")(?![A-Za-z0-9])"
)


def _mod97_ok(compact: str) -> bool:
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(str(int(c, 36)) for c in rearranged)
    return int(numeric) % 97 == 1


def is_valid_iban(value: str) -> bool:
    compact = value.replace(" ", "")
    if compact.isdigit():
        if len(compact) != 26:
            return False
        return _mod97_ok("PL" + compact)
    if len(compact) < 15 or len(compact) > 34:
        return False
    if not compact[:2].isalpha() or not compact[2:4].isdigit():
        return False
    return _mod97_ok(compact)


detector = Detector(name="iban", pattern=_PATTERN, validate=is_valid_iban)

# Fallback: ten sam wzorzec, ale BEZ walidacji checksumem — łapie numery kont
# z błędem OCR/typo, które nie przechodzą mod 97, ale kształtem są jednoznacznie
# numerem rachunku (26 cyfr w formacie NRB lub pełny IBAN z prefiksem kraju).
# Niższy priorytet niż detektor z checksumem — gdy obydwa trafią w to samo
# miejsce, wygrywa checksum-valid (dokładniejszy).
fallback_detector = Detector(name="iban", pattern=_PATTERN)
