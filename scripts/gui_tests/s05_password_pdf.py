"""Scenariusz 5: prawdziwy PDF zaszyfrowany haslem - sprawdza pelna sciezke
PasswordRequiredError -> CTkInputDialog -> ponowna proba z haslem -> sukces.
Monkeypatchujemy TYLKO CTkInputDialog.get_input (natywny dialog OS/Tk, poza
drzewem widgetow aplikacji), zeby dostarczyc haslo bez realnej interakcji
klawiatury."""

from __future__ import annotations

import sys
from pathlib import Path
from tkinter import filedialog, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.gui_tests import harness as h

TMP = Path("/tmp/gui_tests_s05")
TMP.mkdir(exist_ok=True)
PASSWORD = "sekret123"


def main() -> int:
    input_file = h.make_pdf_password(
        TMP / "chroniony.pdf", "Powod Jan Kowalski, PESEL 44051401359.", PASSWORD
    )

    filedialog.askopenfilenames = lambda **kwargs: (str(input_file),)
    messagebox.showinfo = lambda *a, **k: print(f"[showinfo] {a}")
    messagebox.showerror = lambda *a, **k: print(f"[showerror] {a}")

    import customtkinter as ctk

    ctk.CTkInputDialog.get_input = lambda self: PASSWORD

    from app.gui.main_window import AnonymizerApp, FileStatus

    app = AnonymizerApp()
    app.update()

    buttons = h.toolbar_buttons(app)
    h.click_widget(buttons["Dodaj pliki..."])
    h.pump(app, 0.3)
    assert len(app.items) == 1
    key = list(app.items)[0]

    h.click_widget(buttons["Anonimizuj zaznaczone"])
    h.pump(app)
    h.screenshot("s05", "1_processing")

    h.wait_for_status(app, key, FileStatus.DO_WERYFIKACJI, timeout=60)
    h.screenshot("s05", "2_after_password_retry")

    staged = app.items[key].staged
    assert staged is not None
    print("Encje wykryte po podaniu hasla:", staged.entity_count)
    assert staged.entity_count >= 1, "Oczekiwano wykrycia PESEL po odszyfrowaniu"

    app.destroy()
    print("\nOK s05: PDF z haslem - retry z poprawnym haslem dziala i osiaga DO_WERYFIKACJI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
