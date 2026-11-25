"""Nazwy sądów, prokuratur, jednostek policji oraz spółek/firm.

Dwa wzorce:
  1. `detector` — sądy, prokuratury, komendy (wzorzec z użyciem miejscowości)
  2. `company_detector` — nazwy spółek rozpoznawane po przyrostku formy
     prawnej (np. "TravelTour sp. z o.o.", "Bud-Mont S.A.", "Kancelaria
     Nowak sp. k."). Przyrostek formy prawnej jest sam w sobie silną kotwicą
     — zapobiega wyciekowi marki/firmy, gdy NER spaCy wyłapuje tylko "z o.o."
"""

from __future__ import annotations

from app.detectors.base import Detector

_PATTERN = (
    r"(?P<value>(?:Sąd|Prokuratura|Komenda)\s+"
    r"(?:Rejonowy|Rejonowa|Okręgowy|Okręgowa|Apelacyjny|Powiatowa|Miejska|Wojewódzka)\s+"
    r"(?:Policji\s+)?w\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)"
)

# Pełne nazwy spółek z przyrostkiem formy prawnej.
# Nazwa właściwa: 1-5 wyrazów z wielkiej litery (w tym "i", "w" jako spójniki
# pisane małą literą wewnątrz nazwy), ewentualne dodatkowe kwalifikatory
# (np. "Grupa", "Holding") i znaki interpunkcyjne w nazwie ("Bud-Mont").
# Formy prawne: sp. z o.o., S.A., sp. k., sp. j., s.c., sp. p., sp. z o.o. sp. k., itp.
_CAP = r"[A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźżA-ZĄĆĘŁŃÓŚŹŻ.\-]*"
_COMPANY_NAME = rf"{_CAP}(?:\s+(?:{_CAP}|[iw])){{0,5}}"
_LEGAL_FORM = (
    r"(?:[Ss]p\.?\s*[Zz]\s*[Oo]\.?[Oo]\.?|"  # sp. z o.o.
    r"[Ss]półka\s+[Zz]\s*[Oo]graniczonią\s+Odpowiedzialności(?:ą)?|"  # pełna nazwa
    r"S\.?\s*A\.?|"  # S.A.
    r"[Ss]półka\s+[Aa]kcyjna|"  # pełna nazwa
    r"[Ss]p\.?\s*[KkJjPp]\.?|"  # sp. k., sp. j., sp. p.
    r"[Ss]półka\s+(?:Komandytowa|Jawna|Partnerska|Cywilna)|"  # pełne nazwy
    r"[Ss]\.?[Cc]\.?|"  # s.c.
    r"sp\.\s*z\s+o\.\s*o\.\s*[Ss]p\.\s*[KkJj]\.?)"  # combined forms
)
_COMPANY_PATTERN = (
    rf"(?P<value>{_COMPANY_NAME}\s+{_LEGAL_FORM})"
)

detector = Detector(name="institution", pattern=_PATTERN)
company_detector = Detector(name="institution", pattern=_COMPANY_PATTERN)
