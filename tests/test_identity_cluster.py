from app.pipeline.identity_cluster import IdentityRegistry


def test_same_canonical_value_gets_same_number():
    registry = IdentityRegistry()
    first = registry.label_for("phone", "+48 601 234 567")
    second = registry.label_for("phone", "601-234-567")
    assert first == second == "[numer telefonu 1]"


def test_different_values_get_different_numbers():
    registry = IdentityRegistry()
    a = registry.label_for("phone", "601234567")
    b = registry.label_for("phone", "602345678")
    assert a == "[numer telefonu 1]"
    assert b == "[numer telefonu 2]"


def test_counters_are_independent_per_category():
    registry = IdentityRegistry()
    phone = registry.label_for("phone", "601234567")
    email = registry.label_for("email", "a@b.pl")
    assert phone == "[numer telefonu 1]"
    assert email == "[adres e-mail 1]"


def test_amount_always_same_label_without_number():
    registry = IdentityRegistry()
    first = registry.label_for("amount", "5000 zł")
    second = registry.label_for("amount", "12345,67 PLN")
    assert first == second == "[kwota]"


def test_date_category_left_untouched():
    registry = IdentityRegistry()
    assert registry.label_for("date", "12 marca 2026") is None


def test_person_clustered_by_canonical_name():
    registry = IdentityRegistry()
    a = registry.label_for("legal_role_person", "Jan Kowalski")
    b = registry.label_for("legal_role_person", "jan kowalski")
    c = registry.label_for("legal_role_person", "Anna Kowalska")
    assert a == b == "[Osoba 1]"
    assert c == "[Osoba 2]"


def test_registries_are_independent_across_documents():
    registry_a = IdentityRegistry()
    registry_b = IdentityRegistry()
    registry_a.label_for("phone", "601234567")
    label_b = registry_b.label_for("phone", "999888777")
    assert label_b == "[numer telefonu 1]"
