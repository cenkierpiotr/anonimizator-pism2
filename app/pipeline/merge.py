"""Rozstrzyganie nakładających się wykryć (interval resolution).

Sortowanie po (priorytet malejąco, długość malejąco), greedy wybór, z jawną
obsługą zagnieżdżenia: span w pełni zawarty w innym może zostać zachowany
OBOK (nie zamiast) spanu nadrzędnego, jeśli jedna ze stron jest oznaczona
jako `nestable` (np. miejscowość wewnątrz adresu, nazwisko wewnątrz nazwy
firmy). Częściowe nakładanie się (nie pełne zagnieżdżenie) zawsze przegrywa
niższy priorytet/krótszy span - to chroni np. sygnaturę prokuratorską
"Ds. 123.2026" przed rozerwaniem przez detektor daty.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Detection:
    start: int
    end: int
    category: str
    value: str
    priority: int
    nestable: bool = False
    # Pewność detekcji w [0, 1] - domyślnie 1.0 (detektory checksumowe/regex o
    # wysokiej precyzji). Obniżana np. przez tolerancję na pomyłki OCR (patrz
    # `app/detectors/ocr_tolerance.py`) i modyfikowana przez wzmocnienie
    # kontekstowe (`app/pipeline/context_score.py`) - nie wpływa na `resolve()`
    # (który nadal rozstrzyga po `priority`), tylko przenosi się do audytu
    # (`detect_all.Replacement`) i decyduje, czy trafienie jest "pewne" czy
    # "niepewne" na ekranie weryfikacji.
    score: float = 1.0


def _overlaps(a: Detection, b: Detection) -> bool:
    return a.start < b.end and b.start < a.end


def _fully_contains(outer: Detection, inner: Detection) -> bool:
    return outer.start <= inner.start and inner.end <= outer.end


def _is_nested_pair(a: Detection, b: Detection) -> bool:
    return _fully_contains(a, b) or _fully_contains(b, a)


def resolve(detections: list[Detection]) -> list[Detection]:
    ordered = sorted(
        detections,
        key=lambda d: (-d.priority, -(d.end - d.start), d.start),
    )

    accepted: list[Detection] = []
    for candidate in ordered:
        conflicts = [a for a in accepted if _overlaps(candidate, a)]
        if not conflicts:
            accepted.append(candidate)
            continue

        all_nested = all(_is_nested_pair(candidate, a) for a in conflicts)
        nesting_allowed = candidate.nestable or any(a.nestable for a in conflicts)
        # Zduplikowany, identyczny span (np. dwa detektory trafiające w to samo
        # miejsce) nie liczy się jako "zagnieżdżenie" - to zwykła kolizja,
        # wygrywa wyższy priorytet już obecny w `accepted`.
        exact_duplicate = any(a.start == candidate.start and a.end == candidate.end for a in conflicts)

        if all_nested and nesting_allowed and not exact_duplicate:
            accepted.append(candidate)

    return sorted(accepted, key=lambda d: d.start)


def collapse_for_replacement(resolved: list[Detection]) -> list[Detection]:
    """`resolve()` celowo zachowuje zagnieżdżone pary z różnych kategorii obok
    siebie (np. nazwisko wewnątrz nazwy firmy, miejscowość wewnątrz adresu) -
    to poprawne dla samej detekcji, ale dwóch NAKŁADAJĄCYCH się podmian w
    tekście nie da się jednocześnie nanieść bez wzajemnego popsucia offsetów
    (podmiana jednego przesuwa/obcina drugi). Do faktycznej podmiany w
    tekście z każdego zagnieżdżonego klastra bierzemy tylko span o
    NAJWYŻSZYM priorytecie - niezależnie czy to zewnętrzny czy wewnętrzny.

    To naprawia realny przypadek: ogólny detektor instytucji (niski priorytet,
    zawsze `nestable=True`) bywa zbyt zachłanny i łapie fragment w stylu
    "KW nr OL1G/00045213/8" jako jedną "nazwę instytucji", mimo że w środku
    jest właściwy, dużo bardziej precyzyjny numer księgi wieczystej
    (checksum, priorytet 100). Bez tej funkcji wygrywał przypadkowo
    zewnętrzny (szerszy) span, maskując mniej trafną etykietą i - przy samej
    podmianie na płaskim tekście - psując wynik. Gdy wygrywa span wewnętrzny,
    otaczający go tekst ("KW nr ") zostaje nietknięty jako nieidentyfikujący
    szablon - właściwa, wrażliwa część już została zamieniona."""
    ordered = sorted(resolved, key=lambda d: (d.start, -(d.end - d.start)))
    kept: list[Detection] = []
    for candidate in ordered:
        overlapping = [i for i, k in enumerate(kept) if k.start < candidate.end and candidate.start < k.end]
        if not overlapping:
            kept.append(candidate)
            continue
        best_kept_priority = max(kept[i].priority for i in overlapping)
        if candidate.priority > best_kept_priority:
            for i in sorted(overlapping, reverse=True):
                del kept[i]
            kept.append(candidate)
        # W przeciwnym razie candidate przegrywa z już przyjętym, silniejszym
        # spanem pokrywającym ten sam fragment - pomijamy go.
    return sorted(kept, key=lambda d: d.start)
