from app.pipeline.canonicalize import canonicalize


def test_phone_variants_canonicalize_the_same():
    assert canonicalize("phone", "+48 601 234 567") == canonicalize("phone", "601-234-567")
    assert canonicalize("phone", "0048601234567") == canonicalize("phone", "601 234 567")


def test_email_case_insensitive():
    assert canonicalize("email", "Jan.Kowalski@Example.COM") == "jan.kowalski@example.com"


def test_pesel_strips_separators():
    assert canonicalize("pesel", "440514 01359") == "44051401359"


def test_iban_uppercased_and_stripped():
    assert canonicalize("iban", "pl 61 1090 1014 0000 0712 1981 2874") == canonicalize(
        "iban", "PL61109010140000071219812874"
    )


def test_person_name_diacritics_and_case_insensitive():
    assert canonicalize("legal_role_person", "Łukasz Żółć") == canonicalize(
        "legal_role_person", "łukasz żółć"
    )


def test_default_falls_back_to_casefold_and_trim():
    assert canonicalize("unknown_category", "  Some Value  ") == "some value"
