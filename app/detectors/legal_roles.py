"""Wzorzec kontekstowy: tytuł/rola prawna + sekwencja Imię Nazwisko.

Łapie przypadki, w których spaCy NER nie rozpozna ciągu znaków jako PERSON
(np. bo model bazuje na wzorcach z prasy ogólnej, a nie z pism sądowych).
"""

from __future__ import annotations

from app.detectors.base import Detector

_ROLES = (
    r"Pan|Pani|Mec\.|notariusz|adwokat|radca prawny|pełnomocnik|powód|pozwany"
    r"|świadek|wnioskodawca|uczestnik"
    r"|wynajmujący|najemca|wierzyciel|dłużnik|mocodawca|apelujący|spadkobierca"
)

_PATTERN = (
    rf"(?i:{_ROLES})\s+"
    r"(?P<value>[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)"
)

detector = Detector(name="legal_role_person", pattern=_PATTERN)
