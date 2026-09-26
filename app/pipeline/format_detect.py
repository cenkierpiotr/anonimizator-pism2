"""Wykrywanie formatu pliku wejściowego: rozszerzenie + sniff nagłówka.

Rozpoznaje też przypadki brzegowe, żeby dać czytelny komunikat zamiast
surowego wyjątku: PDF zaszyfrowany hasłem, DOCX-w-formacie-OLE (stary,
zaszyfrowany kontener binarny zamiast ZIP-a).
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class DocumentFormat(str, Enum):
    DOCX = "docx"
    DOC = "doc"
    ODT = "odt"
    TXT = "txt"
    PDF = "pdf"
    IMAGE = "image"
    UNKNOWN = "unknown"


class UnsupportedDocumentError(Exception):
    """Plik ma format, którego nie da się przetworzyć bez dodatkowego kroku
    (np. hasło) - komunikat dla użytkownika, nie surowy wyjątek biblioteki."""


@dataclass(frozen=True)
class DetectionResult:
    format: DocumentFormat
    needs_password: bool = False
    note: str | None = None


_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}

# Stare pliki .doc/.xls/.ppt to kontener OLE2 (Compound File Binary Format).
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"


def detect_format(path: str | Path) -> DetectionResult:
    path = Path(path)
    suffix = path.suffix.lower()

    with open(path, "rb") as f:
        header = f.read(8)

    if header.startswith(_PDF_MAGIC):
        return _detect_pdf(path)

    if header.startswith(_ZIP_MAGIC):
        return _detect_zip_based(path, suffix)

    if header.startswith(_OLE_MAGIC):
        if suffix == ".doc":
            return DetectionResult(DocumentFormat.DOC)
        raise UnsupportedDocumentError(
            f"Plik '{path.name}' jest w starym formacie binarnym (OLE), "
            "którego ta aplikacja nie potrafi otworzyć bezpośrednio."
        )

    if suffix in _IMAGE_EXTENSIONS:
        return DetectionResult(DocumentFormat.IMAGE)

    if suffix == ".txt":
        return DetectionResult(DocumentFormat.TXT)

    # Sniff nagłówka obrazu niezależnie od rozszerzenia (np. zmieniona nazwa pliku).
    if header.startswith(b"\xff\xd8\xff") or header.startswith(b"\x89PNG"):
        return DetectionResult(DocumentFormat.IMAGE)

    raise UnsupportedDocumentError(
        f"Nie rozpoznano formatu pliku '{path.name}'. Obsługiwane formaty: "
        "DOCX, DOC, ODT, TXT, PDF, JPG/PNG/TIFF."
    )


def _detect_zip_based(path: Path, suffix: str) -> DetectionResult:
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
    except zipfile.BadZipFile as exc:
        raise UnsupportedDocumentError(
            f"Plik '{path.name}' wygląda na uszkodzony i nie da się go otworzyć."
        ) from exc

    if "word/document.xml" in names:
        return DetectionResult(DocumentFormat.DOCX)
    if "content.xml" in names and "mimetype" in names:
        return DetectionResult(DocumentFormat.ODT)
    if suffix == ".docx":
        return DetectionResult(DocumentFormat.DOCX)
    if suffix == ".odt":
        return DetectionResult(DocumentFormat.ODT)

    raise UnsupportedDocumentError(
        f"Plik '{path.name}' jest archiwum ZIP, ale nie rozpoznano w nim "
        "struktury DOCX ani ODT."
    )


def _detect_pdf(path: Path) -> DetectionResult:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return DetectionResult(DocumentFormat.PDF)

    try:
        pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as exc:
        message = str(exc).lower()
        if "password" in message:
            return DetectionResult(DocumentFormat.PDF, needs_password=True)
        raise UnsupportedDocumentError(
            f"Plik PDF '{path.name}' nie mógł zostać otwarty: {exc}"
        ) from exc

    return DetectionResult(DocumentFormat.PDF)
