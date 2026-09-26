"""Testy dymne dla generatora golden dataset (`scripts/golden_dataset.py`).

Nie testujemy tu samych liczb recall/precision (to narzędzie oceny jakości do
ręcznego uruchamiania, nie bramka CI - patrz plan, sekcja "Weryfikacja" i
docstring modułu) - tylko to, że generator produkuje wewnętrznie spójne dane:
poprawne checksumy i offsety ground truth faktycznie wskazujące na wstawioną
wartość w tekście dokumentu.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

import golden_dataset as gd

from app.detectors.nip import is_valid_nip
from app.detectors.pesel import is_valid_pesel


def test_generate_dataset_produces_requested_number_of_docs():
    docs = gd.generate_dataset(n=8, seed=1)
    assert len(docs) == 8
    assert {d.doc_type for d in docs} <= set(gd._TEMPLATES)

    docs_all = gd.generate_dataset(n=len(gd._TEMPLATES), seed=1)
    assert {d.doc_type for d in docs_all} == set(gd._TEMPLATES)


def test_ground_truth_spans_match_inserted_values():
    docs = gd.generate_dataset(n=12, seed=3)
    for doc in docs:
        for entity in doc.entities:
            assert doc.text[entity.start : entity.end] == entity.value


def test_generated_pesel_and_nip_have_valid_checksums():
    rng = random.Random(99)
    for _ in range(20):
        assert is_valid_pesel(gd.gen_pesel(rng))
        assert is_valid_nip(gd.gen_nip(rng))


def test_generated_iban_passes_detector_validation():
    from app.detectors.iban import is_valid_iban

    rng = random.Random(123)
    for _ in range(20):
        assert is_valid_iban(gd.gen_iban(rng))


def test_generate_dataset_is_deterministic_for_same_seed():
    docs_a = gd.generate_dataset(n=5, seed=42)
    docs_b = gd.generate_dataset(n=5, seed=42)
    assert [d.text for d in docs_a] == [d.text for d in docs_b]


def test_evaluate_runs_real_pipeline_and_reports_full_recall_on_default_set():
    """Confidence check że cały pipeline (`detect_in_text`) faktycznie widzi
    ground truth generatora - jeśli szablon kiedyś przestanie pasować do
    wzorców detektorów (np. zmiana regexu w `legal_roles.py`), ten test to
    wyłapie zanim ktoś odkryje to dopiero w raporcie recall/precision."""
    docs = gd.generate_dataset(n=6, seed=5)
    stats, total_detections, total_tp = gd.evaluate(docs)

    assert total_detections > 0
    for category, s in stats.items():
        assert s.matched_count == s.ground_truth_count, f"recall < 100% dla kategorii {category}"
