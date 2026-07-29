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


def _all_text_parts(docx_path: Path) -> dict[str, str]:
    """Zwraca {nazwa_części: cały_tekst_widoczny_i_ukryty} dla całego pakietu,
    włącznie z docProps (metadane też mogą nieść dane)."""
    texts: dict[str, str] = {}
    with zipfile.ZipFile(docx_path, "r") as zf:
        for name in zf.namelist():
            if not name.endswith(".xml"):
                continue
            try:
                root = etree.fromstring(zf.read(name))
            except etree.XMLSyntaxError:
                continue
            # Złącz WSZYSTKIE fragmenty tekstowe w części, niezależnie od tagu —
            # celowo szerzej niż docx_writer (tam liczy się tylko w:t/w:delText/
            # w:instrText do podmiany; tu chcemy złapać cokolwiek, co mogłoby
            # nieść dane, łącznie z atrybutami w .rels).
            fragments = [t for t in root.itertext() if t and t.strip()]
            attr_fragments = [
                v for elem in root.iter() for v in elem.attrib.values() if v
            ]
            texts[name] = "\n".join(fragments + attr_fragments)
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
