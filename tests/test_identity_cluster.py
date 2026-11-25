from app.config import AppConfig
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


def test_assigned_keys_are_hashed_not_raw_canonical_value():
    registry = IdentityRegistry()
    registry.label_for("phone", "601234567")
    # Klucze rejestru muszą być HMAC-ami (hex sha256 = 64 znaki), nie surową
    # skanonikalizowaną wartością - patrz uzasadnienie w identity_cluster.py.
    assert list(registry._assigned.keys()) == [registry._hashed_key("phone", "601234567")]
    assert "601234567" not in registry._assigned


def test_different_documents_get_different_salts():
    registry_a = IdentityRegistry()
    registry_b = IdentityRegistry()
    assert registry_a._salt != registry_b._salt


def test_date_shift_offset_is_multiple_of_seven_when_enabled():
    config = AppConfig(date_shifting_enabled=True)
    for _ in range(20):
        registry = IdentityRegistry(config)
        assert registry.date_shift_offset_days % 7 == 0


def test_date_shift_offset_zero_when_disabled():
    registry = IdentityRegistry(AppConfig(date_shifting_enabled=False))
    assert registry.date_shift_offset_days == 0


def test_apply_operator_shifts_date_when_enabled():
    config = AppConfig(date_shifting_enabled=True)
    registry = IdentityRegistry(config)
    registry.date_shift_offset_days = 7
    shifted = registry.apply_operator("date", "01.01.2026")
    assert shifted == "08.01.2026"


def test_apply_operator_leaves_date_when_shifting_disabled():
    registry = IdentityRegistry()
    assert registry.apply_operator("date", "01.01.2026") is None
