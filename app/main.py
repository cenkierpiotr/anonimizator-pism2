"""Pipeline end-to-end dla pojedynczego pliku: wykrycie formatu -> odczyt ->
detekcja+anonimizacja -> zapis .docx, z obowiązkową blokadą zapisu przy
wykryciu wycieku (patrz plan, krok [5] pipeline'u i sekcja "Weryfikacja").

Wywoływane przez GUI (Faza 3) per plik z kolejki wieloplikowej - każdy plik
dostaje własny `IdentityRegistry` (numeracja `[Osoba 1]` żyje tylko w pamięci
na czas przetwarzania JEDNEGO dokumentu, nigdy nie jest dzielona między pliki
ani zapisywana na dysk).
"""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import docx

from app.config import AppConfig
from app.pipeline import language_detect, legacy_convert, metadata_scrub, ocr, odt_reader, pdf_reader
from app.pipeline import docx_writer
from app.pipeline.text_reflow import reflow_lines
from app.pipeline.detect_all import Replacement, detect_in_text
from app.pipeline.format_detect import DocumentFormat, UnsupportedDocumentError, detect_format
from app.pipeline.identity_cluster import IdentityRegistry
from app.pipeline.leak_check import LeakDetectedError, LeakFinding, check_docx
from app.pipeline import small_cell_risk
from app.pipeline.temp_hygiene import STAGING_DIR_PREFIX

_LANGUAGE_SAMPLE_CHAR_LIMIT = 5000


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


@dataclass
class StagedAnonymization:
    """Wynik przetworzenia pliku, jeszcze NIE dostarczony użytkownikowi -
    czeka w katalogu tymczasowym na obowiązkowy ekran weryfikacji w GUI
    (patrz plan, punkt 7 sekcji "Jakość detekcji i warstwa bezpieczeństwa").

    `staging_docx_path` już przeszedł metadata_scrub + re-skan `leak_check`.
    Jeśli re-skan coś znalazł, wynik NIE jest odrzucany automatycznie -
    trafia do `leak_findings`, a GUI pokazuje to jako obowiązkowe ostrzeżenie
    na ekranie weryfikacji z jawnym potwierdzeniem, zamiast bezpowrotnie
    blokować zapis (użytkownik musi mieć zawsze możliwość zapisania pliku -
    patrz `feedback_...` w historii projektu). Ścieżki BEZ ekranu weryfikacji
    (`anonymize_file`/`anonymize_files`, batch/testy) nadal twardo blokują
    zapis przy niepustym `leak_findings`, bo tam nie ma człowieka, który mógłby
    świadomie podjąć decyzję o zapisaniu mimo ostrzeżenia.

    Wywołujący MUSI zakończyć każdy staging przez `finalize_staged()` (użytkownik
    zatwierdził) albo `discard_staged()` (użytkownik odrzucił/anulował) -
    inaczej katalog tymczasowy nie zostanie posprzątany.
    """

    input_path: Path
    format: DocumentFormat
    staging_dir: Path
    staging_docx_path: Path
    warnings: list[str]
    registry: IdentityRegistry
    potentially_missed: list[str] = field(default_factory=list)
    leak_findings: list[LeakFinding] = field(default_factory=list)
    uncertain_detections: list[str] = field(default_factory=list)

    @property
    def entity_count(self) -> int:
        return sum(self.registry._counters.values())

    def preview_text(self) -> str:
        """Zwraca cały zanonimizowany tekst do podglądu w ekranie weryfikacji."""
        document = docx.Document(self.staging_docx_path)
        return "\n".join(p.text for p in document.paragraphs)


def finalize_staged(staged: StagedAnonymization, output_path: str | Path) -> AnonymizeResult:
    """Użytkownik zatwierdził podgląd - przenosi plik ze stagingu na docelową
    ścieżkę i sprząta katalog tymczasowy."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staged.staging_docx_path), str(output_path))
    shutil.rmtree(staged.staging_dir, ignore_errors=True)
    return AnonymizeResult(
        input_path=staged.input_path,
        output_path=output_path,
        format=staged.format,
        warnings=staged.warnings,
        entity_count=staged.entity_count,
    )


def discard_staged(staged: StagedAnonymization) -> None:
    """Użytkownik anulował/odrzucił wynik w ekranie weryfikacji - sprząta
    katalog tymczasowy bez dostarczania żadnego pliku."""
    shutil.rmtree(staged.staging_dir, ignore_errors=True)


def _detect_fn_for(
    registry: IdentityRegistry,
    nlp,
    sample_texts: list[str] | None = None,
    potentially_missed: list[str] | None = None,
    uncertain_detections: list[str] | None = None,
) -> Callable[[str], list[tuple[int, int, str]]]:
    def _detect_fn(text: str) -> list[tuple[int, int, str]]:
        if sample_texts is not None and text:
            sample_texts.append(text)
        replacements: list[Replacement] = detect_in_text(
            text,
            registry,
            nlp=nlp,
            potentially_missed_collector=potentially_missed,
            uncertain_collector=uncertain_detections,
        )
        return [(r.start, r.end, r.label) for r in replacements]

    return _detect_fn


_ILLEGAL_XML_CHARS = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f￾￿﷐-﷯\ud800-\udfff]"
)


def _sanitize_for_docx(text: str) -> str:
    """PDF/OCR/TXT nie mają struktury XML jak docx/odt - ich tekst bywa
    zapisany z CRLF (`\\r\\n`) albo (rzadziej) pojedynczymi bajtami sterującymi
    z uszkodzonego kodowania fontu. `lxml` odrzuca gołe `\\r` i inne znaki
    sterujące przy ustawianiu tekstu węzła (`ValueError: ... no NULL bytes or
    control characters`), więc trzeba je znormalizować/usunąć zanim trafią do
    `python-docx` - inaczej cały PDF z warstwą tekstu w stylu Windows wywala
    całe przetwarzanie zamiast dać wynik."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _ILLEGAL_XML_CHARS.sub("", text)


def _build_docx_from_paragraphs(paragraphs: list[str], output_path: Path) -> None:
    """`paragraphs` to bloki tekstu już podzielone na akapity na wyzszym
    poziomie (patrz `reflow_lines` dla PDF/OCR, `\\n\\n` dla TXT) - `\\n\\n`
    wewnatrz kazdego bloku dzieli go na kolejne akapity .docx, a ewentualny
    pojedynczy `\\n` ktory mimo to zostal (np. twardo zawijany TXT) jest
    sklejany spacja zamiast trafiac dosłownie do w:t (surowy znak nowej linii
    w tekscie runu nie jest prawidlowym zlamaniem wiersza w OOXML)."""
    document = docx.Document()
    for text in paragraphs:
        sanitized = _sanitize_for_docx(text)
        for chunk in sanitized.split("\n\n"):
            chunk = chunk.replace("\n", " ").strip()
            if chunk:
                document.add_paragraph(chunk)
    document.save(output_path)


def process_to_staging(
    input_path: str | Path,
    options: AnonymizeOptions | None = None,
) -> StagedAnonymization:
    """Przetwarza JEDEN plik od formatu wejściowego do zanonimizowanego .docx,
    zatrzymując wynik w katalogu tymczasowym do obowiązkowego przeglądu w GUI
    (patrz `StagedAnonymization`) zamiast dostarczać go od razu.

    Metadane są już wyczyszczone i re-skan "leak" (patrz plan, krok [5]) już
    się wykonał - jego wynik trafia do `StagedAnonymization.leak_findings`
    zamiast blokować zwrócenie wyniku (patrz komentarz przy tym polu).

    Rzuca `UnsupportedDocumentError` (nierozpoznany/uszkodzony format),
    `PasswordRequiredError` (PDF wymaga hasła) albo `LibreOfficeNotAvailableError`
    (.doc bez pobranego komponentu). NIE rzuca już `LeakDetectedError` - to
    wywołujący (GUI albo `anonymize_file` dla ścieżek bez ekranu weryfikacji)
    decyduje, co zrobić z niepustym `leak_findings`.
    """
    options = options or AnonymizeOptions()
    input_path = Path(input_path)
    warnings: list[str] = []

    detection = detect_format(input_path)
    registry = IdentityRegistry(options.config)
    sample_texts: list[str] = []
    potentially_missed: list[str] = []
    uncertain_detections: list[str] = []
    detect_fn = _detect_fn_for(registry, options.nlp, sample_texts, potentially_missed, uncertain_detections)

    staging_dir = Path(tempfile.mkdtemp(prefix=STAGING_DIR_PREFIX))
    try:
        tmp_output = staging_dir / "wynik.docx"

        if detection.format == DocumentFormat.DOCX:
            docx_writer.process_docx(input_path, tmp_output, detect_fn)

        elif detection.format == DocumentFormat.DOC:
            converted = staging_dir / "przekonwertowany.docx"
            legacy_convert.convert_doc_to_docx(input_path, converted)
            docx_writer.process_docx(converted, tmp_output, detect_fn)

        elif detection.format == DocumentFormat.ODT:
            odt_output = staging_dir / "wynik.odt"
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
                    page_paragraphs.append(_apply_text(detect_fn, reflow_lines(page.text)))
                else:
                    ocr_result = ocr.run_ocr(page.image)
                    if ocr_result.is_low_quality:
                        warnings.append(
                            f"Strona {page.index + 1}: niska jakość OCR "
                            f"(średnia pewność {ocr_result.mean_confidence:.0f}%) - "
                            "detekcja danych może być mniej pewna."
                        )
                    page_paragraphs.append(_apply_text(detect_fn, reflow_lines(ocr_result.text)))
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
            anonymized_text = _apply_text(detect_fn, reflow_lines(ocr_result.text))
            _build_docx_from_paragraphs(anonymized_text.split("\n\n") or [anonymized_text], tmp_output)

        else:
            raise UnsupportedDocumentError(f"Nieobsługiwany format pliku: {input_path.name}")

        if docx_writer.has_tracked_changes(tmp_output) if tmp_output.exists() else False:
            warnings.append(
                "Dokument ma aktywne śledzenie zmian (track changes) - usunięty tekst "
                "(w:delText) został również zanonimizowany, ale rozważ akceptację/odrzucenie "
                "zmian przed dalszym udostępnieniem pliku."
            )

        if docx_writer.has_document_protection(tmp_output):
            docx_writer.remove_document_protection(tmp_output)
            warnings.append(
                "Oryginalny dokument miał włączoną ochronę edycji - została usunięta "
                "w wyniku, żeby plik zanonimizowany pozostał w pełni edytowalny."
            )

        sample_text = "".join(sample_texts)[:_LANGUAGE_SAMPLE_CHAR_LIMIT]
        if sample_text and not language_detect.looks_polish(sample_text):
            warnings.append(
                "Dokument wygląda na obcojęzyczny - rozpoznawanie osób (NER) może być "
                "mniej skuteczne niż na tekście polskim."
            )

        metadata_scrub.scrub_docx_metadata(tmp_output)
        leak_findings = check_docx(tmp_output)

        seen_snippets: set[str] = set()
        deduped_missed: list[str] = []
        for snippet in potentially_missed:
            key = snippet.casefold()
            if key in seen_snippets:
                continue
            seen_snippets.add(key)
            deduped_missed.append(snippet)

        warnings.extend(small_cell_risk.check(registry, options.config or AppConfig()))

        return StagedAnonymization(
            input_path=input_path,
            format=detection.format,
            staging_dir=staging_dir,
            staging_docx_path=tmp_output,
            warnings=warnings,
            registry=registry,
            potentially_missed=deduped_missed,
            leak_findings=leak_findings,
            uncertain_detections=uncertain_detections,
        )
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def anonymize_file(
    input_path: str | Path,
    output_path: str | Path,
    options: AnonymizeOptions | None = None,
) -> AnonymizeResult:
    """Wygodny skrót jednokrokowy (bez ekranu weryfikacji) - przetwarza i od razu
    zatwierdza wynik pod `output_path`. Używany przez wsadową `anonymize_files`
    i tam, gdzie mandatowy podgląd nie jest wymagany (np. testy end-to-end).

    W przeciwieństwie do `process_to_staging` TU nadal twardo blokujemy zapis
    przy niepustym `leak_findings` - bez ekranu weryfikacji nie ma człowieka,
    który mógłby świadomie zdecydować o zapisaniu mimo ostrzeżenia."""
    staged = process_to_staging(input_path, options)
    if staged.leak_findings:
        discard_staged(staged)
        raise LeakDetectedError(staged.leak_findings)
    return finalize_staged(staged, output_path)


def _apply_text(detect_fn, text: str) -> str:
    """Uruchamia `detect_fn` na płaskim tekście (TXT/PDF/OCR) i nakłada
    podmiany - te ścieżki nie mają struktury węzłów XML/ODF do rozbicia,
    więc operujemy na całym stringu naraz. `detect_fn` (przez
    `detect_all.collapse_for_replacement`) już gwarantuje span-y
    nienakładające się, więc prosta podmiana od końca do początku jest
    bezpieczna."""
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
