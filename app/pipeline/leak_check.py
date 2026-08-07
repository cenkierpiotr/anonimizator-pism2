"""Ostatnia linia obrony przed zapisem: re-skan CAŁEGO wygenerowanego pliku
.docx pod kątem zwalidowanych (checksumem) identyfikatorów, które mogły
przetrwać podmianę. Blokuje zapis, jeśli cokolwiek zostanie znalezione.

To najważniejszy pojedynczy test bezpieczeństwa w projekcie — patrz sekcja
"Weryfikacja" w planie.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from app.detectors import registry
from app.pipeline import docx_writer


@dataclass
class LeakFinding:
    part_name: str
    detector_name: str
    # Nigdy nie przechowujemy tu dopasowanej wartości ani jej treści —
    # tylko nazwę detektora i część pakietu, zgodnie z zasadą "nigdy nie
    # loguj zawartości dokumentu".
    count: int


class LeakDetectedError(RuntimeError):
    def __init__(self, findings: list[LeakFinding]):
        self.findings = findings
        summary = ", ".join(f"{f.detector_name} x{f.count} w {f.part_name}" for f in findings)
        super().__init__(f"Wykryto niezanonimizowane dane przed zapisem: {summary}")


def _attr_fragments(part_name: str, root) -> list[str]:
    """Wartości atrybutów do przeskanowania — świadomie DOKŁADNIE ten sam
    zakres co `docx_writer.apply_attribute_replacements` (patrz komentarz
    bezpieczeństwa tam): nigdy `[Content_Types].xml`, a w `.rels` wyłącznie
    `Target` relacji zewnętrznych. Inaczej ten moduł potrafiłby zgłosić
    "wyciek" w miejscu, którego writer celowo nigdy nie dotyka (żeby nie
    zepsuć integralności archiwum ZIP) — co byłoby dokładnie tym dead-endem
    blokującym zapis bez możliwości naprawy, którego ma unikać cały ten fix."""
    if docx_writer._is_structural_only_part(part_name):
        return []
    if part_name.endswith(".rels"):
        return [
            elem.get("Target")
            for elem in root.iter()
            if elem.get("TargetMode") == "External" and elem.get("Target")
        ]
    return [v for elem in root.iter() for v in elem.attrib.values() if v]


def _all_text_parts(docx_path: Path) -> dict[str, str]:
    """Zwraca {nazwa_części: cały_tekst_widoczny_i_ukryty} dla całego pakietu,
    włącznie z docProps (metadane też mogą nieść dane).

    Tekst węzłów budujemy przez `docx_writer.load_part_text` — DOKŁADNIE tę
    samą funkcję, której używa writer do podmiany — zamiast osobnej
    reimplementacji. To jedyny sposób na trwałą gwarancję parytetu zakresu:
    dwie niezależne implementacje tego samego "złącz tekst części" już raz
    się rozjechały (stąd w ogóle ten cały fix) i ponownie by się rozjechały,
    gdyby ktoś zmienił jedną bez pamiętania o drugiej."""
    texts: dict[str, str] = {}
    with zipfile.ZipFile(docx_path, "r") as zf:
        for name in zf.namelist():
            if not (name.endswith(".xml") or name.endswith(".rels")):
                continue
            if docx_writer._is_structural_only_part(name):
                continue
            try:
                part = docx_writer.load_part_text(name, zf.read(name))
            except etree.XMLSyntaxError:
                continue
            root = part.tree.getroot()
            texts[name] = "\n".join([part.text] + _attr_fragments(name, root))
    return texts


def check_docx(docx_path: str | Path) -> list[LeakFinding]:
    """Przeszukuje cały pakiet .docx wszystkimi zarejestrowanymi detektorami
    z checksumem. Zwraca listę znalezisk (pusta = plik czysty)."""
    docx_path = Path(docx_path)
    findings: list[LeakFinding] = []

    for part_name, text in _all_text_parts(docx_path).items():
        if not text:
            continue
        for detector in registry.CHECKSUM_DETECTORS:
            matches = detector.find_all(text)
            if matches:
                findings.append(
                    LeakFinding(part_name=part_name, detector_name=detector.name, count=len(matches))
                )
    return findings


def assert_clean(docx_path: str | Path) -> None:
    """Rzuca LeakDetectedError jeśli plik zawiera niezanonimizowane dane.
    Wywoływane obowiązkowo przed każdym realnym zapisem w aplikacji."""
    findings = check_docx(docx_path)
    if findings:
        raise LeakDetectedError(findings)
