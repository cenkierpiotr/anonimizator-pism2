"""Augmentacja szumem OCR: wariant zaszumiony golden dataset (patrz plan
fine-tuningu GLiNER, sekcja "Strategia danych treningowych", punkt 2).

Wejście: JSONL wygenerowany przez `golden_dataset.py --export-jsonl`
(`{"doc_id","doc_type","text","entities":[{"category","start","end","value"}]}`).
Wyjście: JSONL o tej samej strukturze, gdzie wartości encji z kategorii Grupy B
(identyfikatory strukturalne: PESEL/NIP/REGON/IBAN/dowód osobisty/VIN) mają z
prawdopodobieństwem `--ratio` podstawiony jeden ze znaków-myłek OCR z
`app/detectors/ocr_tolerance.CONFUSABLES` (O/0, I/1/l, S/5, B/8, Z/2).

Podstawienia są znak-na-znak, więc offsety `start`/`end` w ground truth
NIE się zmieniają - tylko `value` (i odpowiadający fragment `text`) zawiera
zaszumioną wersję. To jest właśnie powód, dla którego reużywamy tabelę z
`ocr_tolerance.py` zamiast losowego szumu ogólnego: gwarantuje 1:1 długość.

Cel treningowy: regex+checksum na czystym tekście jest bezbłędny, więc GLiNER
nie musi się uczyć rozpoznawać PESEL/NIP na czystym tekście - ale gdy OCR
skorumpuje cyfry (checksum przestaje się zgadzać), GLiNER wytrenowany na takich
zaszumionych przykładach może złapać kontekstowo to, czego checksum już nie
złapie (patrz plan, Grupa B: "trening tylko na wariantach z szumem OCR").

Uruchomienie:

    source .venv/bin/activate
    python3 scripts/golden_dataset.py --export-jsonl /tmp/golden.jsonl --n 200
    python3 scripts/ocr_noise_augment.py --in /tmp/golden.jsonl --out /tmp/golden_ocr.jsonl --ratio 0.3
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.detectors.ocr_tolerance import CONFUSABLES

# Grupa B z planu fine-tuningu GLiNER: identyfikatory strukturalne, na których
# regex+checksum jest autorytatywny na czystym tekście - GLiNER ma dla nich
# sens tylko jako warstwa odpornościowa na szum OCR.
GROUP_B_CATEGORIES = frozenset({"pesel", "nip", "regon", "iban", "id_card", "vehicle_vin"})


def _noisy_value(value: str, rng: random.Random, max_substitutions: int = 2) -> str:
    """Podstawia losowo 1..max_substitutions znaków-myłek OCR w `value`.
    Zwraca `value` bez zmian, jeśli nie ma żadnej podstawialnej pozycji."""
    positions = [i for i, ch in enumerate(value) if ch in CONFUSABLES]
    if not positions:
        return value

    k = min(rng.randint(1, max_substitutions), len(positions))
    chosen = rng.sample(positions, k)
    chars = list(value)
    for pos in chosen:
        chars[pos] = rng.choice(CONFUSABLES[chars[pos]])
    return "".join(chars)


def augment_document(record: dict, rng: random.Random, ratio: float) -> dict:
    """Zwraca nową wersję dokumentu z podstawieniami OCR w wybranych encjach
    Grupy B - tekst i wartości encji są przebudowywane od końca, żeby offsety
    encji nieobjętych zaszumieniem zostały nienaruszone."""
    text = record["text"]
    entities = record["entities"]
    noisy_entities = [dict(e) for e in entities]

    # Od końca dokumentu, żeby wcześniejsze offsety nie przesunęły się przy
    # zamianie (mimo że długość się nie zmienia, to i tak bezpieczniejsze
    # nawykowo niż zakładać, że nigdy się nie zmieni).
    for entity in sorted(noisy_entities, key=lambda e: e["start"], reverse=True):
        if entity["category"] not in GROUP_B_CATEGORIES:
            continue
        if rng.random() >= ratio:
            continue
        original = entity["value"]
        noisy = _noisy_value(original, rng)
        if noisy == original:
            continue
        assert len(noisy) == len(original), "podstawienia OCR muszą być 1:1 (offsety się nie zmieniają)"
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="input_path", type=Path, required=True)
    parser.add_argument("--out", dest="output_path", type=Path, required=True)
    parser.add_argument(
        "--ratio",
        type=float,
        default=0.3,
        help="prawdopodobieństwo zaszumienia pojedynczej encji Grupy B (domyślnie 0.3)",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    n_docs = 0
    n_noised_entities = 0

    with args.input_path.open("r", encoding="utf-8") as fin, args.output_path.open(
        "w", encoding="utf-8"
    ) as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            noisy_record = augment_document(record, rng, args.ratio)
            n_docs += 1
            n_noised_entities += sum(1 for e in noisy_record["entities"] if e.get("ocr_noised"))
            fout.write(json.dumps(noisy_record, ensure_ascii=False) + "\n")

    print(f"Zaszumiono {n_docs} dokumentów, {n_noised_entities} encji Grupy B -> {args.output_path}")


if __name__ == "__main__":
    main()
