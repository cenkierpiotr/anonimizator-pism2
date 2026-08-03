"""Scenariusz 4: plik calkowicie nieznanego formatu oraz plik z rozszerzeniem
.docx ktory nie jest prawdziwym ZIP/OOXML - oba powinny wyladowac w statusie
BLAD z czytelnym komunikatem (messagebox.showerror), a nie wywalic wyjatkiem
poza worker."""

from __future__ import annotations

import sys
from pathlib import Path
from tkinter import filedialog, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.gui_tests import harness as h

TMP = Path("/tmp/gui_tests_s04")
TMP.mkdir(exist_ok=True)


def main() -> int:
    files = [
        h.make_unsupported(TMP / "a.xyz"),
        h.make_corrupted_docx(TMP / "b.docx"),
    ]

    errors_shown = []
    filedialog.askopenfilenames = lambda **kwargs: tuple(str(f) for f in files)
    messagebox.showinfo = lambda *a, **k: print(f"[showinfo] {a}")
    messagebox.showerror = lambda *a, **k: errors_shown.append(a) or print(f"[showerror] {a}")

    from app.gui.main_window import AnonymizerApp, FileStatus

    app = AnonymizerApp()
    app.update()

    buttons = h.toolbar_buttons(app)
    h.click_widget(buttons["Dodaj pliki..."])
    h.pump(app, 0.3)
    assert len(app.items) == 2
    h.screenshot("s04", "1_after_add")

    h.click_widget(buttons["Anonimizuj zaznaczone"])
    h.pump(app)

    for key in list(app.items):
        h.wait_for_status(app, key, FileStatus.BLAD, timeout=30)
        widgets = app.row_widgets[key]
        assert widgets["status_label"].cget("text") == FileStatus.BLAD.value
        assert str(widgets["review_button"].cget("state")) == "disabled"
        print(f"OK: {Path(key).name} -> BLAD, komunikat: {app.items[key].error!r}")

    h.screenshot("s04", "2_after_processing")
    assert len(errors_shown) == 2, f"Oczekiwano 2 wywolan messagebox.showerror, bylo {len(errors_shown)}"

    app.destroy()
    print("\nOK s04: pliki nieobslugiwane/uszkodzone poprawnie koncza sie statusem BLAD.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
