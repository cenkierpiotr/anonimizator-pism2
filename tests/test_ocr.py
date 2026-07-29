from PIL import Image, ImageDraw

from app.pipeline import ocr


def test_run_ocr_extracts_text(tmp_path):
    img = Image.new("RGB", (800, 200), "white")
    ImageDraw.Draw(img).text((10, 80), "PESEL 44051401359 powoda", fill="black")

    result = ocr.run_ocr(img)

    assert "PESEL" in result.text
    assert result.mean_confidence > 0


def test_low_quality_flag_on_blank_image():
    blank = Image.new("RGB", (200, 200), "white")
    result = ocr.run_ocr(blank)
    assert result.is_low_quality
