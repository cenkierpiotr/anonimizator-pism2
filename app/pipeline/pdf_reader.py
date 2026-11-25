"""Odczyt PDF: per-strona heurystyka "czy warstwa tekstu jest realna czy
śmieciowa" (nie prosty test "czy get_text() jest niepuste" - PDF-y ze
skanem czasem mają warstwę OCR-a złej jakości albo pojedyncze artefakty
tekstowe, które trzeba i tak potraktować jak skan).

Strona z wysokim wynikiem -> zwracany jest tekst z warstwy PDF.
Strona z niskim wynikiem -> zwracany jest obraz strony (PIL.Image) do OCR.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

_OCR_RENDER_DPI = 300
_MIN_TRUSTED_LENGTH = 20  # krótkie fragmenty (np. strona tytułowa) ufamy bez dalszych testów
_MIN_ALNUM_RATIO = 0.6
_POLISH_WORD_HINTS = re.compile(
    r"\b(?:i|w|na|do|nie|jest|się|z|że|przez|który|która|które|dla|oraz|art)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PageContent:
    index: int
    text: str | None  # None jeśli strona wymaga OCR
    image: Image.Image | None  # None jeśli warstwa tekstu jest wystarczająca


def open_pdf(path: str | Path, password: str | None = None) -> pdfium.PdfDocument:
    return pdfium.PdfDocument(str(path), password=password)


def iter_pages(document: pdfium.PdfDocument) -> Iterator[PageContent]:
    """Jak `read_pages`, ale strumieniuje strony pojedynczo (generator)
    zamiast materializować od razu WSZYSTKIE strony w jednej liście.

    Dla wielostronicowych skanów (np. obszerne akta sądowe) `read_pages`
    renderuje bitmapy 300 DPI dla KAŻDEJ strony-skanu i trzyma je wszystkie
    w pamięci na raz, zanim OCR zdąży przetworzyć choćby pierwszą - zmierzone
    04.10.2026: 120-stronicowy skan podnosi RSS procesu o ~4,6 GB tylko na
    same bitmapy. Wywołujący, który przetwarza strony sekwencyjnie i nie
    trzyma referencji do poprzednich (jak `app.main`), powinien iterować
    po tym generatorze, nie wołać `read_pages`."""
    for index in range(len(document)):
        page = document[index]
        text = _extract_text(page)
        if _looks_like_real_text(text, page):
            yield PageContent(index=index, text=text, image=None)
        else:
            yield PageContent(index=index, text=None, image=_render_page(page))


def read_pages(document: pdfium.PdfDocument) -> list[PageContent]:
    return list(iter_pages(document))


def _extract_text(page: pdfium.PdfPage) -> str:
    textpage = page.get_textpage()
    try:
        return textpage.get_text_range()
    finally:
        textpage.close()


def _looks_like_real_text(text: str, page: pdfium.PdfPage) -> bool:
    stripped = text.strip()
    if not stripped:
        return False

    # Krótkie strony (tytułowa, sama sygnatura na końcu) mają mało tekstu mimo
    # bycia realną warstwą tekstową - nie karzemy ich niską "gęstością znaków".
    if len(stripped) < _MIN_TRUSTED_LENGTH:
        return True

    # Ciąg samych symboli/śmieci (typowe dla błędnie zdekodowanych fontów
    # bitmapowych w skanach) ma niski udział liter/cyfr/białych znaków.
    alnum_ratio = sum(c.isalnum() or c.isspace() for c in stripped) / len(stripped)
    if alnum_ratio < _MIN_ALNUM_RATIO:
        return False

    if _POLISH_WORD_HINTS.search(stripped):
        return True

    # Brak typowych polskich słów funkcyjnych (np. dokument obcojęzyczny albo
    # sama tabela liczb) - i tak ufamy, jeśli tekst jest wyraźnie alfanumeryczny.
    return alnum_ratio >= 0.85


def _render_page(page: pdfium.PdfPage) -> Image.Image:
    scale = _OCR_RENDER_DPI / 72
    bitmap = page.render(scale=scale)
    try:
        return bitmap.to_pil()
    finally:
        bitmap.close()
