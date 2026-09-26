from odf.opendocument import OpenDocumentText
from odf.style import Style, TextProperties
from odf.text import P, Span

from app.detectors.pesel import detector as pesel_detector
from app.pipeline import odt_reader


def _detect_pesel(text: str) -> list[tuple[int, int, str]]:
    return [(m.start, m.end, "[PESEL 1]") for m in pesel_detector.find_all(text)]


def test_process_odt_simple_paragraph(tmp_path):
    input_path = tmp_path / "input.odt"
    document = OpenDocumentText()
    document.text.addElement(P(text="Powod, PESEL 44051401359, wnosi o..."))
    document.save(str(input_path))

    output_path = tmp_path / "output.odt"
    changed = odt_reader.process_odt(input_path, output_path, _detect_pesel)

    assert changed == 1
    result_text = odt_reader.extract_all_text(output_path)
    assert result_text == "Powod, PESEL [PESEL 1], wnosi o..."


def test_process_odt_split_across_spans(tmp_path):
    input_path = tmp_path / "split.odt"
    document = OpenDocumentText()
    style = Style(name="Bold", family="text")
    style.addElement(TextProperties(fontweight="bold"))
    document.automaticstyles.addElement(style)

    p = P()
    p.addText("PESEL: 440514")
    span = Span(stylename=style)
    span.addText("01359")
    p.addElement(span)
    p.addText(" powoda.")
    document.text.addElement(p)
    document.save(str(input_path))

    output_path = tmp_path / "split_out.odt"
    odt_reader.process_odt(input_path, output_path, _detect_pesel)

    assert odt_reader.extract_all_text(output_path) == "PESEL: [PESEL 1] powoda."
