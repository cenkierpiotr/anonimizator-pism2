from app.detectors import ocr_tolerance
from app.detectors.nip import detector as nip_detector
from app.detectors.pesel import detector as pesel_detector
from app.detectors.pesel import is_valid_pesel


def test_generate_variants_substitutes_confusable_chars():
    variants = ocr_tolerance.generate_variants("8O1231O1234")
    assert "80123101234" in variants
    assert "8O1231O1234" not in variants


def test_generate_variants_empty_when_no_confusables():
    assert ocr_tolerance.generate_variants("34679") == []


def test_validates_with_ocr_correction_true_for_corrected_pesel():
    # PESEL poprawny: 44051401359 (wygenerowany i zweryfikowany is_valid_pesel).
    correct = "44051401359"
    assert is_valid_pesel(correct)
    mangled = correct[:2] + "O" + correct[3:]
    # "O" podstawione w miejscu cyfry powoduje, że surowy tekst nie przechodzi
    # walidacji wprost, ale jeden z wariantów OCR-poprawionych powinien.
    assert not is_valid_pesel(mangled)
    assert ocr_tolerance.validates_with_ocr_correction(mangled, is_valid_pesel)


def test_validates_with_ocr_correction_false_when_no_variant_helps():
    assert not ocr_tolerance.validates_with_ocr_correction("601234567", is_valid_pesel)


def test_detector_find_all_catches_letter_substituted_for_digit_in_pesel():
    # Regression: czysto cyfrowy `pattern` (\d{11}) w ogóle nie dopasowuje
    # tekstu, w którym OCR podstawił literę w miejsce cyfry - bez osobnego
    # `fuzzy_pattern` w Detector.find_all() ten przypadek nigdy nie trafiał
    # nawet do walidacji checksumem (patrz `Detector.fuzzy_pattern`).
    correct = "44051401359"
    assert is_valid_pesel(correct)
    mangled = correct[:2] + "O" + correct[3:]
    matches = pesel_detector.find_all(f"Pesel: {mangled} widnieje w aktach.")
    assert len(matches) == 1
    assert matches[0].value == mangled
    assert matches[0].score < 1.0


def test_detector_find_all_catches_letter_substituted_for_digit_in_nip():
    mangled = "526O001246"  # poprawny NIP 5260001246 z "0" podmienionym na "O"
    matches = nip_detector.find_all(f"NIP: {mangled} w umowie.")
    assert len(matches) == 1
    assert matches[0].value == mangled
    assert matches[0].score < 1.0
