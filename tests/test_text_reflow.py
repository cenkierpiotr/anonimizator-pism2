from app.pipeline.text_reflow import reflow_lines


def test_wrapped_sentence_joined_into_one_paragraph():
    text = (
        "W dniu 15 stycznia 2026 roku pozwany Jan Kowalski zamieszkaly w Warszawie przy ulicy\r\n"
        "Marszalkowskiej 10 zawarl umowe najmu lokalu z powodem Anna Nowak na okres dwunastu\r\n"
        "miesiecy za czynsz w wysokosci 3000 zlotych miesiecznie."
    )
    result = reflow_lines(text)
    assert result == (
        "W dniu 15 stycznia 2026 roku pozwany Jan Kowalski zamieszkaly w Warszawie przy ulicy "
        "Marszalkowskiej 10 zawarl umowe najmu lokalu z powodem Anna Nowak na okres dwunastu "
        "miesiecy za czynsz w wysokosci 3000 zlotych miesiecznie."
    )


def test_two_sentences_become_two_paragraphs_without_blank_line():
    text = (
        "Pierwsze zdanie zawija sie\r\nna dwoch liniach.\r\n"
        "Drugie zdanie tez tu jest."
    )
    result = reflow_lines(text)
    assert result == (
        "Pierwsze zdanie zawija sie na dwoch liniach.\n\n"
        "Drugie zdanie tez tu jest."
    )


def test_blank_line_forces_paragraph_break_even_without_punctuation():
    text = "Pierwszy fragment bez kropki\n\nDrugi fragment"
    result = reflow_lines(text)
    assert result == "Pierwszy fragment bez kropki\n\nDrugi fragment"


def test_hyphenated_word_split_across_lines_is_rejoined():
    text = "Przedmiotem postepowania jest wynagrodzenie za wykonane przed-\nmiotowe roboty budowlane."
    result = reflow_lines(text)
    assert "przedmiotowe roboty budowlane" in result
    assert "przed-" not in result


def test_empty_text_returns_empty_string():
    assert reflow_lines("") == ""


def test_single_line_without_terminal_punctuation():
    result = reflow_lines("Tylko jedna linia bez kropki")
    assert result == "Tylko jedna linia bez kropki"
