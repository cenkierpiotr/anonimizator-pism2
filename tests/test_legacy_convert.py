import hashlib
import sys
from pathlib import Path

import pytest

from app.config import LibreOfficeConfig
from app.pipeline import legacy_convert


def test_find_soffice_prefers_bundled_component(tmp_path, monkeypatch):
    bundled = tmp_path / "program" / "soffice"
    bundled.parent.mkdir(parents=True)
    bundled.write_text("fake binary")
    monkeypatch.setattr(legacy_convert, "_bundled_soffice_path", lambda: bundled)

    assert legacy_convert.find_soffice() == bundled


def test_find_soffice_falls_back_to_system_installation(tmp_path, monkeypatch):
    missing_bundled = tmp_path / "does-not-exist" / "soffice"
    monkeypatch.setattr(legacy_convert, "_bundled_soffice_path", lambda: missing_bundled)
    monkeypatch.setattr(legacy_convert.shutil, "which", lambda name: "/usr/bin/soffice" if name == "soffice" else None)

    result = legacy_convert.find_soffice()
    assert result is not None
    assert result == Path("/usr/bin/soffice")


def test_find_soffice_returns_none_when_unavailable(tmp_path, monkeypatch):
    missing_bundled = tmp_path / "does-not-exist" / "soffice"
    monkeypatch.setattr(legacy_convert, "_bundled_soffice_path", lambda: missing_bundled)
    monkeypatch.setattr(legacy_convert.shutil, "which", lambda name: None)

    assert legacy_convert.find_soffice() is None
    assert legacy_convert.is_libreoffice_available() is False


def test_frozen_bundled_soffice_path_returns_none_when_not_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert legacy_convert._frozen_bundled_soffice_path() is None


def test_frozen_bundled_soffice_path_returns_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "AnonimizatorPism.exe"))
    assert legacy_convert._frozen_bundled_soffice_path() is None


def test_frozen_bundled_soffice_path_found_next_to_executable(tmp_path, monkeypatch):
    soffice = tmp_path / "libreoffice" / "program" / "soffice"
    soffice.parent.mkdir(parents=True)
    soffice.write_text("fake bundled soffice")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "AnonimizatorPism.exe"))
    monkeypatch.setattr(legacy_convert.platform, "system", lambda: "Linux")

    assert legacy_convert._frozen_bundled_soffice_path() == soffice


def test_find_soffice_prefers_frozen_bundled_over_cache_and_system(tmp_path, monkeypatch):
    # Build-time vendorowana instalacja (sys.frozen) ma PRIORYTET nad
    # cache'owanym download-on-demand fallbackiem i nad systemowym PATH.
    frozen_soffice = tmp_path / "frozen" / "libreoffice" / "program" / "soffice"
    frozen_soffice.parent.mkdir(parents=True)
    frozen_soffice.write_text("fake frozen bundled soffice")
    monkeypatch.setattr(legacy_convert, "_frozen_bundled_soffice_path", lambda: frozen_soffice)

    cached_soffice = tmp_path / "cache" / "program" / "soffice"
    cached_soffice.parent.mkdir(parents=True)
    cached_soffice.write_text("fake cached soffice")
    monkeypatch.setattr(legacy_convert, "_bundled_soffice_path", lambda: cached_soffice)
    monkeypatch.setattr(legacy_convert.shutil, "which", lambda name: "/usr/bin/soffice" if name == "soffice" else None)

    assert legacy_convert.find_soffice() == frozen_soffice


def test_download_libreoffice_requires_checksum_configured():
    config = LibreOfficeConfig(release_sha256="")
    with pytest.raises(legacy_convert.LibreOfficeChecksumError):
        legacy_convert.download_libreoffice(config=config)


def test_download_libreoffice_rejects_wrong_checksum(tmp_path, monkeypatch):
    fake_archive_content = b"not a real libreoffice archive"

    def fake_urlretrieve(url, filename, reporthook=None):
        with open(filename, "wb") as f:
            f.write(fake_archive_content)
        if reporthook:
            reporthook(1, len(fake_archive_content), len(fake_archive_content))

    monkeypatch.setattr(legacy_convert.urllib.request, "urlretrieve", fake_urlretrieve)
    monkeypatch.setattr(legacy_convert, "_cache_root", lambda: tmp_path / "cache")

    config = LibreOfficeConfig(release_url="https://example.invalid/lo.zip", release_sha256="0" * 64)
    with pytest.raises(legacy_convert.LibreOfficeChecksumError):
        legacy_convert.download_libreoffice(config=config)


def test_download_libreoffice_accepts_correct_checksum_and_extracts(tmp_path, monkeypatch):
    import zipfile

    source_zip = tmp_path / "source.zip"
    with zipfile.ZipFile(source_zip, "w") as zf:
        zf.writestr("program/soffice", "fake soffice binary")
    archive_bytes = source_zip.read_bytes()
    expected_sha256 = hashlib.sha256(archive_bytes).hexdigest()

    def fake_urlretrieve(url, filename, reporthook=None):
        with open(filename, "wb") as f:
            f.write(archive_bytes)
        if reporthook:
            reporthook(1, len(archive_bytes), len(archive_bytes))

    monkeypatch.setattr(legacy_convert.urllib.request, "urlretrieve", fake_urlretrieve)
    cache_root = tmp_path / "cache"
    monkeypatch.setattr(legacy_convert, "_cache_root", lambda: cache_root)
    monkeypatch.setattr(legacy_convert, "_bundled_soffice_path", lambda: cache_root / "program" / "soffice")

    config = LibreOfficeConfig(release_url="https://example.invalid/lo.zip", release_sha256=expected_sha256)
    result = legacy_convert.download_libreoffice(config=config)

    assert result.exists()
    assert result.read_text() == "fake soffice binary"


def test_convert_document_raises_when_soffice_missing(monkeypatch):
    monkeypatch.setattr(legacy_convert, "find_soffice", lambda: None)
    with pytest.raises(legacy_convert.LibreOfficeNotAvailableError):
        legacy_convert.convert_document("input.doc", "output.docx")
