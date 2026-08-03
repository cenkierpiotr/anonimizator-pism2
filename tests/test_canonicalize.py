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


def test_person_name_inflected_forms_canonicalize_the_same():
    """Regresja: 'Annie Nowak' (celownik) i 'Anna Nowak' (mianownik) to ta sama
    osoba wykryta przez NER w dwoch roznych formach gramatycznych - powinny
    dostac ten sam klucz kanoniczny (i wiec ten sam numer [Osoba N])."""
    nominative = canonicalize("legal_role_person", "Anna Nowak")
    dative = canonicalize("legal_role_person", "Annie Nowak")
    accusative = canonicalize("legal_role_person", "Annę Nowak")
    genitive = canonicalize("legal_role_person", "Anny Nowak")
    assert nominative == dative == accusative == genitive

    assert canonicalize("legal_role_person", "Jan Kowalski") == canonicalize(
        "legal_role_person", "Janowi Kowalskiemu"
    )
    assert canonicalize("legal_role_person", "Jan Kowalski") == canonicalize(
        "legal_role_person", "Janem Kowalskim"
    )


def test_person_name_different_surnames_stay_distinct():
    """Straznik przed nadgorliwym 'sklejaniem': rozne nazwiska (nawet o
    podobnym wzorcu fleksyjnym) nie powinny dostac tego samego klucza."""
    assert canonicalize("legal_role_person", "Jan Kowalski") != canonicalize(
        "legal_role_person", "Jan Kowalczyk"
    )
    assert canonicalize("legal_role_person", "Anna Nowak") != canonicalize(
        "legal_role_person", "Anna Nowicka"
    )
