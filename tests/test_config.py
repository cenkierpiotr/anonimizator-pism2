from app.config import AppConfig, CategoryPolicy, DEFAULT_CATEGORY_POLICIES, GlinerConfig


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


def test_gliner_enabled_by_default():
    # Domyślnie WŁĄCZONE od Fazy 5 (23.09.2026) - patrz uzasadnienie w
    # komentarzu przy AppConfig.gliner_enabled w app/config.py.
    config = AppConfig()
    assert config.gliner_enabled is True


def test_gliner_config_defaults_present_and_configurable():
    config = AppConfig()
    assert isinstance(config.gliner, GlinerConfig)
    assert config.gliner.model_path
    assert 0.0 <= config.gliner.confidence_threshold <= 1.0

    config.gliner.model_path = "/inna/sciezka/model.onnx"
    assert AppConfig().gliner.model_path != "/inna/sciezka/model.onnx"
