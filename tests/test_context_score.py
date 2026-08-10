from app.pipeline.context_score import context_boost


def test_boosts_score_when_trigger_word_nearby():
    text = "Pesel osoby to 8O1231O1234, proszę zweryfikować."
    start, end = text.index("8O1231O1234"), text.index("8O1231O1234") + len("8O1231O1234")
    boosted = context_boost(text, start, end, "pesel", 0.4)
    assert boosted == 0.85


def test_no_boost_without_trigger_word():
    text = "Losowy ciąg 8O1231O1234 w treści."
    start, end = text.index("8O1231O1234"), text.index("8O1231O1234") + len("8O1231O1234")
    assert context_boost(text, start, end, "pesel", 0.4) == 0.4


def test_no_boost_for_unknown_category():
    assert context_boost("dowolny tekst", 0, 5, "unknown_category", 0.4) == 0.4


def test_never_lowers_score():
    text = "pesel: 12345678901"
    assert context_boost(text, 7, 18, "pesel", 1.0) == 1.0
