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
