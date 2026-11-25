"""Odczyt i podmiana tekstu w plikach ODT (odfpy).

Analogicznie do `docx_writer.py`: każdy akapit bywa podzielony na wiele
węzłów tekstowych (formatowanie w `text:span`), więc detekcja działa na
złączonym tekście akapitu z mapą offsetów do poszczególnych węzłów, a
podmiana rozbija span na fragmenty tak, żeby nietknięty tekst zachował
oryginalne formatowanie.

Fallback: jeśli dokument ma nietypową strukturę (sekcje, ramki tekstowe
zagnieżdżone nietypowo), warto skierować go do `legacy_convert.py`
(konwersja przez LibreOffice) zamiast tej ścieżki - to wywołujący decyduje.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from odf.opendocument import load
from odf.table import TableCell
from odf.text import P as Paragraph

DetectFn = Callable[[str], list[tuple[int, int, str]]]


@dataclass
class TextNode:
    element: object  # odf.element.Text (ma atrybut .data)
    start: int
    end: int


@dataclass
class ParagraphText:
    paragraph: object
    text: str
    nodes: list[TextNode] = field(default_factory=list)


def _walk_text_nodes(element) -> list:
    nodes = []
    for child in element.childNodes:
        if hasattr(child, "data"):
            nodes.append(child)
        elif hasattr(child, "childNodes"):
            nodes.extend(_walk_text_nodes(child))
    return nodes


def load_paragraph_text(paragraph) -> ParagraphText:
    text_nodes = _walk_text_nodes(paragraph)
    parts: list[str] = []
    nodes: list[TextNode] = []
    offset = 0
    for text_node in text_nodes:
        value = str(text_node.data)
        nodes.append(TextNode(element=text_node, start=offset, end=offset + len(value)))
        parts.append(value)
        offset += len(value)
    return ParagraphText(paragraph=paragraph, text="".join(parts), nodes=nodes)


def apply_replacements(paragraph_text: ParagraphText, replacements: list[tuple[int, int, str]]) -> None:
    """`replacements`: lista (start, end, etykieta) w offsetach złączonego tekstu."""
    for start, end, label in sorted(replacements, key=lambda r: r[0], reverse=True):
        _apply_single_replacement(paragraph_text, start, end, label)


def _apply_single_replacement(paragraph_text: ParagraphText, start: int, end: int, label: str) -> None:
    first_node = True
    for node in paragraph_text.nodes:
        overlap_start = max(start, node.start)
        overlap_end = min(end, node.end)
        if overlap_start >= overlap_end:
            continue

        local_start = overlap_start - node.start
        local_end = overlap_end - node.start
        original = str(node.element.data)
        replacement = label if first_node else ""
        node.element.data = original[:local_start] + replacement + original[local_end:]
        first_node = False


def _iter_paragraphs(document):
    for paragraph in document.getElementsByType(Paragraph):
        yield paragraph
    for cell in document.getElementsByType(TableCell):
        for paragraph in cell.getElementsByType(Paragraph):
            yield paragraph


def process_odt(input_path: str | Path, output_path: str | Path, detect_fn: DetectFn) -> int:
    """Zwraca liczbę akapitów, w których dokonano podmiany."""
    document = load(str(input_path))
    changed = 0
    for paragraph in _iter_paragraphs(document):
        paragraph_text = load_paragraph_text(paragraph)
        if not paragraph_text.text:
            continue
        matches = detect_fn(paragraph_text.text)
        if not matches:
            continue
        apply_replacements(paragraph_text, matches)
        changed += 1
    document.save(str(output_path))
    return changed


def extract_all_text(input_path: str | Path) -> str:
    document = load(str(input_path))
    return "\n".join(load_paragraph_text(p).text for p in _iter_paragraphs(document))
