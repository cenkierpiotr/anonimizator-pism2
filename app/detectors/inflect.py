"""Generowanie form fleksyjnych polskich nazwisk - "drugi przebieg literalny".

Gdy inna warstwa (NER/`legal_roles.py`) znajdzie konkretne nazwisko w jednej
formie, ten moduł generuje jego prawdopodobne formy przypadkowe, żeby można
było przeszukać cały dokument dosłownie i złapać wystąpienia pominięte przez
NER (tabele, wyliczenia, wersaliki w sentencji wyroku). Reguły są uproszczone
(prawdziwa polska fleksja ma liczne wyjątki) - to celowo "tania" warstwa
podnosząca recall, nie próba pełnej poprawności językoznawczej.
"""

from __future__ import annotations


def generate_surname_forms(surname: str) -> set[str]:
    if not surname:
        return set()

    lower = surname.lower()
    forms = {surname}

    if lower.endswith("ski"):
        stem = surname[:-3]
        forms |= {stem + suf for suf in ("ski", "skiego", "skiemu", "skim")}
    elif lower.endswith("ska"):
        stem = surname[:-3]
        forms |= {stem + suf for suf in ("ska", "skiej", "ską")}
    elif lower.endswith("cki"):
        stem = surname[:-3]
        forms |= {stem + suf for suf in ("cki", "ckiego", "ckiemu", "ckim")}
    elif lower.endswith("cka"):
        stem = surname[:-3]
        forms |= {stem + suf for suf in ("cka", "ckiej", "cką")}
    elif lower.endswith("icz"):
        forms |= {surname + suf for suf in ("a", "owi", "em", "u")}
    elif lower.endswith("a"):
        stem = surname[:-1]
        forms |= {stem + suf for suf in ("a", "y", "ą", "ę", "o")}
    elif lower.endswith("y"):
        stem = surname[:-1]
        forms |= {stem + suf for suf in ("y", "ego", "emu", "ym")}
    elif lower.endswith(("k", "g")):
        # Po k/g wstawia się w polskiej fleksji "i" epentetyczne: Nowak -> Nowakiem, nie Nowakem.
        forms |= {surname + suf for suf in ("a", "owi", "iem", "u")}
    else:
        forms |= {surname + suf for suf in ("a", "owi", "em", "u")}

    return forms


def generate_full_name_forms(full_name: str) -> set[str]:
    """Dla "Imię Nazwisko" generuje warianty z odmienionym nazwiskiem, imię
    zostawiając bez zmian (proste imiona żeńskie/męskie rzadziej sprawiają
    problem w tekstach prawniczych niż nazwiska)."""

    parts = full_name.split()
    if len(parts) < 2:
        return generate_surname_forms(full_name)

    *given_names, surname = parts
    prefix = " ".join(given_names)
    return {f"{prefix} {form}" for form in generate_surname_forms(surname)}
