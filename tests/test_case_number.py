from app.detectors.case_number import find_all_with_subtype


def test_all_subtypes_detected():
    text = (
        "Sprawy: I C 123/24, II K 45/24, PR 1 Ds. 123.2026, "
        "RSD-123/26, II SA/Wa 123/24, KIO 123/24, Km 123/24."
    )
    results = find_all_with_subtype(text)
    subtypes = {subtype for _, subtype in results}
    assert subtypes == {
        "cywilne_gospodarcze",
        "karne",
        "prokuratorskie",
        "policyjne",
        "administracyjne",
        "sn_kio",
        "komornicze",
    }


def test_negative_date_not_matched():
    results = find_all_with_subtype("Termin: 12.03.2024.")
    assert results == []


def test_negative_phone_not_matched():
    results = find_all_with_subtype("Tel: 601-234-567.")
    assert results == []
