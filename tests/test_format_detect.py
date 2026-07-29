import zipfile

import docx
import pytest

from app.pipeline.format_detect import DocumentFormat, UnsupportedDocumentError, detect_format


def test_detect_docx(tmp_path):
    path = tmp_path / "doc.docx"
    docx.Document().save(path)
    result = detect_format(path)
    assert result.format == DocumentFormat.DOCX


def test_detect_txt(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("zwykły tekst")
    result = detect_format(path)
    assert result.format == DocumentFormat.TXT


def test_detect_image_by_extension(tmp_path):
    path = tmp_path / "scan.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
    result = detect_format(path)
    assert result.format == DocumentFormat.IMAGE


def test_detect_corrupt_zip_raises(tmp_path):
    path = tmp_path / "broken.docx"
    path.write_bytes(b"PK\x03\x04" + b"not a real zip" * 5)
    with pytest.raises(UnsupportedDocumentError):
        detect_format(path)


def test_detect_old_binary_doc(tmp_path):
    path = tmp_path / "old.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 20)
    result = detect_format(path)
    assert result.format == DocumentFormat.DOC


def test_detect_unknown_extension_raises(tmp_path):
    path = tmp_path / "mystery.xyz"
    path.write_bytes(b"random bytes not matching any known signature")
    with pytest.raises(UnsupportedDocumentError):
        detect_format(path)
