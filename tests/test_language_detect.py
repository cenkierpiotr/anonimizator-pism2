from app.pipeline.language_detect import looks_polish


def test_looks_polish_true_for_polish_legal_text():
    text = (
        "Powód wnosi o zasądzenie od pozwanego kwoty dochodzonej pozwem "
        "wraz z odsetkami ustawowymi za opóźnienie oraz kosztami postępowania."
    )
    assert looks_polish(text) is True


def test_looks_polish_false_for_english_text():
    text = (
        "The plaintiff hereby requests that the court grant judgment in favor "
        "of the plaintiff and award damages together with interest and costs "
        "of the proceedings as set forth in the complaint filed with the court."
    )
    assert looks_polish(text) is False


def test_looks_polish_true_for_short_text_ambiguous():
    assert looks_polish("Krótki tekst.") is True


def test_looks_polish_true_for_empty_text():
    assert looks_polish("") is True
