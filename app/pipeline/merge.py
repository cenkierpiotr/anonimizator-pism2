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
