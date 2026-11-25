"""Czyszczenie metadanych z wyjściowego .docx: docProps/core.xml, docProps/app.xml,
oraz generowanie neutralnej nazwy pliku wyjściowego (nie kopiujemy nazwy wejściowej
1:1, jeśli może nieść dane osobowe, np. "pozew_Kowalski_Jan.docx")."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from lxml import etree

CORE_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_NS = "http://purl.org/dc/elements/1.1/"
DCTERMS_NS = "http://purl.org/dc/terms/"

# Węzły docProps/core.xml, które mogą nieść dane identyfikujące autora/redaktora.
_CORE_FIELDS_TO_CLEAR = [
    f"{{{DC_NS}}}creator",
    f"{{{DC_NS}}}title",
    f"{{{DC_NS}}}subject",
    f"{{{DC_NS}}}description",
    f"{{{CORE_NS}}}lastModifiedBy",
    f"{{{CORE_NS}}}keywords",
]

_APP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
_APP_FIELDS_TO_CLEAR = [
    f"{{{_APP_NS}}}Manager",
    f"{{{_APP_NS}}}Company",
]


def _scrub_core_xml(xml_bytes: bytes) -> bytes:
    root = etree.fromstring(xml_bytes)
    for tag in _CORE_FIELDS_TO_CLEAR:
        for elem in root.iter(tag):
            elem.text = ""
    for tag in (f"{{{DCTERMS_NS}}}created", f"{{{DCTERMS_NS}}}modified"):
        for elem in root.iter(tag):
            elem.text = ""
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _scrub_app_xml(xml_bytes: bytes) -> bytes:
    root = etree.fromstring(xml_bytes)
    for tag in _APP_FIELDS_TO_CLEAR:
        for elem in root.iter(tag):
            elem.text = ""
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def scrub_docx_metadata(docx_path: str | Path) -> None:
    """Czyści docProps/core.xml i docProps/app.xml w istniejącym pliku .docx,
    w miejscu (in-place), zachowując resztę pakietu bez zmian."""
    docx_path = Path(docx_path)
    replacements: dict[str, bytes] = {}

    with zipfile.ZipFile(docx_path, "r") as zf:
        names = set(zf.namelist())
        if "docProps/core.xml" in names:
            replacements["docProps/core.xml"] = _scrub_core_xml(zf.read("docProps/core.xml"))
        if "docProps/app.xml" in names:
            replacements["docProps/app.xml"] = _scrub_app_xml(zf.read("docProps/app.xml"))

    if not replacements:
        return

    tmp_path = docx_path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(docx_path, "r") as zin, zipfile.ZipFile(
        tmp_path, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            data = replacements.get(item.filename, zin.read(item.filename))
            zout.writestr(item, data)
    tmp_path.replace(docx_path)


_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def neutral_output_filename() -> str:
    """Generuje neutralną nazwę pliku wyjściowego zamiast kopiowania nazwy
    wejściowej 1:1 (która może nieść dane osobowe, np. nazwisko strony)."""
    return "dokument_zanonimizowany.docx"
