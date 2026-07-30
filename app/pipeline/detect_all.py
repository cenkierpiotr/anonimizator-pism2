"""Orkiestrator: uruchamia wszystkie warstwy detekcji na tekście jednego bloku
(akapitu/komórki tabeli/nagłówka/stopki/przypisu), scala wyniki przez
`merge.resolve` i zwraca gotowe podmiany (start, end, etykieta) do zastosowania
przez writer (docx/odt/txt).

Priorytety niżej odzwierciedlają pewność każdej warstwy (patrz plan, sekcja
"Jakość detekcji i warstwa bezpieczeństwa"): wyżej = wygrywa przy nakładaniu
span-ów w `merge.resolve`. Zagnieżdżenia (np. miejscowość wewnątrz adresu,
nazwisko wewnątrz nazwy firmy) są dozwolone przez `nestable=True`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import AppConfig
from app.detectors import address as address_detector
from app.detectors import amounts
from app.detectors import case_number
from app.detectors import civil_registry
from app.detectors import dates
from app.detectors import digital_ids
from app.detectors import email
from app.detectors import iban
from app.detectors import id_card
from app.detectors import inflect
from app.detectors import institutions
from app.detectors import krs
from app.detectors import land_register
from app.detectors import legal_roles
from app.detectors import nip
from app.detectors import notarial_act
from app.detectors import npwz
from app.detectors import pesel
from app.detectors import phone
from app.detectors import regon
from app.detectors import vehicle
from app.pipeline import ner
from app.pipeline.identity_cluster import IdentityRegistry
from app.pipeline.merge import Detection, resolve

_PRIORITY_CHECKSUM = 100
_PRIORITY_CONTEXT_STRUCTURED = 90
_PRIORITY_ADDRESS_HIGH = 85
_PRIORITY_PHONE_EMAIL = 80
_PRIORITY_BIRTH_DATE = 75
_PRIORITY_LEGAL_ROLE = 70
_PRIORITY_LITERAL_RESCAN = 65
_PRIORITY_NER_PERSON = 60
_PRIORITY_NER_ORG = 55
_PRIORITY_ADDRESS_MEDIUM = 50
_PRIORITY_INSTITUTION = 45
_PRIORITY_DIGITAL_ID = 40
_PRIORITY_ADDRESS_LOW = 20
_PRIORITY_DATE = 10
_PRIORITY_AMOUNT = 10

_ADDRESS_PRIORITY_BY_CONFIDENCE = {
    "high": _PRIORITY_ADDRESS_HIGH,
    "medium": _PRIORITY_ADDRESS_MEDIUM,
    "low": _PRIORITY_ADDRESS_LOW,
}


@dataclass(frozen=True)
class Replacement:
    """Gotowa podmiana do zastosowania przez writer: [start, end) -> label."""

    start: int
    end: int
    label: str


def _from_detector(detector, text, category, priority, nestable=False) -> list[Detection]:
    return [
        Detection(m.start, m.end, category, m.value, priority, nestable)
        for m in detector.find_all(text)
    ]


def _literal_rescan(text: str, known_names: set[str], existing_spans: set[tuple[int, int]]) -> list[Detection]:
    """Drugi przebieg literalny: dla każdego znanego imienia+nazwiska wygeneruj
    jego formy fleksyjne i przeszukaj tekst dosłownie - łapie wystąpienia
    pominięte przez NER (tabele, wyliczenia, wersaliki)."""
    detections: list[Detection] = []
    seen = set(existing_spans)
    for name in known_names:
        for form in inflect.generate_full_name_forms(name):
            if form == name:
                continue
            start = 0
            while True:
                idx = text.find(form, start)
                if idx == -1:
                    break
                span = (idx, idx + len(form))
                if span not in seen:
                    detections.append(
                        Detection(span[0], span[1], "legal_role_person", form, _PRIORITY_LITERAL_RESCAN)
                    )
                    seen.add(span)
                start = idx + len(form)
    return detections


def detect_in_text(text: str, registry: IdentityRegistry, nlp=None) -> list[Replacement]:
    """Uruchamia wszystkie warstwy detekcji na pojedynczym bloku tekstu i zwraca
    listę podmian po scaleniu nakładających się span-ów i przydzieleniu etykiet
    przez `registry` (per-dokumentowy `IdentityRegistry`)."""

    detections: list[Detection] = []

    detections += _from_detector(pesel.detector, text, "pesel", _PRIORITY_CHECKSUM)
    detections += _from_detector(nip.detector, text, "nip", _PRIORITY_CHECKSUM)
    detections += _from_detector(regon.detector, text, "regon", _PRIORITY_CHECKSUM)
    detections += _from_detector(iban.detector, text, "iban", _PRIORITY_CHECKSUM)
    detections += _from_detector(land_register.detector, text, "land_register", _PRIORITY_CHECKSUM)
    detections += _from_detector(id_card.detector, text, "id_card", _PRIORITY_CHECKSUM)
    detections += _from_detector(id_card.passport_detector, text, "passport", _PRIORITY_CONTEXT_STRUCTURED)
    detections += _from_detector(vehicle.detector, text, "vehicle_vin", _PRIORITY_CHECKSUM)
    detections += _from_detector(vehicle.plate_detector, text, "vehicle_plate", _PRIORITY_CONTEXT_STRUCTURED)

    detections += _from_detector(krs.detector, text, "krs", _PRIORITY_CONTEXT_STRUCTURED)
    detections += _from_detector(npwz.detector, text, "npwz", _PRIORITY_CONTEXT_STRUCTURED)
    detections += _from_detector(case_number.detector, text, "case_number", _PRIORITY_CONTEXT_STRUCTURED)
    detections += _from_detector(notarial_act.detector, text, "notarial_act", _PRIORITY_CONTEXT_STRUCTURED)
    detections += _from_detector(civil_registry.usc_detector, text, "usc_act", _PRIORITY_CONTEXT_STRUCTURED)
    detections += _from_detector(
        civil_registry.apd_detector, text, "poswiadczenie_dziedziczenia", _PRIORITY_CONTEXT_STRUCTURED
    )
    detections += _from_detector(
        civil_registry.nors_detector, text, "rejestr_spadkowy", _PRIORITY_CONTEXT_STRUCTURED
    )

    detections += _from_detector(phone.detector, text, "phone", _PRIORITY_PHONE_EMAIL)
    detections += _from_detector(email.detector, text, "email", _PRIORITY_PHONE_EMAIL)

    detections += _from_detector(digital_ids.ip_detector, text, "ip_address", _PRIORITY_DIGITAL_ID)
    detections += _from_detector(digital_ids.imei_detector, text, "imei", _PRIORITY_DIGITAL_ID)
    detections += _from_detector(digital_ids.url_detector, text, "url", _PRIORITY_DIGITAL_ID)

    detections += _from_detector(legal_roles.detector, text, "legal_role_person", _PRIORITY_LEGAL_ROLE)
    detections += _from_detector(institutions.detector, text, "institution", _PRIORITY_INSTITUTION, nestable=True)

    entities = ner.find_entities(text, nlp=nlp)
    person_entities = [e for e in entities if e.label == "PERSON"]
    org_entities = [e for e in entities if e.label == "ORG"]
    loc_entities = [e for e in entities if e.label == "LOC"]

    detections += [
        Detection(e.start, e.end, "legal_role_person", e.text, _PRIORITY_NER_PERSON)
        for e in person_entities
    ]
    detections += [
        Detection(e.start, e.end, "institution", e.text, _PRIORITY_NER_ORG, nestable=True)
        for e in org_entities
    ]

    for candidate in address_detector.find_addresses(text, ner_locations=loc_entities):
        priority = _ADDRESS_PRIORITY_BY_CONFIDENCE[candidate.confidence]
        detections.append(Detection(candidate.start, candidate.end, "address", candidate.value, priority))

    detections += _from_detector(dates.birth_date_detector, text, "birth_date", _PRIORITY_BIRTH_DATE)
    detections += _from_detector(dates.detector, text, "date", _PRIORITY_DATE)
    detections += _from_detector(amounts.detector, text, "amount", _PRIORITY_AMOUNT)

    known_names = {d.value for d in detections if d.category == "legal_role_person"}
    existing_spans = {(d.start, d.end) for d in detections}
    detections += _literal_rescan(text, known_names, existing_spans)

    resolved = resolve(detections)

    replacements: list[Replacement] = []
    for d in resolved:
        label = registry.label_for(d.category, d.value)
        if label is None:
            continue
        replacements.append(Replacement(d.start, d.end, label))
    return replacements


def apply_replacements(text: str, replacements: list[Replacement]) -> str:
    """Nakłada podmiany na tekst od końca do początku, żeby wcześniejsze offsety
    zostały nienaruszone."""
    result = text
    for r in sorted(replacements, key=lambda r: r.start, reverse=True):
        result = result[: r.start] + r.label + result[r.end :]
    return result


def anonymize_text(text: str, config: AppConfig | None = None, nlp=None) -> tuple[str, IdentityRegistry]:
    """Wygodne API end-to-end dla pojedynczego bloku tekstu: zwraca zanonimizowany
    tekst oraz rejestr (do ponownego użycia dla kolejnych bloków tego samego
    dokumentu, żeby numeracja była spójna w całym pliku)."""
    registry = IdentityRegistry(config)
    replacements = detect_in_text(text, registry, nlp=nlp)
    return apply_replacements(text, replacements), registry
