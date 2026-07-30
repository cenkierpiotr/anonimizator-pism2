"""Podmiana tekstu w pakiecie .docx na poziomie lxml, obejmująca CAŁY pakiet.

python-docx'owe `paragraph.runs` pomija hyperlinki (.rels), pola (w:instrText),
przypisy/komentarze, nagłówki/stopki każdej sekcji osobno oraz w:delText (tekst
usunięty przy śledzeniu zmian, wciąż fizycznie obecny w pliku). Ten moduł operuje
bezpośrednio na XML wszystkich części pakietu, żeby żadne z tych miejsc nie
zostało pominięte przy anonimizacji.
"""

from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": W_NS}

# Nazwy węzłów tekstowych, które muszą być objęte podmianą.
TEXT_TAGS = (f"{{{W_NS}}}t", f"{{{W_NS}}}delText", f"{{{W_NS}}}instrText")

# Części pakietu .docx, które mogą zawierać tekst widoczny/potencjalnie wrażliwy.
XML_PART_GLOBS = (
    "word/document.xml",
    "word/header*.xml",
    "word/footer*.xml",
    "word/footnotes.xml",
    "word/endnotes.xml",
    "word/comments.xml",
)


@dataclass
class TextNode:
    """Węzeł tekstowy XML wraz z jego pozycją w złączonym tekście części."""

    element: etree._Element
    start: int
    end: int  # koniec wyłączny


@dataclass
class PartText:
    """Złączony tekst jednej części XML pakietu, z mapą offsetów do węzłów."""

    part_name: str
    tree: etree._ElementTree
    text: str
    nodes: list[TextNode]


def _iter_text_nodes(root: etree._Element) -> Iterable[etree._Element]:
    for tag in TEXT_TAGS:
        yield from root.iter(tag)


def load_part_text(part_name: str, xml_bytes: bytes) -> PartText:
    """Parsuje jedną część XML i buduje złączony tekst z mapą offsetów."""
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.fromstring(xml_bytes, parser=parser).getroottree()
    root = tree.getroot()

    nodes: list[TextNode] = []
    pieces: list[str] = []
    offset = 0
    for elem in _iter_text_nodes(root):
        content = elem.text or ""
        if content == "":
            continue
        nodes.append(TextNode(element=elem, start=offset, end=offset + len(content)))
        pieces.append(content)
        offset += len(content)

    return PartText(part_name=part_name, tree=tree, text="".join(pieces), nodes=nodes)


def apply_replacements(part: PartText, spans: list[tuple[int, int, str]]) -> bool:
    """Nakłada podmiany (start, end, etykieta) na węzły tekstowe danej części.

    `spans` odnosi się do offsetów w `part.text` (jak zwrócone przez detektory).
    Zwraca True jeśli cokolwiek zmieniono.
    """
    if not spans:
        return False

    # `spans` pochodzi z `detect_all.detect_in_text`, który przez
    # `merge.collapse_for_replacement` już gwarantuje brak nakładających się
    # span-ów (z każdego zagnieżdżonego klastra wybrany jest jeden, o
    # najwyższym priorytecie) - bezpiecznie sortować i nakładać wprost.
    #
    # Sortuj malejąco po starcie, żeby podmiana jednego spana nie przesuwała
    # offsetów pozostałych (operujemy na kopii tekstu per-węzeł, nie na part.text).
    spans_sorted = sorted(spans, key=lambda s: s[0], reverse=True)
    changed = False

    for start, end, label in spans_sorted:
        affected = [n for n in part.nodes if n.start < end and n.end > start]
        if not affected:
            continue
        changed = True
        affected.sort(key=lambda n: n.start)

        label_written = False
        for node in affected:
            local_start = max(start, node.start) - node.start
            local_end = min(end, node.end) - node.start
            original = node.element.text or ""
            before = original[:local_start]
            after = original[local_end:]

            if not label_written:
                node.element.text = before + label + after
                label_written = True
            else:
                node.element.text = before + after

    return changed


def _iterate_target_parts(zf: zipfile.ZipFile) -> list[str]:
    names = set(zf.namelist())
    targets: list[str] = []
    for pattern in XML_PART_GLOBS:
        if "*" in pattern:
            prefix, _, suffix = pattern.partition("*")
            targets.extend(n for n in names if n.startswith(prefix) and n.endswith(suffix))
        elif pattern in names:
            targets.append(pattern)
    return sorted(set(targets))


def process_docx(
    input_path: str | Path,
    output_path: str | Path,
    detect_fn: Callable[[str], list[tuple[int, int, str]]],
) -> list[str]:
    """Wczytuje .docx, uruchamia `detect_fn` na tekście każdej istotnej części
    pakietu, nakłada podmiany i zapisuje wynikowy plik, zachowując resztę
    pakietu (obrazy, style, .rels itd.) bez zmian.

    `detect_fn` przyjmuje złączony tekst części i zwraca listę
    (start, end, etykieta) do podmiany.

    Zwraca listę nazw części, w których faktycznie coś podmieniono
    (do celów logowania bez treści — patrz higiena logów w planie).
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    shutil.copyfile(input_path, output_path)

    with zipfile.ZipFile(input_path, "r") as zin:
        target_names = _iterate_target_parts(zin)
        original_bytes = {name: zin.read(name) for name in target_names}

    modified_bytes: dict[str, bytes] = {}
    changed_parts: list[str] = []

    for name, xml_bytes in original_bytes.items():
        part = load_part_text(name, xml_bytes)
        if not part.text:
            continue
        spans = detect_fn(part.text)
        if apply_replacements(part, spans):
            changed_parts.append(name)
            modified_bytes[name] = etree.tostring(
                part.tree, xml_declaration=True, encoding="UTF-8", standalone=True
            )

    if modified_bytes:
        _rewrite_zip_parts(output_path, modified_bytes)

    return changed_parts


def _rewrite_zip_parts(docx_path: Path, replacements: dict[str, bytes]) -> None:
    """Podmienia wybrane części w istniejącym pliku .docx (ZIP), zachowując
    resztę archiwum bajt-w-bajt (obrazy, fonty, style, .rels itd.)."""
    tmp_path = docx_path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(docx_path, "r") as zin, zipfile.ZipFile(
        tmp_path, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            data = replacements.get(item.filename, zin.read(item.filename))
            zout.writestr(item, data)
    tmp_path.replace(docx_path)


def has_tracked_changes(docx_path: str | Path) -> bool:
    """Wykrywa czy dokument ma aktywne śledzenie zmian (w:ins/w:del w treści)."""
    with zipfile.ZipFile(docx_path, "r") as zf:
        if "word/document.xml" not in zf.namelist():
            return False
        xml_bytes = zf.read("word/document.xml")
    root = etree.fromstring(xml_bytes)
    return bool(root.find(f".//{{{W_NS}}}ins") is not None or root.find(f".//{{{W_NS}}}del") is not None)


def has_document_protection(docx_path: str | Path) -> bool:
    """Wykrywa `w:documentProtection` w `word/settings.xml` (ochrona edycji/
    formularza/śledzenia zmian narzucona na dokument wejściowy — patrz plan,
    sekcja "Obsługa przypadków brzegowych plików wejściowych")."""
    with zipfile.ZipFile(docx_path, "r") as zf:
        if "word/settings.xml" not in zf.namelist():
            return False
        xml_bytes = zf.read("word/settings.xml")
    root = etree.fromstring(xml_bytes)
    return root.find(f".//{{{W_NS}}}documentProtection") is not None


def remove_document_protection(docx_path: str | Path) -> bool:
    """Usuwa `w:documentProtection` z `word/settings.xml`, jeśli obecny.

    Decyzja projektowa: wynikowy plik zanonimizowany ma być swobodnie
    edytowalny przez prawnika (np. do dalszych poprawek pisma) - ochrona
    edycji odziedziczona z oryginału nie ma tu żadnej wartości ochronnej
    (dokument i tak trafia do rąk tej samej osoby), a jej zachowanie
    utrudniałoby dalszą pracę z wynikiem bez wyraźnej korzyści.

    Zwraca True jeśli coś faktycznie usunięto.
    """
    docx_path = Path(docx_path)
    with zipfile.ZipFile(docx_path, "r") as zf:
        if "word/settings.xml" not in zf.namelist():
            return False
        xml_bytes = zf.read("word/settings.xml")

    root = etree.fromstring(xml_bytes)
    protection_nodes = root.findall(f".//{{{W_NS}}}documentProtection")
    if not protection_nodes:
        return False

    for node in protection_nodes:
        node.getparent().remove(node)

    new_bytes = etree.tostring(
        root.getroottree(), xml_declaration=True, encoding="UTF-8", standalone=True
    )
    _rewrite_zip_parts(docx_path, {"word/settings.xml": new_bytes})
    return True
