"""Scenariusz 1: dodanie w jednym wywolaniu 4 roznych formatow (docx, txt,
pdf-tekstowy, pdf-skan/OCR) i sprawdzenie ze CALA kolejka poprawnie przechodzi
do "do weryfikacji" niezaleznie od formatu wejsciowego, a etykiety statusu w
wierszach listy odzwierciedlaja to poprawnie."""

from __future__ import annotations

import sys
from pathlib import Path
from tkinter import filedialog, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.gui_tests import harness as h

TMP = Path("/tmp/gui_tests_s01")
TMP.mkdir(exist_ok=True)


def main() -> int:
    files = [
        h.make_docx(TMP / "a.docx", "Powod Jan Kowalski, PESEL 44051401359, tel. 601-234-567."),
        h.make_txt(TMP / "b.txt", "Wnioskodawca PESEL 44051401359 wnosi o rozpoznanie sprawy."),
        h.make_pdf_text(TMP / "c.pdf", "Pozwana Anna Nowak, tel. 601-234-567, wnosi odpowiedz."),
        h.make_pdf_scanned(TMP / "d_scan.pdf", "PESEL 44051401359 powoda"),
    ]

    filedialog.askopenfilenames = lambda **kwargs: tuple(str(f) for f in files)
    filedialog.asksaveasfilename = lambda **kwargs: str(TMP / "out.docx")
    messagebox.showinfo = lambda *a, **k: print(f"[showinfo] {a}")
    messagebox.showerror = lambda *a, **k: print(f"[showerror] {a}")

    from app.gui.main_window import AnonymizerApp, FileStatus

    app = AnonymizerApp()
    app.update()
    h.screenshot("s01", "1_initial")

    buttons = h.toolbar_buttons(app)
    h.click_widget(buttons["Dodaj pliki..."])
    h.pump(app, 0.3)
    assert len(app.items) == 4, f"Oczekiwano 4 plikow w kolejce, jest {len(app.items)}"
    print("Kolejka po dodaniu:", [Path(k).name for k in app.items])
    h.screenshot("s01", "2_after_add")

    h.click_widget(buttons["Anonimizuj zaznaczone"])
    h.pump(app)

    for key in list(app.items):
        h.wait_for_status(app, key, FileStatus.DO_WERYFIKACJI, timeout=90)
        widgets = app.row_widgets[key]
        assert widgets["status_label"].cget("text") == FileStatus.DO_WERYFIKACJI.value
        assert str(widgets["review_button"].cget("state")) == "normal"
        print(f"OK: {Path(key).name} -> do weryfikacji, entity_count={app.items[key].staged.entity_count}")

    h.screenshot("s01", "3_all_done")
    app.destroy()
    print("\nOK s01: batch 4 roznych formatow przeszedl do weryfikacji poprawnie.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
