import numpy as np
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
    # Dla pustego obrazu adaptacyjny retry PSM próbuje wszystkich trybów, bo
    # confidence nigdy nie przekracza progu - upewnijmy się, że kończy się na
    # skończonym, poprawnym wyniku (nie wywala wyjątku, nie zawiesza się).
    assert result.text == "" or result.mean_confidence == 0.0


def test_ocr_attempt_ignores_blank_text_tokens_in_confidence(monkeypatch):
    """Regresja: Tesseract czasem zwraca token z tekstem pustym/samą spacją
    i wysokim `conf` (widmowe wykrycie bez rozpoznanych znaków). Jeśli taki
    token wchodzi do średniej pewności, PSM który nie odczytał NIC może
    dostać wyższą confidence niż PSM, który faktycznie coś przeczytał -
    adaptacyjny retry w run_ocr() wybrałby wtedy ten milczący wynik jako
    "najlepszy", a ostrzeżenie o niskiej jakości OCR nigdy by się nie pojawiło
    mimo braku odczytanego tekstu. Odkryte przy projektowaniu testu na
    celowo zdegradowanym skanie (scripts/gui_tests/s07_ocr_quality.py)."""
    fake_data = {
        "conf": ["-1", "-1", "95", "95"],
        "text": ["", "", " ", ""],
    }

    monkeypatch.setattr(ocr.pytesseract, "image_to_data", lambda *a, **k: fake_data)
    monkeypatch.setattr(ocr.pytesseract, "image_to_string", lambda *a, **k: "")

    result = ocr._ocr_attempt(Image.new("L", (10, 10), 255), "pol+eng", 3)

    assert result.mean_confidence == 0.0
    assert result.is_low_quality


def test_preprocess_binarizes_to_pure_black_and_white():
    img = Image.new("RGB", (800, 200), "white")
    ImageDraw.Draw(img).text((10, 80), "Wyrok w imieniu Rzeczypospolitej", fill="black")

    preprocessed = ocr.preprocess_for_ocr(img)

    assert preprocessed.mode == "L"
    values = set(np.asarray(preprocessed).flatten().tolist())
    assert values <= {0, 255}


def test_preprocess_upscales_low_resolution_images():
    small = Image.new("RGB", (300, 100), "white")
    ImageDraw.Draw(small).text((5, 30), "TEST 12345", fill="black")

    preprocessed = ocr.preprocess_for_ocr(small)

    assert preprocessed.width >= ocr._MIN_OCR_WIDTH_PX


def test_estimate_skew_angle_detects_rotation():
    img = Image.new("RGB", (900, 300), "white")
    ImageDraw.Draw(img).text((20, 100), "UMOWA NAJMU NR 123/2024", fill="black")
    rotated = img.rotate(-3, expand=True, fillcolor="white")

    grayscale = rotated.convert("L")
    angle = ocr.estimate_skew_angle(grayscale)

    # Nie wymagamy dokładnego trafienia (metoda profilu projekcji jest
    # przybliżona) - liczy się, że korekta idzie we właściwym kierunku i
    # rzędu wielkości rzeczywistego przekrzywienia (3 stopnie).
    assert 0.5 <= angle <= 5.0


def test_estimate_skew_angle_near_zero_for_upright_text():
    img = Image.new("RGB", (900, 300), "white")
    ImageDraw.Draw(img).text((20, 100), "UMOWA NAJMU NR 123/2024", fill="black")

    grayscale = img.convert("L")
    angle = ocr.estimate_skew_angle(grayscale)

    assert abs(angle) <= 1.0


def test_run_ocr_recovers_text_from_slightly_rotated_scan():
    img = Image.new("RGB", (900, 300), "white")
    ImageDraw.Draw(img).text((20, 100), "UMOWA NAJMU NR 123 2024", fill="black")
    rotated = img.rotate(-3, expand=True, fillcolor="white")

    result = ocr.run_ocr(rotated)

    assert "UMOWA" in result.text.upper()
    assert "NAJMU" in result.text.upper()


def test_run_ocr_adaptive_psm_retries_on_low_confidence(monkeypatch):
    """Symuluje niską pewność pierwszej próby (PSM domyślny) i sprawdza, że
    kolejne PSM z `_PSM_ATTEMPTS` są faktycznie próbowane, a wynik z wyższym
    confidence wygrywa - bez konieczności posiadania realnego trudnego skanu."""
    attempts = []

    def fake_attempt(image, lang, psm):
        attempts.append(psm)
        # Pierwsza próba (PSM domyślny) słaba, druga dobra, trzecia gorsza.
        confidences = {ocr._PSM_ATTEMPTS[0]: 10.0, ocr._PSM_ATTEMPTS[1]: 90.0, ocr._PSM_ATTEMPTS[2]: 50.0}
        return ocr.OcrResult(text=f"psm-{psm}", mean_confidence=confidences[psm], psm_used=psm)

    monkeypatch.setattr(ocr, "_ocr_attempt", fake_attempt)

    img = Image.new("RGB", (200, 100), "white")
    result = ocr.run_ocr(img)

    # Zatrzymuje się, gdy tylko trafi na wystarczająco pewny wynik (PSM 3) -
    # nie próbuje już trzeciego PSM, bo nie ma po co.
    assert attempts == [ocr._PSM_ATTEMPTS[0], ocr._PSM_ATTEMPTS[1]]
    assert result.psm_used == ocr._PSM_ATTEMPTS[1]
    assert result.mean_confidence == 90.0


def test_run_ocr_skips_retry_when_first_attempt_confident(monkeypatch):
    attempts = []

    def fake_attempt(image, lang, psm):
        attempts.append(psm)
        return ocr.OcrResult(text="ok", mean_confidence=95.0, psm_used=psm)

    monkeypatch.setattr(ocr, "_ocr_attempt", fake_attempt)

    img = Image.new("RGB", (200, 100), "white")
    result = ocr.run_ocr(img)

    assert attempts == [ocr._PSM_ATTEMPTS[0]]
    assert result.mean_confidence == 95.0
