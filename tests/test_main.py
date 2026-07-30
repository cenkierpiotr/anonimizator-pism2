import docx
import pytest

from app.main import AnonymizeOptions, anonymize_file, anonymize_files


@pytest.fixture
def sample_docx(tmp_path):
    path = tmp_path / "pozew.docx"
    document = docx.Document()
    document.add_paragraph(
        "Powód Jan Kowalski, PESEL 44051401359, tel. 601-234-567, "
        "wnosi pozew przeciwko Annie Nowak."
    )
    document.save(path)
    return path


@pytest.fixture
def sample_txt(tmp_path):
    path = tmp_path / "pismo.txt"
    path.write_text(
        "Wnioskodawca PESEL 44051401359 wnosi o rozpoznanie sprawy.\n\n"
        "Kontakt: 601-234-567.",
        encoding="utf-8",
    )
    return path


def test_anonymize_docx_end_to_end(sample_docx, tmp_path):
    output = tmp_path / "out" / "wynik.docx"
    result = anonymize_file(sample_docx, output)

    assert output.exists()
    assert result.entity_count > 0

    document = docx.Document(output)
    full_text = "\n".join(p.text for p in document.paragraphs)
    assert "44051401359" not in full_text
    assert "601-234-567" not in full_text
    assert "[PESEL 1]" in full_text
    assert "[numer telefonu 1]" in full_text


def test_anonymize_txt_end_to_end(sample_txt, tmp_path):
    output = tmp_path / "wynik.docx"
    result = anonymize_file(sample_txt, output)

    assert output.exists()
    document = docx.Document(output)
    full_text = "\n".join(p.text for p in document.paragraphs)
    assert "44051401359" not in full_text
    assert "601-234-567" not in full_text
    assert "[PESEL 1]" in full_text


def test_anonymize_files_queue_continues_after_single_failure(sample_docx, tmp_path):
    bad_input = tmp_path / "nieznany.xyz"
    bad_input.write_bytes(b"\x00\x01garbage")
    output_dir = tmp_path / "out"

    results = anonymize_files([sample_docx, bad_input], output_dir)

    assert len(results) == 2
    good_input, good_result, good_error = results[0]
    assert good_result is not None
    assert good_error is None
    assert good_result.output_path.exists()

    bad_path, bad_result, bad_error = results[1]
    assert bad_result is None
    assert bad_error is not None
