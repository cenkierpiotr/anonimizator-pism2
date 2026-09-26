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

import re
from dataclasses import dataclass

from app.config import AppConfig
from app.detectors import address as address_detector
from app.detectors import amounts
from app.detectors import case_number
from app.detectors import civil_registry
from app.detectors import dates
from app.detectors import digital_ids
from app.detectors import email
from app.detectors import gazetteer_name
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
from app.pipeline import gliner_layer, ner
from app.pipeline.context_score import context_boost
from app.pipeline.identity_cluster import IdentityRegistry
from app.pipeline.merge import Detection, collapse_for_replacement, resolve

_PRIORITY_CHECKSUM = 100
_PRIORITY_CONTEXT_STRUCTURED = 90
_PRIORITY_ADDRESS_HIGH = 85
_PRIORITY_PHONE_EMAIL = 80
_PRIORITY_BIRTH_DATE = 75
_PRIORITY_LEGAL_ROLE = 70
_PRIORITY_LITERAL_RESCAN = 65
_PRIORITY_NER_PERSON = 60
_PRIORITY_NER_ORG = 55
# Niżej niż wszystko kontekstowe - to warstwa awaryjna, uruchamiana tylko gdy
# NER w ogóle nie znalazł żadnej osoby w danym bloku (patrz gazetteer_name.py).
_PRIORITY_GAZETTEER_NAME_FALLBACK = 35
_PRIORITY_COMPANY = 58  # wzorzec formy prawnej — pełniejszy niż NER ORG
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


_CAPITALIZED_TOKEN_RE = re.compile(r"[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]{2,}")

# Częste w pismach prawniczych słowa pospolite pisane wielką literą w środku
# zdania (nazwy instytucji rodzajowe, tytuły grzecznościowe) - wykluczone,
# żeby lista "potencjalnie pominięte" (patrz niżej) nie tonęła w szumie.
_COMMON_CAPITALIZED_WORDS = frozenset(
    {
        "sąd", "sądu", "sądowi", "sądem", "sądzie",
        "prokuratura", "prokuratury", "prokuraturze", "prokuraturą",
        "urząd", "urzędu", "urzędem", "urzędzie",
        "kodeks", "kodeksu", "kodeksem", "kodeksie",
        "artykuł", "artykułu", "artykule", "artykułem",
        "ustawa", "ustawy", "ustawie", "ustawą",
        "rzeczpospolita", "rzeczypospolitej",
        "polska", "polski", "polskiej", "polską",
        "pan", "pani", "państwo", "państwa",
        "rejonowy", "rejonowego", "rejonowym",
        "okręgowy", "okręgowego", "okręgowym",
        "apelacyjny", "apelacyjnego", "apelacyjnym",
    }
)


def _is_sentence_start(text: str, pos: int) -> bool:
    i = pos - 1
    while i >= 0 and text[i] in " \t\n\r":
        i -= 1
    if i < 0:
        return True
    return text[i] in ".!?\n"


def find_potentially_missed(text: str, resolved: list[Detection]) -> list[str]:
    """Punkt 6 planu, sekcja "Jakość detekcji i warstwa bezpieczeństwa": tokeny
    z wielkiej litery, nie na początku zdania, nieobjęte żadną warstwą
    detekcji i nie będące znanym słowem pospolitym z krótkiej listy wyjątków
    - zwracane jako fragmenty kontekstu (nie automatycznie anonimizowane, to
    sygnał "sprawdź ręcznie w ekranie weryfikacji", nie decyzja). Zerowy koszt
    modelowy, celowo z niską precyzją/wysokim recall - fałszywe alarmy są
    tańsze niż ciche pominięcie prawdziwej danej."""
    covered = [(d.start, d.end) for d in resolved]
    missed: list[str] = []
    seen_tokens: set[str] = set()

    for match in _CAPITALIZED_TOKEN_RE.finditer(text):
        start, end = match.start(), match.end()
        token = match.group()

        if token.casefold() in _COMMON_CAPITALIZED_WORDS:
            continue
        if any(c_start <= start < c_end for c_start, c_end in covered):
            continue
        if _is_sentence_start(text, start):
            continue

        key = token.casefold()
        if key in seen_tokens:
            continue
        seen_tokens.add(key)

        ctx_start = max(0, start - 25)
        ctx_end = min(len(text), end + 25)
        missed.append(text[ctx_start:ctx_end].strip())

    return missed


@dataclass(frozen=True)
class Replacement:
    """Gotowa podmiana do zastosowania przez writer: [start, end) -> label.

    `category`/`score` (punkt 7c planu - AnalyzerResult/OperatorResult jako
    niemutowalny rekord z audytem): pozwalają odtworzyć POCZĄTKI decyzji
    (co wykryto, z jaką pewnością) obok samego skutku (etykieta), bez
    przechowywania nigdzie oryginalnej wartości - `label` już jest bezpieczną
    formą do wyświetlenia. Wykorzystywane przez ekran weryfikacji do
    odróżnienia trafień "pewnych" od "niepewnych" (patrz `score` w
    `merge.Detection`)."""

    start: int
    end: int
    label: str
    category: str = ""
    score: float = 1.0


def _from_detector(detector, text, category, priority, nestable=False) -> list[Detection]:
    detections = []
    for m in detector.find_all(text):
        score = context_boost(text, m.start, m.end, category, m.score) if m.score < 1.0 else m.score
        detections.append(Detection(m.start, m.end, category, m.value, priority, nestable, score))
    return detections


def _literal_rescan(text: str, known_names: set[str], existing_spans: set[tuple[int, int]]) -> list[Detection]:
    """Drugi przebieg literalny: dla każdego znanego imienia+nazwiska wygeneruj
    jego formy fleksyjne i przeszukaj tekst dosłownie - łapie wystąpienia
    pominięte przez NER (tabele, wyliczenia, wersaliki)."""
    detections: list[Detection] = []
    seen = set(existing_spans)
    for name in known_names:
        # Uwaga: BEZ pomijania formy podstawowej (`form == name`) - dokładnie
        # ta forma najczęściej powtarza się dosłownie w tabelach/nagłówkach/
        # stopkach (np. komórka "Imię i nazwisko: Jan Kowalski"), gdzie NER
        # zawodzi bo sąsiedni tekst komórek jest sklejany bez separatora
        # (patrz `docx_writer._FLOW_CONTENT_PART_PREFIXES`) i psuje tokenizację.
        # Pomijanie jej tu byłoby sprzeczne z celem tej funkcji opisanym wyżej
        # - realny wyciek znaleziony testem e2e (nazwisko w komórce tabeli
        # nieobjęte przez NER, bo sklejone z sąsiednim tekstem w jeden token).
        # `seen`/`existing_spans` i tak eliminują duplikaty tam, gdzie NER już
        # trafił tę samą formę.
        for form in inflect.generate_full_name_forms(name):
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


def _append_gliner_uncertain(
    text: str,
    resolved: list[Detection],
    gliner_model,
    gliner_threshold: float,
    uncertain_collector: list[str],
) -> None:
    """Warstwa GLiNER (patrz `app/pipeline/gliner_layer.py` - zasada
    bezpieczeństwa nienaruszalna, opisana tam w docstringu modułu): dopisuje
    do `uncertain_collector` WYŁĄCZNIE te trafienia GLiNER, które nie
    pokrywają się z żadną już zaakceptowaną (regex+checksum/NER) detekcją -
    te zawsze wygrywają i GLiNER nigdy ich nie duplikuje. Trafienia GLiNER
    NIGDY nie trafiają do `resolve()`/`Replacement` - błąd sieci neuronowej
    bez per-span review człowieka to nieakceptowalne ryzyko wycieku danych
    klienta kancelarii."""
    covered = [(d.start, d.end) for d in resolved]
    try:
        candidates = gliner_layer.find_gliner_candidates(
            text, gliner_model, threshold=gliner_threshold
        )
    except gliner_layer.GlinerUnavailableError as exc:
        # Model już był raz wczytany poprawnie (patrz app/main.py) - błąd tutaj
        # dotyczy tylko tego jednego bloku tekstu, nie całego dokumentu.
        uncertain_collector.append(f"[GLiNER] Błąd warstwy GLiNER dla tego fragmentu: {exc}")
        return

    for candidate in candidates:
        if any(c_start < candidate.end and candidate.start < c_end for c_start, c_end in covered):
            continue
        uncertain_collector.append(
            f"[GLiNER] {candidate.label}: \"{candidate.text}\" "
            f"(pewność {candidate.score:.0%}) - sprawdź ręcznie w oryginale."
        )


def detect_in_text(
    text: str,
    registry: IdentityRegistry,
    nlp=None,
    potentially_missed_collector: list[str] | None = None,
    uncertain_collector: list[str] | None = None,
    gliner_model=None,
    gliner_threshold: float = 0.5,
) -> list[Replacement]:
    """Uruchamia wszystkie warstwy detekcji na pojedynczym bloku tekstu i zwraca
    listę podmian po scaleniu nakładających się span-ów i przydzieleniu etykiet
    przez `registry` (per-dokumentowy `IdentityRegistry`)."""

    detections: list[Detection] = []

    detections += _from_detector(pesel.detector, text, "pesel", _PRIORITY_CHECKSUM)
    detections += _from_detector(nip.detector, text, "nip", _PRIORITY_CHECKSUM)
    detections += _from_detector(regon.detector, text, "regon", _PRIORITY_CHECKSUM)
    detections += _from_detector(iban.detector, text, "iban", _PRIORITY_CHECKSUM)
    detections += _from_detector(iban.fallback_detector, text, "iban", _PRIORITY_DIGITAL_ID)
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
    detections += _from_detector(institutions.company_detector, text, "institution", _PRIORITY_COMPANY, nestable=True)

    entities = ner.find_entities(text, nlp=nlp)
    person_entities = [e for e in entities if e.label == "PERSON"]
    org_entities = [e for e in entities if e.label == "ORG"]
    loc_entities = [e for e in entities if e.label == "LOC"]

    detections += [
        Detection(e.start, e.end, "legal_role_person", e.text, _PRIORITY_NER_PERSON)
        for e in person_entities
    ]
    if not person_entities:
        # NER nie znalazł ŻADNEJ osoby w tym bloku - uruchom awaryjną warstwę
        # gazetteerową (patrz gazetteer_name.py), żeby nie polegać wyłącznie
        # na statystycznym modelu w tekstach bez kontekstu zdaniowego (np.
        # krótki nagłówek skanu OCR, wartość komórki tabeli). Celowo POMIJANA,
        # gdy NER znalazł choć jedną osobę - w takich dokumentach dodatkowa
        # warstwa tylko mnożyłaby fałszywe alarmy bez korzyści.
        detections += [
            Detection(m.start, m.end, "legal_role_person", m.value, _PRIORITY_GAZETTEER_NAME_FALLBACK, score=m.score)
            for m in gazetteer_name.find_all(text)
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

    if gliner_model is not None and uncertain_collector is not None:
        _append_gliner_uncertain(text, resolved, gliner_model, gliner_threshold, uncertain_collector)

    if potentially_missed_collector is not None:
        potentially_missed_collector.extend(find_potentially_missed(text, resolved))

    replacements: list[Replacement] = []
    for d in collapse_for_replacement(resolved):
        label = registry.apply_operator(d.category, d.value)
        if label is None:
            continue
        replacements.append(
            Replacement(d.start, d.end, label, category=d.category, score=d.score)
        )
        if uncertain_collector is not None and d.score < 1.0:
            uncertain_collector.append(
                f"{label} - dopasowanie tylko po korekcie typowych pomyłek OCR "
                f"(pewność {d.score:.0%}), sprawdź ręcznie w oryginale."
            )
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
