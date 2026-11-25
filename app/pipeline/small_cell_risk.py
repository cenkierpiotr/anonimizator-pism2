"""Ostrzeżenie o ryzyku małej celki / k-anonimity (punkt 5 planu, zaadaptowane
z de-identyfikacji medycznej).

Numerowanie/usuwanie identyfikatorów bezpośrednich (PESEL, telefon, adres...)
nie chroni przed pośrednią re-identyfikacją, gdy w dokumencie zostaje
KOMBINACJA rzadkich atrybutów - np. widoczna data (polityka `zostaw`) razem
z kategorią, której w całym dokumencie przydzielono tylko jeden numer (a
więc "[Osoba 1]"/"[adres 1]" odnosi się do dokładnie jednej, unikalnej w tym
dokumencie wartości). To tylko ostrzeżenie surowane na ekranie weryfikacji,
NIE blokada zapisu - decyzję zawsze podejmuje człowiek.
"""

from __future__ import annotations

from app.config import AppConfig, CategoryPolicy
from app.pipeline.identity_cluster import CATEGORY_LABELS, IdentityRegistry

# Kategorie pomijane przy liczeniu "rzadkich" - same w sobie nie identyfikują
# (kwota, sygnatura akt to identyfikator SPRAWY, nie osoby).
_EXCLUDED_FROM_RARITY = frozenset({"amount", "case_number"})

_RARE_COUNT_THRESHOLD = 1


def check(registry: IdentityRegistry, config: AppConfig) -> list[str]:
    """Zwraca listę ostrzeżeń (0 lub 1 element) o potencjalnym ryzyku pośredniej
    re-identyfikacji przez kombinację widocznych dat/kwot z rzadko
    występującymi w dokumencie kategoriami numerowanymi."""
    visible_categories = [
        category
        for category, policy in config.category_policies.items()
        if policy is CategoryPolicy.LEAVE
    ]
    if not visible_categories:
        return []

    rare_numbered = [
        category
        for category, count in registry._counters.items()
        if count <= _RARE_COUNT_THRESHOLD and category not in _EXCLUDED_FROM_RARITY
    ]
    if not rare_numbered:
        return []

    visible_names = ", ".join(CATEGORY_LABELS.get(c, c) for c in visible_categories)
    rare_names = ", ".join(CATEGORY_LABELS.get(c, c) for c in rare_numbered)
    return [
        f"Ryzyko pośredniej identyfikacji: dokument pozostawia widoczne "
        f"({visible_names}) razem z pojedynczymi (unikalnymi w tym dokumencie) "
        f"wystąpieniami kategorii: {rare_names}. Taka kombinacja, mimo usunięcia "
        "identyfikatorów bezpośrednich, może w praktyce wskazywać na konkretną "
        "osobę - rozważ dodatkowe uogólnienie przed udostępnieniem pisma."
    ]
