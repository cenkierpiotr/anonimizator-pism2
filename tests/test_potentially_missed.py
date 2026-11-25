from app.pipeline.detect_all import find_potentially_missed
from app.pipeline.merge import Detection


def test_flags_capitalized_token_not_at_sentence_start_and_uncovered():
    text = "Powód spotkał się z Zubrowskim w kancelarii wczoraj."
    missed = find_potentially_missed(text, resolved=[])

    assert any("Zubrowskim" in snippet for snippet in missed)


def test_ignores_token_at_sentence_start():
    text = "Powód wniósł pozew. Zubrowski się nie zjawił."
    missed = find_potentially_missed(text, resolved=[])

    assert not any("Zubrowski" in snippet for snippet in missed)


def test_ignores_token_already_covered_by_detection():
    text = "Powód spotkał się z Zubrowskim w kancelarii."
    start = text.index("Zubrowskim")
    end = start + len("Zubrowskim")
    covered = [Detection(start, end, "legal_role_person", "Zubrowskim", priority=60)]

    missed = find_potentially_missed(text, resolved=covered)

    assert not any("Zubrowskim" in snippet for snippet in missed)


def test_ignores_common_capitalized_legal_words():
    text = "Sprawę skierowano do Sądu Rejonowego dla rozpoznania."
    missed = find_potentially_missed(text, resolved=[])

    assert not any("Sądu" in snippet for snippet in missed)


def test_deduplicates_repeated_token():
    text = "Spotkał się z Zubrowskim rano. Potem znów z Zubrowskim wieczorem."
    missed = find_potentially_missed(text, resolved=[])

    assert len(missed) == 1
