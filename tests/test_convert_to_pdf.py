import pytest

from app.pipeline import convert_to_pdf


def test_can_convert_to_pdf_supported_extensions():
    assert convert_to_pdf.can_convert_to_pdf("umowa.docx")
    assert convert_to_pdf.can_convert_to_pdf("pismo.doc")
    assert convert_to_pdf.can_convert_to_pdf("akt.odt")
    assert not convert_to_pdf.can_convert_to_pdf("skan.pdf")
    assert not convert_to_pdf.can_convert_to_pdf("zdjecie.jpg")


def test_convert_to_pdf_rejects_unsupported_extension():
    with pytest.raises(convert_to_pdf.UnsupportedConversionError):
        convert_to_pdf.convert_to_pdf("skan.pdf")


def test_convert_to_pdf_raises_when_libreoffice_missing(monkeypatch):
    monkeypatch.setattr(convert_to_pdf, "is_libreoffice_available", lambda: False)
    with pytest.raises(convert_to_pdf.LibreOfficeNotAvailableError):
        convert_to_pdf.convert_to_pdf("umowa.docx")


def test_convert_to_pdf_default_output_path_derivation(monkeypatch, tmp_path):
    captured = {}

    def fake_convert_document(input_path, output_path, target_format):
        captured["input_path"] = input_path
        captured["output_path"] = output_path
        captured["target_format"] = target_format
        return output_path

    monkeypatch.setattr(convert_to_pdf, "is_libreoffice_available", lambda: True)
    monkeypatch.setattr(convert_to_pdf, "convert_document", fake_convert_document)

    input_path = tmp_path / "umowa.docx"
    input_path.write_text("tresc")
    convert_to_pdf.convert_to_pdf(input_path)

    assert captured["output_path"] == tmp_path / "umowa.pdf"
    assert captured["target_format"] == "pdf"


def test_convert_many_to_pdf_continues_after_single_failure(monkeypatch, tmp_path):
    def fake_convert_to_pdf(input_path, output_path=None):
        input_path = type(input_path)(input_path)
        if str(input_path).endswith("bad.docx"):
            raise RuntimeError("konwersja nieudana")
        return output_path or input_path.with_suffix(".pdf")

    monkeypatch.setattr(convert_to_pdf, "convert_to_pdf", fake_convert_to_pdf)

    good = tmp_path / "good.docx"
    bad = tmp_path / "bad.docx"
    good.write_text("x")
    bad.write_text("x")

    results = convert_to_pdf.convert_many_to_pdf([good, bad])

    assert results[0][0] == good
    assert results[0][1] == good.with_suffix(".pdf")
    assert results[0][2] is None

    assert results[1][0] == bad
    assert results[1][1] is None
    assert isinstance(results[1][2], RuntimeError)
