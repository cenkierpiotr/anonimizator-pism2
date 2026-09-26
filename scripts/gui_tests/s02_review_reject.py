"""Scenariusz 2: otwarcie okna recenzji i klikniecie "Odrzuc" - sprawdza ze
status wraca do POMINIETY, dane staged sa odrzucone (discard_staged wywolany),
a plik wyjsciowy NIE powstaje (asksaveasfilename w ogole nie powinien byc
wolany na tej sciezce)."""

from __future__ import annotations

import sys
from pathlib import Path
from tkinter import filedialog, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.gui_tests import harness as h

TMP = Path("/tmp/gui_tests_s02")
TMP.mkdir(exist_ok=True)


def main() -> int:
    input_file = h.make_docx(TMP / "a.docx", "Powod Jan Kowalski, PESEL 44051401359, tel. 601-234-567.")
    output_file = TMP / "out.docx"
    output_file.unlink(missing_ok=True)

    save_calls = []

    filedialog.askopenfilenames = lambda **kwargs: (str(input_file),)
    filedialog.asksaveasfilename = lambda **kwargs: save_calls.append(1) or str(output_file)
    messagebox.showinfo = lambda *a, **k: print(f"[showinfo] {a}")
    messagebox.showerror = lambda *a, **k: print(f"[showerror] {a}")

    from app.gui.main_window import AnonymizerApp, FileStatus

    app = AnonymizerApp()
    app.update()
    h.screenshot("s02", "1_initial")

    buttons = h.toolbar_buttons(app)
    h.click_widget(buttons["Dodaj pliki..."])
    h.pump(app, 0.3)
    assert len(app.items) == 1

    h.click_widget(buttons["Anonimizuj zaznaczone"])
    h.pump(app)
    key = list(app.items)[0]
    h.wait_for_status(app, key, FileStatus.DO_WERYFIKACJI, timeout=60)

    row_widgets = app.row_widgets[key]
    h.click_widget(row_widgets["review_button"])
    h.pump(app, 0.3)
    h.screenshot("s02", "2_review_open")

    reject_button = h.find_toplevel_button(app, "Odrzuć")
    assert reject_button is not None, "Nie znaleziono przycisku 'Odrzuć' w oknie recenzji"
    h.click_widget(reject_button)
    h.pump(app, 0.3)
    h.screenshot("s02", "3_after_reject")

    assert app.items[key].status == FileStatus.POMINIETY, (
        f"Oczekiwano POMINIETY po odrzuceniu, jest {app.items[key].status}"
    )
    assert app.items[key].staged is None, "staged powinien byc wyczyszczony po odrzuceniu"
    assert not save_calls, "asksaveasfilename NIE powinien byc wolany przy odrzuceniu"
    assert not output_file.exists(), "Plik wyjsciowy nie powinien powstac przy odrzuceniu"
    assert h.find_open_toplevel(app) is None, "Okno recenzji powinno byc zamkniete po odrzuceniu"

    app.destroy()
    print("\nOK s02: odrzucenie w oknie recenzji dziala poprawnie (status POMINIETY, brak zapisu).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
