"""Uruchamia wszystkie scenariusze GUI po kolei (kazdy we wlasnym procesie
python, bo kazdy tworzy wlasne okno CTk/Tk i monkeypatchuje globalne moduly
tkinter/customtkinter - odpalanie w jednym procesie zanieczyszczaloby stan
miedzy scenariuszami). Wymaga dzialajacego X (Xvfb) pod $DISPLAY oraz
xdotool zainstalowanego w systemie. Nie wchodzi do pytest/CI - patrz
pytest.ini (testpaths=tests) i komentarz w harness.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCENARIOS = [
    "s01_batch_multi_format",
    "s02_review_reject",
    "s03_cancel_and_remove",
    "s04_unsupported_corrupted",
    "s05_password_pdf",
    "s06_guards_and_libreoffice",
    "s07_ocr_quality",
]

ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> int:
    results: dict[str, bool] = {}
    for name in SCENARIOS:
        print(f"\n{'=' * 70}\n>>> {name}\n{'=' * 70}")
        proc = subprocess.run(
            [sys.executable, "-m", f"scripts.gui_tests.{name}"],
            cwd=str(ROOT),
        )
        results[name] = proc.returncode == 0

    print(f"\n{'=' * 70}\nPODSUMOWANIE\n{'=' * 70}")
    for name, ok in results.items():
        print(f"  {'OK  ' if ok else 'FAIL'} - {name}")

    failed = [name for name, ok in results.items() if not ok]
    if failed:
        print(f"\n{len(failed)}/{len(SCENARIOS)} scenariuszy nie powiodlo sie: {failed}")
        return 1
    print(f"\nWszystkie {len(SCENARIOS)} scenariuszy przeszly poprawnie.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
