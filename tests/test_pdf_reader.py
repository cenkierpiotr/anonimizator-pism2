from fpdf import FPDF
from PIL import Image, ImageDraw

from app.pipeline import pdf_reader


def test_text_layer_pdf_returns_text(tmp_path):
    path = tmp_path / "text.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, "Powod Jan Kowalski, PESEL 44051401359, wnosi o zaplate.")
    pdf.output(str(path))

    document = pdf_reader.open_pdf(path)
    pages = pdf_reader.read_pages(document)

    assert len(pages) == 1
    assert pages[0].text is not None
    assert "PESEL" in pages[0].text
    assert pages[0].image is None


def test_scanned_pdf_returns_image_for_ocr(tmp_path):
    image_path = tmp_path / "scan.png"
    img = Image.new("RGB", (800, 200), "white")
    ImageDraw.Draw(img).text((10, 80), "PESEL 44051401359 powoda", fill="black")
    img.save(image_path)

    pdf_path = tmp_path / "scan.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.image(str(image_path), x=10, y=10, w=180)
    pdf.output(str(pdf_path))

    document = pdf_reader.open_pdf(pdf_path)
    pages = pdf_reader.read_pages(document)

    assert len(pages) == 1
    assert pages[0].text is None
    assert pages[0].image is not None
