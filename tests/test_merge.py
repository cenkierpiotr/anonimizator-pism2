from app.pipeline.merge import Detection, resolve


def test_no_overlap_keeps_all():
    detections = [
        Detection(0, 5, "phone", "12345", priority=10),
        Detection(10, 15, "email", "a@b.pl", priority=10),
    ]
    result = resolve(detections)
    assert result == sorted(detections, key=lambda d: d.start)


def test_partial_overlap_higher_priority_wins():
    # "Ds. 123.2026" (sygnatura) kontra fragment dopasowany przez detektor daty
    case_number = Detection(0, 12, "case_number", "Ds. 123.2026", priority=100)
    date_fragment = Detection(4, 12, "date", "123.2026", priority=50)

    result = resolve([case_number, date_fragment])

    assert result == [case_number]


def test_nested_span_kept_when_marked_nestable():
    address = Detection(0, 30, "address", "ul. Polna 5, 00-950 Warszawa", priority=80)
    city = Detection(20, 28, "city", "Warszawa", priority=60, nestable=True)

    result = resolve([address, city])

    assert address in result
    assert city in result
    assert len(result) == 2


def test_partial_overlap_not_nested_drops_lower_priority():
    a = Detection(0, 10, "a", "x", priority=90)
    b = Detection(5, 15, "b", "y", priority=50)

    result = resolve([a, b])

    assert result == [a]


def test_exact_duplicate_span_keeps_higher_priority_only():
    a = Detection(0, 10, "pesel", "44051401359", priority=100)
    b = Detection(0, 10, "ner_person", "44051401359", priority=40)

    result = resolve([a, b])

    assert result == [a]
