"""Golden dataset: generator syntetycznych pism prawniczych + pomiar recall/precision.

Patrz plan projektu, sekcja "Weryfikacja": zamiast ręcznie zbieranych (i przez
to niepowtarzalnych, trudnych do dzielenia się) prawdziwych skanów, generujemy
syntetyczne dokumenty z ZNANYMI z góry rozpiętościami danych wrażliwych
(ground truth), wypełnione losowymi, ale poprawnymi pod względem checksumy
danymi (PESEL/NIP/IBAN z prawdziwym algorytmem kontrolnym) oraz imionami/
nazwiskami/miejscowościami z tych samych gazetteerów, których używa produkcyjny
pipeline (`app/pipeline/gazetteers.py`) - dzięki temu miara jest reprezentatywna
dla realnych warunków działania detektorów, a nie zależna od cudzych danych
osobowych.

To jest narzędzie deweloperskie/ewaluacyjne, NIE część wysyłanej aplikacji -
celowo żyje pod `scripts/`, nie pod `app/`, i nie jest wpięte w pytest/CI
(liczby recall/precision są do oceny człowieka, nie do bramki pass/fail -
regresja jakości detekcji jednego procenta nie powinna czerwienić builda,
ale POWINNA być widoczna przy ręcznym uruchomieniu tego skryptu).

Uruchomienie:

    source .venv/bin/activate
    python3 scripts/golden_dataset.py [--n 30] [--seed 42] [--out scripts/golden_report.md]
"""

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline import gazetteers
from app.pipeline.detect_all import Replacement, detect_in_text
from app.pipeline.identity_cluster import IdentityRegistry

# ---------------------------------------------------------------------------
# Generatory pojedynczych wartości z poprawną checksumą / kształtem regexu
# detektorów produkcyjnych (patrz app/detectors/*.py) - żeby ground truth
# faktycznie było tym, co detektor MÓGŁBY złapać, a nie losowym szumem.
# ---------------------------------------------------------------------------

_PESEL_WEIGHTS = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
_NIP_WEIGHTS = (6, 5, 7, 2, 3, 4, 5, 6, 7)

_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def gen_pesel(rng: random.Random) -> str:
    year = rng.randint(1950, 2009)
    month = rng.randint(1, 12)
    day = rng.randint(1, _DAYS_IN_MONTH[month - 1])
    century_offset = 0 if 1900 <= year <= 1999 else 20  # wystarczy do naszego zakresu lat
    encoded_month = month + century_offset
    yy = year % 100
    digits = [int(c) for c in f"{yy:02d}{encoded_month:02d}{day:02d}"]
    digits += [rng.randint(0, 9) for _ in range(4)]
    checksum = sum(w * d for w, d in zip(_PESEL_WEIGHTS, digits)) % 10
    control = (10 - checksum) % 10
    digits.append(control)
    return "".join(str(d) for d in digits)


def gen_nip(rng: random.Random) -> str:
    digits = [rng.randint(0, 9) for _ in range(9)]
    while True:
        checksum = sum(w * d for w, d in zip(_NIP_WEIGHTS, digits)) % 11
        if checksum != 10:
            break
        digits = [rng.randint(0, 9) for _ in range(9)]
    digits.append(checksum)
    d = digits
    return f"{d[0]}{d[1]}{d[2]}-{d[3]}{d[4]}{d[5]}-{d[6]}{d[7]}-{d[8]}{d[9]}"


def gen_iban(rng: random.Random) -> str:
    """PL + 2 cyfry kontrolne + 24 cyfry numeru krajowego, checksum ISO 7064
    MOD 97-10 (ta sama reguła co w `app/detectors/iban.py`)."""
    national = "".join(str(rng.randint(0, 9)) for _ in range(24))
    rearranged = national + "PL00"
    numeric = "".join(str(int(c, 36)) for c in rearranged)
    remainder = int(numeric) % 97
    check_digits = 98 - remainder
    return f"PL{check_digits:02d}{national}"


def gen_case_number(rng: random.Random) -> str:
    roman = rng.choice(["I", "II", "III", "IV"])
    kind = rng.choice(["C", "Nc", "GC", "Ns", "Co"])
    number = rng.randint(1, 9999)
    year = rng.randint(20, 26)
    return f"{roman} {kind} {number}/{year}"


def gen_phone(rng: random.Random) -> str:
    prefix = rng.choice(["5", "6", "7", "8"])
    digits = prefix + "".join(str(rng.randint(0, 9)) for _ in range(8))
    return f"{digits[0:3]} {digits[3:6]} {digits[6:9]}"


def gen_email(rng: random.Random, first: str, last: str) -> str:
    domain = rng.choice(["example.com", "poczta.pl", "mail.pl"])
    return f"{first.casefold()}.{last.casefold()}@{domain}"


def gen_postal_city(rng: random.Random) -> str:
    postal = f"{rng.randint(0, 99):02d}-{rng.randint(0, 999):03d}"
    city = rng.choice(sorted(gazetteers.cities())).capitalize()
    return f"{postal} {city}"


def gen_person_name(rng: random.Random) -> tuple[str, str]:
    first = rng.choice(sorted(gazetteers.first_names())).capitalize()
    last = rng.choice(sorted(gazetteers.surnames())).capitalize()
    return first, last


# ---------------------------------------------------------------------------
# Budowanie dokumentu z jednoczesnym śledzeniem ground truth (kategoria,
# start, end, wartość) - offsety liczone w miarę doklejania fragmentów, więc
# nie ma ryzyka rozjazdu przy późniejszych zmianach szablonu.
# ---------------------------------------------------------------------------


@dataclass
class GroundTruthEntity:
    category: str
    start: int
    end: int
    value: str


class DocBuilder:
    def __init__(self) -> None:
        self._parts: list[str] = []
        self._pos = 0
        self.entities: list[GroundTruthEntity] = []

    def text(self, s: str) -> "DocBuilder":
        self._parts.append(s)
        self._pos += len(s)
        return self

    def entity(self, category: str, value: str) -> "DocBuilder":
        start = self._pos
        self._parts.append(value)
        self._pos += len(value)
        self.entities.append(GroundTruthEntity(category, start, self._pos, value))
        return self

    def build(self) -> str:
        return "".join(self._parts)


@dataclass
class GoldenDocument:
    doc_id: str
    doc_type: str
    text: str
    entities: list[GroundTruthEntity]


# ---------------------------------------------------------------------------
# Szablony 4 typów pism (patrz zadanie: pozew / akt notarialny / wyrok /
# wezwanie do zapłaty). Każdy szablon woła te same generatory wartości, żeby
# rozkład kategorii ground truth był porównywalny między typami.
# ---------------------------------------------------------------------------


def _fill_common(b: DocBuilder, rng: random.Random, role_word: str) -> None:
    """Wspólny blok danych strony (imię/nazwisko, PESEL, adres, telefon,
    e-mail) w formie, którą łapią odpowiednie detektory produkcyjne:
    - `legal_roles.py` wymaga słowa-roli BEZPOŚREDNIO przed Imię Nazwisko
      (bez dwukropka/przecinka pomiędzy).
    - `address.py` (`_POSTAL_WITH_CITY_PATTERN`) łapie samo "NN-NNN Miasto",
      niezależnie od otaczającego tekstu.
    """
    first, last = gen_person_name(rng)
    b.text(f"{role_word} ")
    b.entity("legal_role_person", f"{first} {last}")
    b.text(", PESEL ")
    b.entity("pesel", gen_pesel(rng))
    b.text(", zamieszkały/-a pod adresem: ")
    b.entity("address", gen_postal_city(rng))
    b.text(", tel. ")
    b.entity("phone", gen_phone(rng))
    b.text(", e-mail: ")
    b.entity("email", gen_email(rng, first, last))
    b.text(".\n")


def _fill_company(b: DocBuilder, rng: random.Random, label: str) -> None:
    b.text(f"{label} \"Nowak i Wspólnicy\" Sp. z o.o. z siedzibą w ")
    b.entity("address", gen_postal_city(rng))
    b.text(", NIP ")
    b.entity("nip", gen_nip(rng))
    b.text(", nr rachunku bankowego ")
    b.entity("iban", gen_iban(rng))
    b.text(".\n")


def template_pozew(rng: random.Random) -> DocBuilder:
    b = DocBuilder()
    b.text("Sąd Rejonowy dla Warszawy-Śródmieścia, Wydział I Cywilny\n\n")
    b.text("POZEW O ZAPŁATĘ\n\n")
    _fill_common(b, rng, "Powód")
    b.text("przeciwko\n\n")
    _fill_company(b, rng, "Pozwany")
    b.text("Sygn. akt ")
    b.entity("case_number", gen_case_number(rng))
    b.text(".\n\nWnoszę o zasądzenie od pozwanego na rzecz powoda kwoty 12 500,00 zł wraz z odsetkami.\n")
    return b


def template_akt_notarialny(rng: random.Random) -> DocBuilder:
    b = DocBuilder()
    b.text("AKT NOTARIALNY\n\n")
    b.text("Repertorium A numer 1234/2024\n\n")
    b.text("Przed notariuszem stawił się ")
    _fill_common(b, rng, "Pan")
    b.text("działający w imieniu spółki, przy czym ")
    _fill_company(b, rng, "spółka")
    b.text("Strony oświadczają, że powyższe dane są zgodne z prawdą.\n")
    return b


def template_wyrok(rng: random.Random) -> DocBuilder:
    b = DocBuilder()
    b.text("WYROK\nW IMIENIU RZECZYPOSPOLITEJ POLSKIEJ\n\n")
    b.text("Sąd Okręgowy w Krakowie, sygn. akt ")
    b.entity("case_number", gen_case_number(rng))
    b.text(", po rozpoznaniu sprawy z powództwa:\n\n")
    _fill_common(b, rng, "powód")
    b.text("\nprzeciwko:\n\n")
    _fill_common(b, rng, "pozwany")
    b.text("\norzeka jak w sentencji.\n")
    return b


def template_wezwanie(rng: random.Random) -> DocBuilder:
    b = DocBuilder()
    b.text("WEZWANIE DO ZAPŁATY\n\n")
    _fill_company(b, rng, "Wierzyciel")
    b.text("wzywa\n\n")
    _fill_common(b, rng, "Pani")
    b.text("do zapłaty zaległej kwoty 3 200,00 zł w terminie 7 dni.\n")
    return b


_TEMPLATES = {
    "pozew": template_pozew,
    "akt_notarialny": template_akt_notarialny,
    "wyrok": template_wyrok,
    "wezwanie_do_zaplaty": template_wezwanie,
}


def generate_dataset(n: int, seed: int) -> list[GoldenDocument]:
    rng = random.Random(seed)
    doc_types = sorted(_TEMPLATES)
    docs: list[GoldenDocument] = []
    for i in range(n):
        doc_type = doc_types[i % len(doc_types)]
        builder = _TEMPLATES[doc_type](rng)
        docs.append(
            GoldenDocument(
                doc_id=f"{doc_type}-{i:03d}",
                doc_type=doc_type,
                text=builder.build(),
                entities=builder.entities,
            )
        )
    return docs


# ---------------------------------------------------------------------------
# Ewaluacja: uruchomienie prawdziwego pipeline'u detekcji (`detect_in_text`,
# ten sam kod co produkcyjny `app/main.py`) i porównanie z ground truth.
# ---------------------------------------------------------------------------


def _spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return max(a_start, b_start) < min(a_end, b_end)


@dataclass
class CategoryStats:
    ground_truth_count: int = 0
    matched_count: int = 0

    @property
    def recall(self) -> float:
        return self.matched_count / self.ground_truth_count if self.ground_truth_count else float("nan")


def evaluate(docs: list[GoldenDocument]) -> tuple[dict[str, CategoryStats], int, int]:
    """Zwraca (statystyki per kategoria, liczba wszystkich detekcji, liczba
    detekcji pokrywających się z JAKĄKOLWIEK zaplanowaną encją - "prawdziwie
    pozytywne" względem naszego ground truth).

    Uwaga o precyzji: `Replacement` (wynik `detect_in_text`) niesie tylko
    gotową etykietę zamiany, nie kategorię detektora - dokładna precyzja PER
    KATEGORIA wymagałaby zmiany publicznego API `detect_all.py`, którego celowo
    nie ruszamy w tym zadaniu (równoległa praca na innym wątku). Liczymy więc
    precyzję zbiorczo: detekcja bez pokrycia w ground truth to potencjalny
    fałszywy alarm - ALE część z nich to poprawne, zamierzone działanie
    detektorów na tekście szablonu (np. nazwa sądu/spółki wykryta jako
    `institution`, data w nagłówku) - patrz komentarz w raporcie."""
    stats: dict[str, CategoryStats] = {}
    total_detections = 0
    total_true_positive_detections = 0

    for doc in docs:
        registry = IdentityRegistry()
        replacements: list[Replacement] = detect_in_text(doc.text, registry)
        total_detections += len(replacements)

        for gt in doc.entities:
            cat_stats = stats.setdefault(gt.category, CategoryStats())
            cat_stats.ground_truth_count += 1
            if any(_spans_overlap(gt.start, gt.end, r.start, r.end) for r in replacements):
                cat_stats.matched_count += 1

        for r in replacements:
            if any(_spans_overlap(r.start, r.end, gt.start, gt.end) for gt in doc.entities):
                total_true_positive_detections += 1

    return stats, total_detections, total_true_positive_detections


def format_report(
    docs: list[GoldenDocument],
    stats: dict[str, CategoryStats],
    total_detections: int,
    total_true_positive_detections: int,
    seed: int,
) -> str:
    lines = [
        "# Golden dataset - raport recall/precision",
        "",
        f"Wygenerowano {len(docs)} syntetycznych dokumentów (seed={seed}), typy: "
        + ", ".join(sorted({d.doc_type for d in docs})) + ".",
        "",
        "## Recall per kategoria",
        "",
        "| Kategoria | Ground truth | Wykryte | Recall |",
        "|---|---:|---:|---:|",
    ]
    for category in sorted(stats):
        s = stats[category]
        recall_pct = f"{s.recall * 100:.1f}%" if s.ground_truth_count else "n/d"
        lines.append(f"| {category} | {s.ground_truth_count} | {s.matched_count} | {recall_pct} |")

    total_gt = sum(s.ground_truth_count for s in stats.values())
    total_matched = sum(s.matched_count for s in stats.values())
    overall_recall = total_matched / total_gt if total_gt else float("nan")

    precision = total_true_positive_detections / total_detections if total_detections else float("nan")

    lines += [
        "",
        f"**Recall ogółem: {overall_recall * 100:.1f}%** ({total_matched}/{total_gt} zaplanowanych encji wykrytych).",
        "",
        "## Precyzja (zbiorcza, nie per kategoria)",
        "",
        f"Wszystkich detekcji w całym zbiorze: {total_detections}. Z tego pokrywających się z jakąś "
        f"zaplanowaną encją: {total_true_positive_detections} -> **precyzja zbiorcza: {precision * 100:.1f}%**.",
        "",
        "Uwaga: część detekcji spoza ground truth to NIE fałszywe alarmy w sensie użytkowym, tylko "
        "poprawne działanie warstw, których nie modelujemy w tym generatorze (np. `institution` na "
        "nazwie sądu/spółki w nagłówku, `date`/`amount` we frazach szablonu, dodatkowe wystąpienia "
        "nazwiska w drugim przebiegu literalnym). Realna precyzja \"czy to naprawdę PII\" jest więc "
        "prawdopodobnie WYŻSZA niż liczba powyżej sugeruje - to ograniczenie metodologii, nie pipeline'u.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=30, help="liczba dokumentów do wygenerowania")
    parser.add_argument("--seed", type=int, default=42, help="ziarno losowości (powtarzalność)")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "golden_report.md",
        help="ścieżka pliku raportu Markdown",
    )
    args = parser.parse_args()

    docs = generate_dataset(args.n, args.seed)
    stats, total_detections, total_tp = evaluate(docs)
    report = format_report(docs, stats, total_detections, total_tp, args.seed)

    args.out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n(raport zapisany też do {args.out})")


if __name__ == "__main__":
    main()
