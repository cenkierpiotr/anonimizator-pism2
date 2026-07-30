"""Pipeline end-to-end dla pojedynczego pliku: wykrycie formatu -> odczyt ->
detekcja+anonimizacja -> zapis .docx, z obowiązkową blokadą zapisu przy
wykryciu wycieku (patrz plan, krok [5] pipeline'u i sekcja "Weryfikacja").

Wywoływane przez GUI (Faza 3) per plik z kolejki wieloplikowej - każdy plik
dostaje własny `IdentityRegistry` (numeracja `[Osoba 1]` żyje tylko w pamięci
na czas przetwarzania JEDNEGO dokumentu, nigdy nie jest dzielona między pliki
ani zapisywana na dysk).
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import docx

from app.config import AppConfig
from app.pipeline import legacy_convert, metadata_scrub, ocr, odt_reader, pdf_reader
from app.pipeline import docx_writer
from app.pipeline.detect_all import Replacement, detect_in_text
from app.pipeline.format_detect import DocumentFormat, UnsupportedDocumentError, detect_format
from app.pipeline.identity_cluster import IdentityRegistry
from app.pipeline.leak_check import assert_clean


class PasswordRequiredError(RuntimeError):
    """PDF wejściowy jest zaszyfrowany hasłem - wywołujący (GUI) musi je
    zebrać od użytkownika i przekazać w `AnonymizeOptions.pdf_password`."""


@dataclass
class AnonymizeOptions:
    config: AppConfig | None = None
    pdf_password: str | None = None
    nlp: object | None = None  # pozwala wstrzyknąć już załadowany model spaCy


@dataclass
class AnonymizeResult:
    input_path: Path
    output_path: Path
    format: DocumentFormat
    warnings: list[str] = field(default_factory=list)
    entity_count: int = 0


def _detect_fn_for(registry: IdentityRegistry, nlp) -> Callable[[str], list[tuple[int, int, str]]]:
    def _detect_fn(text: str) -> list[tuple[int, int, str]]:
        replacements: list[Replacement] = detect_in_text(text, registry, nlp=nlp)
        return [(r.start, r.end, r.label) for r in replacements]

    return _detect_fn


def _build_docx_from_paragraphs(paragraphs: list[str], output_path: Path) -> None:
    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    document.save(output_path)


def _finalize_output(tmp_docx: Path, final_output_path: Path) -> None:
    """Czyści metadane, uruchamia re-skan "leak" jako ostatnią linię obrony,
    i dopiero po pozytywnym wyniku przenosi plik na docelową ścieżkę. Blokuje
    dostarczenie pliku użytkownikowi, jeśli cokolwiek zwalidowanego przetrwało."""
    metadata_scrub.scrub_docx_metadata(tmp_docx)
    assert_clean(tmp_docx)  # rzuca LeakDetectedError, jeśli coś przetrwało
    final_output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(tmp_docx), str(final_output_path))


def anonymize_file(
    input_path: str | Path,
    output_path: str | Path,
    options: AnonymizeOptions | None = None,
) -> AnonymizeResult:
    """Przetwarza JEDEN plik od formatu wejściowego do zanonimizowanego .docx.

    Rzuca `UnsupportedDocumentError` (nierozpoznany/uszkodzony format),
    `PasswordRequiredError` (PDF wymaga hasła), `LibreOfficeNotAvailableError`
    (.doc bez pobranego komponentu) albo `LeakDetectedError` (blokada zapisu
    po wykryciu niezanonimizowanych danych w wyniku - błąd wewnętrzny
    detektorów, nie powinien normalnie wystąpić).
    """
    options = options or AnonymizeOptions()
    input_path = Path(input_path)
    output_path = Path(output_path)
    warnings: list[str] = []

    detection = detect_format(input_path)
    registry = IdentityRegistry(options.config)
    detect_fn = _detect_fn_for(registry, options.nlp)

    with tempfile.TemporaryDirectory(prefix="anonimizator_run_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        tmp_output = tmp_path / "wynik.docx"

        if detection.format == DocumentFormat.DOCX:
            docx_writer.process_docx(input_path, tmp_output, detect_fn)

        elif detection.format == DocumentFormat.DOC:
            converted = tmp_path / "przekonwertowany.docx"
            legacy_convert.convert_doc_to_docx(input_path, converted)
            docx_writer.process_docx(converted, tmp_output, detect_fn)

        elif detection.format == DocumentFormat.ODT:
            odt_output = tmp_path / "wynik.odt"
            odt_reader.process_odt(input_path, odt_output, detect_fn)
            legacy_convert.convert_document(odt_output, tmp_output, target_format="docx")

        elif detection.format == DocumentFormat.TXT:
            raw_text = input_path.read_text(encoding="utf-8", errors="replace")
            paragraphs = raw_text.split("\n\n") or [raw_text]
            anonymized = [_apply_text(detect_fn, p) for p in paragraphs]
            _build_docx_from_paragraphs(anonymized, tmp_output)

        elif detection.format == DocumentFormat.PDF:
            if detection.needs_password and not options.pdf_password:
                raise PasswordRequiredError(
                    f"Plik PDF '{input_path.name}' jest zaszyfrowany hasłem."
                )
            document = pdf_reader.open_pdf(input_path, password=options.pdf_password)
            try:
                pages = pdf_reader.read_pages(document)
            finally:
                document.close()

            warnings.append(
                "Dokument wejściowy to PDF - układ wyniku jest przybliżony "
                "(tekst per strona), nie identyczny z oryginałem."
            )
            page_paragraphs: list[str] = []
            for page in pages:
                if page.text is not None:
                    page_paragraphs.append(_apply_text(detect_fn, page.text))
                else:
                    ocr_result = ocr.run_ocr(page.image)
                    if ocr_result.is_low_quality:
                        warnings.append(
                            f"Strona {page.index + 1}: niska jakość OCR "
                            f"(średnia pewność {ocr_result.mean_confidence:.0f}%) - "
                            "detekcja danych może być mniej pewna."
                        )
                    page_paragraphs.append(_apply_text(detect_fn, ocr_result.text))
            _build_docx_from_paragraphs(page_paragraphs, tmp_output)

        elif detection.format == DocumentFormat.IMAGE:
            from PIL import Image

            image = Image.open(input_path)
            ocr_result = ocr.run_ocr(image)
            if ocr_result.is_low_quality:
                warnings.append(
                    f"Niska jakość OCR (średnia pewność {ocr_result.mean_confidence:.0f}%) - "
                    "detekcja danych może być mniej pewna."
                )
            warnings.append(
                "Dokument wejściowy to obraz - wynik to zwykły tekst OCR, bez oryginalnego układu."
            )
            anonymized_text = _apply_text(detect_fn, ocr_result.text)
            _build_docx_from_paragraphs(anonymized_text.split("\n\n") or [anonymized_text], tmp_output)

        else:
            raise UnsupportedDocumentError(f"Nieobsługiwany format pliku: {input_path.name}")

        if docx_writer.has_tracked_changes(tmp_output) if tmp_output.exists() else False:
            warnings.append(
                "Dokument ma aktywne śledzenie zmian (track changes) - usunięty tekst "
                "(w:delText) został również zanonimizowany, ale rozważ akceptację/odrzucenie "
                "zmian przed dalszym udostępnieniem pliku."
            )

        _finalize_output(tmp_output, output_path)

    return AnonymizeResult(
        input_path=input_path,
        output_path=output_path,
        format=detection.format,
        warnings=warnings,
        entity_count=sum(registry._counters.values()),
    )


def _apply_text(detect_fn, text: str) -> str:
    """Uruchamia `detect_fn` na płaskim tekście (TXT/PDF/OCR) i nakłada
    podmiany - te ścieżki nie mają struktury węzłów XML/ODF do rozbicia,
    więc operujemy na całym stringu naraz."""
    spans = detect_fn(text)
    result = text
    for start, end, label in sorted(spans, key=lambda s: s[0], reverse=True):
        result = result[:start] + label + result[end:]
    return result


def anonymize_files(
    input_paths: list[str | Path],
    output_dir: str | Path,
    options: AnonymizeOptions | None = None,
) -> list[tuple[Path, AnonymizeResult | None, Exception | None]]:
    """Przetwarza wiele plików (kolejka z GUI) - błąd jednego pliku nie
    przerywa reszty kolejki. Każdy plik dostaje WŁASNY `IdentityRegistry`
    (numeracja per dokument, zgodnie z planem)."""
    output_dir = Path(output_dir)
    results: list[tuple[Path, AnonymizeResult | None, Exception | None]] = []
    for raw_path in input_paths:
        input_path = Path(raw_path)
        target = output_dir / (metadata_scrub.neutral_output_filename())
        target = _unique_path(target)
        try:
            result = anonymize_file(input_path, target, options)
            results.append((input_path, result, None))
        except Exception as exc:  # noqa: BLE001 - kolejka musi kontynuować mimo błędu pojedynczego pliku
            results.append((input_path, None, exc))
    return results


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    counter = 2
    while True:
        candidate = path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1
