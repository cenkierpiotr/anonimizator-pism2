"""Ewaluacja warstwy GLiNER: delta recall vs baseline (regex+checksum/NER),
per kategoria (Grupa A/B), na tekście czystym i zaszumionym OCR.

Równoległy do `golden_dataset.py` (reużywa jego generator + `IdentityRegistry`)
- NIE modyfikuje `tests/golden/test_golden_dataset.py` (to explicite test dymny
generatora, nie bramka jakości/ewaluacji GLiNER). Patrz plan
`.claude/plans/encapsulated-splashing-panda.md`, sekcja "Ewaluacja".

Metodologia:
1. Generujemy golden dataset (`golden_dataset.generate_dataset`) w dwóch
   wariantach: czysty i zaszumiony OCR (ten sam dokument, ten sam seed;
   augmentacja przez `ocr_noise_augment.augment_document`, ratio=1.0 - żeby
   KAŻDA encja Grupy B miała szansę zostać zaszumiona, bo inaczej przy małej
   próbce delta byłaby rozmyta losowością).
2. Na każdym dokumencie wołamy `detect_in_text` DWA razy:
   - baseline: bez `gliner_model` (regex+checksum+NER, jak dziś produkcyjnie),
   - z GLiNER: z prawdziwym modelem wczytanym przez `gliner_layer.load_model()`.
   `uncertain_collector` przekazywany w obu wołaniach - liczymy różnicę
   długości (i wpisy z prefiksem "[GLiNER]") jako metrykę szumu.
3. Recall "z GLiNER" liczymy jako: pokrycie ground truth przez finalne
   `Replacement` (identyczne w obu wołaniach - GLiNER NIGDY nie zmienia
   `resolve()`/`Replacement`, patrz zasada bezpieczeństwa) ORAZ przez surowe
   kandydaty GLiNER (`gliner_layer.find_gliner_candidates`) po odfiltrowaniu
   tych pokrywających się z już zaakceptowaną detekcją - to jest DOSŁOWNIE ta
   sama reguła, którą `detect_all._append_gliner_uncertain` stosuje przed
   dopisaniem do `uncertain_collector`; liczymy tu na surowych spanach (nie na
   sformatowanym stringu z collectora), bo string nie niesie offsetów.
4. Kluczowa metryka: delta recall (z GLiNER - baseline) na wariancie OCR.

Uruchomienie:

    source .venv/bin/activate
    python3 scripts/eval_gliner_recall.py --n 40 \\
        --model /config/gliner-anonimizator-pl-finetune/models/anonPL-300M/onnx/model_quantized.onnx \\
        --out /config/gliner-anonimizator-pl-finetune/results/gliner_recall_eval.md
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.pipeline import gliner_layer
from app.pipeline.detect_all import Replacement, detect_in_text
from app.pipeline.identity_cluster import IdentityRegistry
from app.detectors.ocr_tolerance import CONFUSABLES
from golden_dataset import GoldenDocument, GroundTruthEntity, generate_dataset
from ocr_noise_augment import GROUP_B_CATEGORIES

# Grupy z planu głównego (sekcja "Taksonomia GLiNER: 12 z 25 kategorii").
GROUP_A_CATEGORIES = frozenset(
    {
        "legal_role_person",
        "institution",
        "address",
        "case_number",
        "notarial_act",
        "usc_act",
        "poswiadczenie_dziedziczenia",
        "rejestr_spadkowy",
    }
)
GROUP_B_CATEGORIES_EVAL = GROUP_B_CATEGORIES  # pesel/nip/regon/iban/id_card/vehicle_vin


def _group_of(category: str) -> str:
    if category in GROUP_A_CATEGORIES:
        return "A"
    if category in GROUP_B_CATEGORIES_EVAL:
        return "B"
    return "poza-zakresem"  # date/amount/phone/email/... - nieuczone przez GLiNER


def _spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return max(a_start, b_start) < min(a_end, b_end)


@dataclass
class CatStats:
    ground_truth: int = 0
    matched_baseline: int = 0
    matched_with_gliner: int = 0

    @property
    def recall_baseline(self) -> float:
        return self.matched_baseline / self.ground_truth if self.ground_truth else float("nan")

    @property
    def recall_with_gliner(self) -> float:
        return self.matched_with_gliner / self.ground_truth if self.ground_truth else float("nan")


def _doc_from_record(record: dict) -> GoldenDocument:
    """`augment_document` dopisuje opcjonalny klucz `ocr_noised` do encji, którego
    `GroundTruthEntity` nie ma w konstruktorze - odfiltrowujemy go tu."""
    return GoldenDocument(
        doc_id=record["doc_id"],
        doc_type=record["doc_type"],
        text=record["text"],
        entities=[
            GroundTruthEntity(category=e["category"], start=e["start"], end=e["end"], value=e["value"])
            for e in record["entities"]
        ],
    )


def _record_from_doc(doc: GoldenDocument) -> dict:
    from dataclasses import asdict

    return {
        "doc_id": doc.doc_id,
        "doc_type": doc.doc_type,
        "text": doc.text,
        "entities": [asdict(e) for e in doc.entities],
    }


def _severe_noisy_value(value: str, rng: random.Random, max_substitutions: int) -> str:
    """Jak `ocr_noise_augment._noisy_value`, ale z konfigurowalnym, WYŻSZYM
    limitem jednoczesnych podstawień. Ważne dla tej ewaluacji: produkcyjna
    tolerancja OCR (`app/detectors/ocr_tolerance.py::_MAX_SUBSTITUTIONS = 2`)
    domyślnie NAPRAWIA do 2 jednoczesnych podstawień w checksumie - a
    `ocr_noise_augment.py` (do generacji danych treningowych) też domyślnie
    stosuje maksymalnie 2, więc szum wygenerowany TĄ SAMĄ metodą co dane
    treningowe byłby w 100% odzyskiwany przez baseline (zerowa delta, zero
    sygnału). Żeby zmierzyć realną wartość GLiNER jako "drugiej szansy" tam,
    gdzie checksum OSTATECZNIE zawodzi (zgodnie z planem, sekcja Grupa B),
    ewaluacja celowo używa silniejszego szumu (domyślnie 3+ podstawień) -
    to POZA zasięgiem korekcji `ocr_tolerance.generate_variants`."""
    positions = [i for i, ch in enumerate(value) if ch in CONFUSABLES]
    if not positions:
        return value
    k = min(max_substitutions, len(positions))
    if k <= 0:
        return value
    chosen = rng.sample(positions, k)
    chars = list(value)
    for pos in chosen:
        # Wszystkie wartości Grupy B są same cyfry albo same WIELKIE litery
        # (PESEL/NIP/REGON/IBAN - cyfry; id_card/vehicle_vin - wielkie litery +
        # cyfry, alfabet VIN nawet nie ma I/O/Q) - `CONFUSABLES["1"]` zawiera
        # też małe "l", które podstawione w VIN/id_card wywołałoby KeyError w
        # walidatorze checksumu (nieoczekiwany znak) zamiast realistycznego
        # "OCR pomylił cyfrę z literą". Odfiltrowujemy warianty małych liter.
        options = [o for o in CONFUSABLES[chars[pos]] if not o.islower()]
        if not options:
            continue
        chars[pos] = rng.choice(options)
    return "".join(chars)


def make_severe_ocr_variant(
    record: dict, rng: random.Random, ratio: float, max_substitutions: int
) -> dict:
    """Analogicznie do `ocr_noise_augment.augment_document`, ale przez
    `_severe_noisy_value` (patrz docstring tam) - reużywa tę samą strategię
    (podstawienia znak-na-znak z `CONFUSABLES`, offsety bez zmian), tylko z
    większym `max_substitutions`, żeby faktycznie przekroczyć zdolność
    korekcji produkcyjnego `ocr_tolerance.py` na części próbki."""
    text = record["text"]
    entities = record["entities"]
    noisy_entities = [dict(e) for e in entities]

    for entity in sorted(noisy_entities, key=lambda e: e["start"], reverse=True):
        if entity["category"] not in GROUP_B_CATEGORIES:
            continue
        if rng.random() >= ratio:
            continue
        original = entity["value"]
        noisy = _severe_noisy_value(original, rng, max_substitutions)
        if noisy == original:
            continue
        assert len(noisy) == len(original)
        start, end = entity["start"], entity["end"]
        assert text[start:end] == original, f"rozjazd offsetu w {record['doc_id']}: {entity}"
        text = text[:start] + noisy + text[end:]
        entity["value"] = noisy
        entity["ocr_noised"] = True

    return {
        "doc_id": f"{record['doc_id']}-ocr",
        "doc_type": record["doc_type"],
        "text": text,
        "entities": noisy_entities,
    }


def evaluate_variant(
    docs: list[GoldenDocument],
    model,
    threshold: float,
) -> tuple[dict[str, CatStats], int, int, float, float]:
    """Zwraca (stats per kategoria, liczba wpisów uncertain BEZ GLiNER,
    liczba wpisów uncertain Z GLiNER, czas przetwarzania baseline [s],
    czas przetwarzania z GLiNER [s]) - zsumowane po wszystkich dokumentach."""
    stats: dict[str, CatStats] = {}
    total_uncertain_baseline = 0
    total_uncertain_gliner = 0
    time_baseline = 0.0
    time_gliner = 0.0

    for doc in docs:
        # --- baseline: bez GLiNER ---
        registry_b = IdentityRegistry()
        uncertain_b: list[str] = []
        t0 = time.perf_counter()
        replacements_b: list[Replacement] = detect_in_text(
            doc.text, registry_b, uncertain_collector=uncertain_b
        )
        time_baseline += time.perf_counter() - t0
        total_uncertain_baseline += len(uncertain_b)

        # --- z GLiNER (przez oficjalne API detect_in_text, jak produkcyjnie) ---
        registry_g = IdentityRegistry()
        uncertain_g: list[str] = []
        t0 = time.perf_counter()
        replacements_g: list[Replacement] = detect_in_text(
            doc.text,
            registry_g,
            gliner_model=model,
            gliner_threshold=threshold,
            uncertain_collector=uncertain_g,
        )
        time_gliner += time.perf_counter() - t0
        total_uncertain_gliner += len(uncertain_g)

        # Bezpieczeństwo (patrz zasada z gliner_layer.py): GLiNER NIGDY nie
        # wpływa na resolve()/Replacement - finalne podmiany muszą być
        # identyczne z baseline niezależnie od gliner_model.
        assert replacements_b == replacements_g, (
            f"NARUSZENIE ZASADY BEZPIECZEŃSTWA w {doc.doc_id}: GLiNER zmienił "
            "finalne Replacement - to nie powinno być możliwe."
        )

        # Surowe kandydaty GLiNER, odfiltrowane wg TEJ SAMEJ reguły co
        # `detect_all._append_gliner_uncertain` (nie pokrywają się z żadną już
        # zaakceptowaną detekcją) - potrzebne tu z offsetami, bo string w
        # uncertain_collector ich nie niesie.
        covered = [(r.start, r.end) for r in replacements_b]
        try:
            raw_candidates = gliner_layer.find_gliner_candidates(doc.text, model, threshold=threshold)
        except gliner_layer.GlinerUnavailableError:
            raw_candidates = []
        new_candidates = [
            c
            for c in raw_candidates
            if not any(cs < c.end and c.start < ce for cs, ce in covered)
        ]

        for gt in doc.entities:
            cat_stats = stats.setdefault(gt.category, CatStats())
            cat_stats.ground_truth += 1
            matched_baseline = any(_spans_overlap(gt.start, gt.end, r.start, r.end) for r in replacements_b)
            if matched_baseline:
                cat_stats.matched_baseline += 1
                cat_stats.matched_with_gliner += 1
            elif any(_spans_overlap(gt.start, gt.end, c.start, c.end) for c in new_candidates):
                cat_stats.matched_with_gliner += 1

    return stats, total_uncertain_baseline, total_uncertain_gliner, time_baseline, time_gliner


def _group_rollup(stats: dict[str, CatStats], group: str) -> CatStats:
    rollup = CatStats()
    for category, s in stats.items():
        if _group_of(category) != group:
            continue
        rollup.ground_truth += s.ground_truth
        rollup.matched_baseline += s.matched_baseline
        rollup.matched_with_gliner += s.matched_with_gliner
    return rollup


def format_report(
    n_docs: int,
    seed: int,
    model_path: str,
    threshold: float,
    clean_result: tuple,
    ocr_result: tuple,
) -> str:
    lines = [
        "# Ewaluacja warstwy GLiNER - delta recall vs baseline",
        "",
        f"Wygenerowano {n_docs} syntetycznych dokumentów (seed={seed}) w dwóch wariantach "
        f"(czysty + zaszumiony OCR, ratio=1.0 na encjach Grupy B). Model: `{model_path}` "
        f"(threshold={threshold}).",
        "",
        "Legenda: 'baseline' = regex+checksum+NER (bez GLiNER, jak dziś produkcyjnie). "
        "'z GLiNER' = baseline + kandydaty GLiNER, które nie pokrywają się z żadną już "
        "zaakceptowaną detekcją (dokładnie ta reguła, którą stosuje "
        "`detect_all._append_gliner_uncertain` przy dopisywaniu do `uncertain_collector`). "
        "Recall GLiNER liczony na tych właśnie kandydatach, nie na finalnym "
        "`Replacement` (do którego GLiNER z zasady nigdy nie trafia).",
        "",
    ]

    for variant_name, result in (("Tekst czysty", clean_result), ("Tekst zaszumiony OCR", ocr_result)):
        stats, unc_baseline, unc_gliner, t_baseline, t_gliner = result
        lines += [
            f"## {variant_name}",
            "",
            "| Kategoria | Grupa | Ground truth | Recall baseline | Recall z GLiNER | Delta |",
            "|---|---|---:|---:|---:|---:|",
        ]
        for category in sorted(stats):
            s = stats[category]
            group = _group_of(category)
            rb = s.recall_baseline
            rg = s.recall_with_gliner
            delta = (rg - rb) * 100 if s.ground_truth else float("nan")
            rb_s = f"{rb * 100:.1f}%" if s.ground_truth else "n/d"
            rg_s = f"{rg * 100:.1f}%" if s.ground_truth else "n/d"
            delta_s = f"{delta:+.1f}pp" if s.ground_truth else "n/d"
            lines.append(f"| {category} | {group} | {s.ground_truth} | {rb_s} | {rg_s} | {delta_s} |")

        rollup_a = _group_rollup(stats, "A")
        rollup_b = _group_rollup(stats, "B")
        lines += ["", "### Zbiorczo per grupa", ""]
        for label, rollup in (("Grupa A (kontekstowe)", rollup_a), ("Grupa B (identyfikatory)", rollup_b)):
            if rollup.ground_truth == 0:
                lines.append(f"- **{label}**: brak ground truth w tej próbce.")
                continue
            delta_pp = (rollup.recall_with_gliner - rollup.recall_baseline) * 100
            lines.append(
                f"- **{label}**: recall baseline {rollup.recall_baseline * 100:.1f}% "
                f"({rollup.matched_baseline}/{rollup.ground_truth}) -> z GLiNER "
                f"{rollup.recall_with_gliner * 100:.1f}% ({rollup.matched_with_gliner}/{rollup.ground_truth}) "
                f"= **delta {delta_pp:+.1f}pp**."
            )

        n_variant_docs = n_docs
        lines += [
            "",
            f"Wpisy `uncertain_collector` (cały zbiór {n_variant_docs} dokumentów): "
            f"baseline (tylko niepewne po korekcie OCR-checksum) = {unc_baseline}, "
            f"z GLiNER (baseline + `[GLiNER]`) = {unc_gliner} "
            f"(+{unc_gliner - unc_baseline} nowych wpisów, "
            f"{(unc_gliner - unc_baseline) / n_variant_docs:.2f} na dokument).",
            f"Czas przetwarzania: baseline {t_baseline:.2f}s ({t_baseline / n_variant_docs * 1000:.1f}ms/dok), "
            f"z GLiNER {t_gliner:.2f}s ({t_gliner / n_variant_docs * 1000:.1f}ms/dok) "
            f"-> narzut {((t_gliner - t_baseline) / t_baseline * 100) if t_baseline else float('nan'):.0f}%.",
            "",
        ]

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=40, help="liczba dokumentów do wygenerowania")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--model",
        type=str,
        default="/config/gliner-anonimizator-pl-finetune/models/anonPL-300M/onnx/model_quantized.onnx",
    )
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--ocr-ratio", type=float, default=1.0, help="prawdopodobieństwo zaszumienia encji Grupy B")
    parser.add_argument(
        "--ocr-max-substitutions",
        type=int,
        default=3,
        help="max jednoczesnych podstawień OCR na wartość (>2 przekracza korekcję ocr_tolerance.py - patrz docstring)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("/config/gliner-anonimizator-pl-finetune/results/gliner_recall_eval.md"),
    )
    args = parser.parse_args()

    print(f"Wczytywanie modelu GLiNER z {args.model} ...")
    model = gliner_layer.load_model(args.model)
    print("Model wczytany.")

    docs_clean = generate_dataset(args.n, args.seed)

    rng = random.Random(args.seed)
    docs_ocr: list[GoldenDocument] = []
    for doc in docs_clean:
        record = _record_from_doc(doc)
        noisy_record = make_severe_ocr_variant(record, rng, args.ocr_ratio, args.ocr_max_substitutions)
        docs_ocr.append(_doc_from_record(noisy_record))

    print(f"Ewaluacja na {len(docs_clean)} dokumentach (czysty tekst) ...")
    clean_result = evaluate_variant(docs_clean, model, args.threshold)

    print(f"Ewaluacja na {len(docs_ocr)} dokumentach (zaszumiony OCR) ...")
    ocr_result = evaluate_variant(docs_ocr, model, args.threshold)

    report = format_report(args.n, args.seed, args.model, args.threshold, clean_result, ocr_result)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n(raport zapisany też do {args.out})")


if __name__ == "__main__":
    main()
