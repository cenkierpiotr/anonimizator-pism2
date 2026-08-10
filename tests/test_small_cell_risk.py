from app.config import AppConfig, CategoryPolicy
from app.pipeline import small_cell_risk
from app.pipeline.identity_cluster import IdentityRegistry


def test_no_warning_when_no_categories_left_visible():
    config = AppConfig()
    config.category_policies["date"] = CategoryPolicy.NUMBER  # brak LEAVE-kategorii
    registry = IdentityRegistry(config)
    registry.label_for("address", "ul. Testowa 1")

    assert small_cell_risk.check(registry, config) == []


def test_warns_on_visible_date_plus_single_rare_category():
    config = AppConfig()  # "date" domyślnie LEAVE
    registry = IdentityRegistry(config)
    registry.label_for("address", "ul. Testowa 1")  # tylko jedno wystąpienie

    warnings = small_cell_risk.check(registry, config)
    assert len(warnings) == 1
    assert "adres" in warnings[0]


def test_no_warning_when_rare_category_is_excluded_type():
    config = AppConfig()
    registry = IdentityRegistry(config)
    registry.label_for("amount", "5000 zł")  # wykluczone z liczenia rzadkości

    assert small_cell_risk.check(registry, config) == []


def test_no_warning_when_category_appears_multiple_times():
    config = AppConfig()
    registry = IdentityRegistry(config)
    registry.label_for("address", "ul. Testowa 1")
    registry.label_for("address", "ul. Inna 2")

    assert small_cell_risk.check(registry, config) == []
