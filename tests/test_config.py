from app.config import AppConfig, CategoryPolicy, DEFAULT_CATEGORY_POLICIES


def test_default_policy_for_identifying_categories_is_number():
    config = AppConfig()
    assert config.policy_for("phone") is CategoryPolicy.NUMBER
    assert config.policy_for("pesel") is CategoryPolicy.NUMBER
    assert config.policy_for("legal_role_person") is CategoryPolicy.NUMBER


def test_date_defaults_to_leave():
    config = AppConfig()
    assert config.policy_for("date") is CategoryPolicy.LEAVE


def test_amount_defaults_to_no_number():
    config = AppConfig()
    assert config.policy_for("amount") is CategoryPolicy.NO_NUMBER


def test_unknown_category_defaults_to_number():
    config = AppConfig()
    assert config.policy_for("jakas_nieznana_kategoria") is CategoryPolicy.NUMBER


def test_custom_config_overrides_default_without_mutating_global():
    config = AppConfig()
    config.category_policies["date"] = CategoryPolicy.NUMBER
    assert config.policy_for("date") is CategoryPolicy.NUMBER
    assert DEFAULT_CATEGORY_POLICIES["date"] is CategoryPolicy.LEAVE


def test_ocr_and_ner_defaults():
    config = AppConfig()
    assert config.ocr.languages == "pol+eng"
    assert config.ner.model_name == "pl_core_news_md"
