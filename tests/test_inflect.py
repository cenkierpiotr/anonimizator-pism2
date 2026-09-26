from app.detectors.inflect import generate_full_name_forms, generate_surname_forms


def test_ski_surname_generates_case_forms():
    forms = generate_surname_forms("Kowalski")
    assert "Kowalski" in forms
    assert "Kowalskiego" in forms
    assert "Kowalskiemu" in forms
    assert "Kowalskim" in forms


def test_ska_surname_generates_case_forms():
    forms = generate_surname_forms("Kowalska")
    assert "Kowalska" in forms
    assert "Kowalskiej" in forms
    assert "Kowalską" in forms


def test_icz_surname_generates_case_forms():
    forms = generate_surname_forms("Ratajewicz")
    assert "Ratajewicza" in forms
    assert "Ratajewiczowi" in forms
    assert "Ratajewiczem" in forms


def test_consonant_ending_surname_generates_case_forms():
    forms = generate_surname_forms("Nowak")
    assert "Nowaka" in forms
    assert "Nowakowi" in forms
    assert "Nowakiem" in forms


def test_empty_surname_returns_empty_set():
    assert generate_surname_forms("") == set()


def test_full_name_keeps_given_name_unchanged():
    forms = generate_full_name_forms("Jan Kowalski")
    assert "Jan Kowalskiego" in forms
    assert "Jan Kowalskiemu" in forms
    assert all(f.startswith("Jan ") for f in forms)


def test_single_word_full_name_falls_back_to_surname_forms():
    forms = generate_full_name_forms("Kowalski")
    assert forms == generate_surname_forms("Kowalski")
