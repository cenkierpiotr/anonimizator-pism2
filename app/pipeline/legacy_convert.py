"""Konwersja przez LibreOffice headless: .doc -> .docx (obsługa starych
dokumentów) oraz dowolny dokument biurowy -> .pdf (funkcja "konwertuj do PDF",
niezależna od anonimizacji).

LibreOffice na Windows NIE jest częścią bazowego instalatora (patrz plan,
sekcja "Pobieranie LibreOffice na żądanie") - jest pobierany raz, z checksumem,
do `%LOCALAPPDATA%\\AnonimizatorPism\\libreoffice\\` i cache'owany. Na Linuksie
(środowisko deweloperskie/CI) korzystamy z systemowego `soffice`, jeśli jest
zainstalowany - ta sama ścieżka kodu, inne źródło binarki.

Higiena plików tymczasowych (patrz plan): każde wywołanie `soffice` dostaje
własny, izolowany katalog HOME/profil, czyszczony po zakończeniu - żeby nie
zostawić nieanonimizowanej treści ani historii dokumentów w profilu LibreOffice.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from app.config import LibreOfficeConfig

_APP_DIR_NAME = "AnonimizatorPism"
_LIBREOFFICE_SUBDIR = "libreoffice"
_CONVERT_TIMEOUT_SECONDS = 180

ProgressCallback = Callable[[int, int], None]  # (bytes_pobrane, bytes_razem)


class LibreOfficeNotAvailableError(RuntimeError):
    """LibreOffice nie jest zainstalowany ani pobrany - wywołujący (GUI)
    powinien zaproponować pobranie komponentu."""


class LibreOfficeChecksumError(RuntimeError):
    """Pobrany artefakt nie zgadza się z oczekiwanym SHA-256 - odrzucony,
    nie instalujemy niezweryfikowanej binarki."""


def _cache_root() -> Path:
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        # Ścieżka używana tylko w dev/CI na Linuksie - na Windows zawsze LOCALAPPDATA.
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / _APP_DIR_NAME / _LIBREOFFICE_SUBDIR


def _bundled_soffice_path() -> Path:
    root = _cache_root()
    if platform.system() == "Windows":
        return root / "program" / "soffice.exe"
    return root / "program" / "soffice"


def find_soffice() -> Path | None:
    """Zwraca ścieżkę do binarki `soffice`: najpierw pobrany/cache'owany
    komponent, potem instalacja systemowa (przydatne w dev/CI na Linuksie)."""
    bundled = _bundled_soffice_path()
    if bundled.exists():
        return bundled

    system_path = shutil.which("soffice") or shutil.which("libreoffice")
    return Path(system_path) if system_path else None


def is_libreoffice_available() -> bool:
    return find_soffice() is not None


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_libreoffice(
    config: LibreOfficeConfig | None = None,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    """Pobiera portable LibreOffice z GitHub Releases projektu, weryfikuje
    SHA-256 i rozpakowuje do katalogu cache. Zwraca ścieżkę do `soffice.exe`.

    Wymaga jednorazowego połączenia z siecią - jedyne miejsce w aplikacji,
    które je wykonuje (patrz zastrzeżenie "100% offline" w planie); użytkownik
    bez internetu może zamiast tego wskazać już zainstalowany LibreOffice na
    dysku (patrz `use_existing_installation`).
    """
    config = config or LibreOfficeConfig()
    if not config.release_sha256:
        raise LibreOfficeChecksumError(
            "Brak skonfigurowanego SHA-256 dla artefaktu LibreOffice - "
            "release jeszcze nie został opublikowany (patrz app/config.py: "
            "LibreOfficeConfig.release_sha256)."
        )

    cache_root = _cache_root()
    cache_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="lo-download-") as tmp_dir:
        archive_path = Path(tmp_dir) / "libreoffice-portable.zip"

        def _reporthook(block_num: int, block_size: int, total_size: int) -> None:
            if progress_callback is not None:
                progress_callback(min(block_num * block_size, total_size), total_size)

        urllib.request.urlretrieve(config.release_url, archive_path, reporthook=_reporthook)

        actual_sha256 = _sha256_of_file(archive_path)
        if actual_sha256 != config.release_sha256:
            raise LibreOfficeChecksumError(
                f"Suma kontrolna pobranego pliku ({actual_sha256}) nie zgadza się "
                f"z oczekiwaną ({config.release_sha256}) - plik odrzucony."
            )

        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(cache_root)

    soffice_path = _bundled_soffice_path()
    if not soffice_path.exists():
        raise RuntimeError(
            f"Rozpakowano archiwum LibreOffice, ale nie znaleziono {soffice_path} - "
            "sprawdź strukturę archiwum wydania."
        )
    return soffice_path


def use_existing_installation(soffice_path: str | Path) -> Path:
    """Alternatywa dla `download_libreoffice()` w pełni offline: użytkownik
    wskazuje już zainstalowany LibreOffice (np. przeniesiony z innego
    komputera). Kopiuje/linkuje go do katalogu cache, żeby `find_soffice()`
    znajdował go tak samo jak pobrany komponent."""
    source = Path(soffice_path)
    if not source.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku: {source}")

    target = _bundled_soffice_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def convert_document(
    input_path: str | Path,
    output_path: str | Path,
    target_format: str = "docx",
    timeout: int = _CONVERT_TIMEOUT_SECONDS,
) -> Path:
    """Konwertuje dowolny dokument obsługiwany przez LibreOffice do
    `target_format` ("docx" dla starych .doc, "pdf" dla funkcji konwersji do PDF).

    Używane w dwóch miejscach: `main.py` (branch .doc -> .docx przed
    anonimizacją) i `convert_to_pdf.py` (osobna funkcja konwersji do PDF,
    niezwiązana z anonimizacją).
    """
    soffice = find_soffice()
    if soffice is None:
        raise LibreOfficeNotAvailableError(
            "LibreOffice nie jest dostępny. Pobierz komponent obsługi .doc/PDF "
            "(patrz download_libreoffice()) albo wskaż istniejącą instalację."
        )

    input_path = Path(input_path)
    output_path = Path(output_path)

    with tempfile.TemporaryDirectory(prefix="anonimizator_lo_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        # Izolowany profil/HOME per-wywołanie: soffice nie zostawia historii
        # dokumentów ani plików tymczasowych poza tym katalogu (czyszczony
        # automatycznie po wyjściu z bloku `with`).
        profile_dir = tmp_path / "profile"
        profile_dir.mkdir()
        outdir = tmp_path / "out"
        outdir.mkdir()

        env = dict(os.environ)
        env["HOME"] = str(profile_dir)

        cmd = [
            str(soffice),
            "--headless",
            "--norestore",
            f"-env:UserInstallation=file://{profile_dir.as_posix()}",
            "--convert-to",
            target_format,
            "--outdir",
            str(outdir),
            str(input_path),
        ]
        result = subprocess.run(
            cmd,
            timeout=timeout,
            env=env,
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Konwersja LibreOffice zakończona kodem {result.returncode}. "
                "Szczegóły błędu nie są logowane (mogą zawierać treść dokumentu)."
            )

        produced = outdir / f"{input_path.stem}.{target_format}"
        if not produced.exists():
            raise RuntimeError(
                f"Konwersja LibreOffice nie utworzyła oczekiwanego pliku wyjściowego "
                f"({produced.name})."
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(produced, output_path)

    return output_path


def convert_doc_to_docx(input_path: str | Path, output_path: str | Path) -> Path:
    """Wygodny alias dla głównej ścieżki użycia w pipeline (.doc -> .docx)."""
    return convert_document(input_path, output_path, target_format="docx")
