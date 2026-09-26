import docx

from app.pipeline import docx_writer, leak_check


def _detect_pesel(text: str) -> list[tuple[int, int, str]]:
    from app.detectors.pesel import detector as pesel_detector

    return [(m.start, m.end, "[PESEL 1]") for m in pesel_detector.find_all(text)]


def test_leak_check_clean_after_anonymization(tmp_path):
    input_path = tmp_path / "input.docx"
    document = docx.Document()
    document.add_paragraph("PESEL 44051401359 powoda.")
    document.save(input_path)

    output_path = tmp_path / "output.docx"
    docx_writer.process_docx(input_path, output_path, _detect_pesel)

    assert leak_check.check_docx(output_path) == []
    leak_check.assert_clean(output_path)  # nie powinno rzucić wyjątku


def test_leak_check_detects_forgotten_pesel_in_footer(tmp_path):
    """Symuluje najgorszy scenariusz z planu: dane przetrwały w miejscu,
    które nie zostało objęte podmianą (tu: brak detekcji w ogóle)."""
    input_path = tmp_path / "input.docx"
    document = docx.Document()
    document.add_paragraph("PESEL 44051401359 powoda.")
    document.save(input_path)

    output_path = tmp_path / "output_leaky.docx"

    def _no_op_detect(text: str) -> list[tuple[int, int, str]]:
        return []

    docx_writer.process_docx(input_path, output_path, _no_op_detect)

    findings = leak_check.check_docx(output_path)
    assert len(findings) == 1
    assert findings[0].detector_name == "pesel"

    try:
        leak_check.assert_clean(output_path)
        assert False, "assert_clean powinien rzucić LeakDetectedError"
    except leak_check.LeakDetectedError:
        pass
