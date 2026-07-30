import zipfile

import docx
import pytest

from app.detectors.pesel import detector as pesel_detector
from app.pipeline import docx_writer


def _detect_pesel(text: str) -> list[tuple[int, int, str]]:
    return [(m.start, m.end, "[PESEL 1]") for m in pesel_detector.find_all(text)]


@pytest.fixture
def sample_docx(tmp_path):
    path = tmp_path / "input.docx"
    document = docx.Document()
    document.add_paragraph("Powód, PESEL 44051401359, wnosi o...")
    document.add_paragraph("Fragment bez danych wrażliwych.")
    document.save(path)
    return path


def test_process_docx_replaces_pesel_and_keeps_rest(sample_docx, tmp_path):
    output = tmp_path / "output.docx"
    changed = docx_writer.process_docx(sample_docx, output, _detect_pesel)

    assert "word/document.xml" in changed

    result = docx.Document(output)
    paragraphs = [p.text for p in result.paragraphs]
    assert paragraphs[0] == "Powód, PESEL [PESEL 1], wnosi o..."
    assert paragraphs[1] == "Fragment bez danych wrażliwych."


def test_process_docx_preserves_other_zip_parts(sample_docx, tmp_path):
    output = tmp_path / "output.docx"
    docx_writer.process_docx(sample_docx, output, _detect_pesel)

    with zipfile.ZipFile(sample_docx) as zin, zipfile.ZipFile(output) as zout:
        assert set(zin.namelist()) == set(zout.namelist())
        # Style'e i inne nietknięte części pakietu muszą zostać identyczne.
        for name in zin.namelist():
            if name == "word/document.xml":
                continue
            assert zin.read(name) == zout.read(name), name


def test_split_run_replacement(tmp_path):
    """PESEL rozbity na wiele w:r/w:t o różnym formatowaniu (np. pogrubienie
    części numeru) musi zostać zamieniony na jedną poprawną etykietę."""
    path = tmp_path / "split.docx"
    document = docx.Document()
    p = document.add_paragraph()
    p.add_run("PESEL: 440514")
    p.add_run("01359").bold = True
    p.add_run(" powoda.")
    document.save(path)

    output = tmp_path / "split_out.docx"
    docx_writer.process_docx(path, output, _detect_pesel)

    result = docx.Document(output)
    assert result.paragraphs[0].text == "PESEL: [PESEL 1] powoda."


def test_has_tracked_changes_false_for_clean_doc(sample_docx):
    assert docx_writer.has_tracked_changes(sample_docx) is False


def _add_document_protection(docx_path):
    """Wstrzykuje `w:documentProtection` do word/settings.xml istniejącego
    .docx - python-docx nie ma dla tego API, więc manipulujemy XML wprost,
    tak jak zrobiłby to Word przy włączonej ochronie edycji."""
    from lxml import etree

    from app.pipeline.docx_writer import W_NS

    settings_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:settings xmlns:w="{W_NS}">'
        f'<w:documentProtection w:edit="readOnly" w:enforcement="1"/>'
        f"</w:settings>"
    ).encode("utf-8")

    tmp_path = docx_path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(docx_path, "r") as zin, zipfile.ZipFile(
        tmp_path, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        written_settings = False
        for item in zin.infolist():
            if item.filename == "word/settings.xml":
                zout.writestr(item, settings_xml)
                written_settings = True
            else:
                zout.writestr(item, zin.read(item.filename))
        if not written_settings:
            zout.writestr("word/settings.xml", settings_xml)
    tmp_path.replace(docx_path)
    # potwierdź że XML jest poprawny
    etree.fromstring(settings_xml)


def test_has_document_protection_true_when_present(sample_docx):
    _add_document_protection(sample_docx)
    assert docx_writer.has_document_protection(sample_docx) is True


def test_has_document_protection_false_for_clean_doc(sample_docx):
    assert docx_writer.has_document_protection(sample_docx) is False


def test_remove_document_protection_strips_node_and_reports_change(sample_docx):
    _add_document_protection(sample_docx)
    assert docx_writer.remove_document_protection(sample_docx) is True
    assert docx_writer.has_document_protection(sample_docx) is False
    # drugie wywołanie - nic już nie ma do usunięcia
    assert docx_writer.remove_document_protection(sample_docx) is False


def test_remove_document_protection_noop_when_no_settings_part(sample_docx):
    assert docx_writer.remove_document_protection(sample_docx) is False
