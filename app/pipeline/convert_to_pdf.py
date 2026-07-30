"""Funkcja "konwertuj do PDF" - niezależna od pipeline'u anonimizacji.

Prawnik czasem chce po prostu zamienić .doc/.docx/.odt na .pdf (np. do wysyłki),
bez żadnej anonimizacji. To osobna, prosta ścieżka: deleguje do LibreOffice
headless (ten sam mechanizm on-demand co `legacy_convert.py` dla .doc), więc
wymaga tego samego jednorazowo pobranego komponentu.

Celowo NIE dotyka treści dokumentu - żadnej detekcji, żadnych podmian. To zwykła
konwersja formatu, w pełni odwracalna (oryginał zostaje nietknięty).
"""

from __future__ import annotations

from pathlib import Path

from app.pipeline.legacy_convert import (
    LibreOfficeNotAvailableError,
    convert_document,
    is_libreoffice_available,
)

_SUPPORTED_SOURCE_SUFFIXES = {".doc", ".docx", ".odt", ".txt", ".rtf"}


class UnsupportedConversionError(ValueError):
    """Rozszerzenie pliku wejściowego nie jest obsługiwane przez tę funkcję."""


def can_convert_to_pdf(input_path: str | Path) -> bool:
    return Path(input_path).suffix.lower() in _SUPPORTED_SOURCE_SUFFIXES


def convert_to_pdf(input_path: str | Path, output_path: str | Path | None = None) -> Path:
    """Konwertuje pojedynczy dokument biurowy do PDF przez LibreOffice headless.

    Jeśli `output_path` nie podano, plik wynikowy powstaje obok wejściowego,
    z tym samym rdzeniem nazwy i rozszerzeniem `.pdf`.
    """
    input_path = Path(input_path)
    if not can_convert_to_pdf(input_path):
        raise UnsupportedConversionError(
            f"Nieobsługiwane rozszerzenie do konwersji na PDF: '{input_path.suffix}'. "
            f"Obsługiwane: {', '.join(sorted(_SUPPORTED_SOURCE_SUFFIXES))}."
        )
    if not is_libreoffice_available():
        raise LibreOfficeNotAvailableError(
            "Konwersja do PDF wymaga komponentu LibreOffice - pobierz go najpierw "
            "(patrz app.pipeline.legacy_convert.download_libreoffice)."
        )

    if output_path is None:
        output_path = input_path.with_suffix(".pdf")
    else:
        output_path = Path(output_path)

    return convert_document(input_path, output_path, target_format="pdf")


def convert_many_to_pdf(
    input_paths: list[str | Path],
    output_dir: str | Path | None = None,
) -> list[tuple[Path, Path | None, Exception | None]]:
    """Konwertuje wiele plików do PDF (funkcja wspierająca kolejkę wieloplikową
    w GUI). Nie przerywa całej partii przy błędzie pojedynczego pliku - zwraca
    per-plik wynik: (plik_wejsciowy, plik_wyjsciowy_lub_None, wyjatek_lub_None).
    """
    results: list[tuple[Path, Path | None, Exception | None]] = []
    for raw_path in input_paths:
        input_path = Path(raw_path)
        try:
            if output_dir is not None:
                target = Path(output_dir) / (input_path.stem + ".pdf")
            else:
                target = None
            produced = convert_to_pdf(input_path, target)
            results.append((input_path, produced, None))
        except Exception as exc:  # noqa: BLE001 - kolejka musi kontynuować mimo błędu pojedynczego pliku
            results.append((input_path, None, exc))
    return results
