"""Scenariusz 3: anulowanie w trakcie przetwarzania wsadu + usuwanie
zaznaczonych z listy (zarowno pliku oczekujacego jak i juz przetworzonego
ze stagingiem)."""

from __future__ import annotations

import sys
from pathlib import Path
from tkinter import filedialog, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.gui_tests import harness as h

TMP = Path("/tmp/gui_tests_s03")
TMP.mkdir(exist_ok=True)


def main() -> int:
    files = [
        h.make_txt(TMP / "a.txt", "Powod Jan Kowalski, PESEL 44051401359."),
        h.make_txt(TMP / "b.txt", "Pozwana Anna Nowak, tel. 601-234-567."),
        h.make_txt(TMP / "c.txt", "Swiadek Piotr Wisniewski, adres Marszalkowska 10."),
    ]

    filedialog.askopenfilenames = lambda **kwargs: tuple(str(f) for f in files)
    messagebox.showinfo = lambda *a, **k: print(f"[showinfo] {a}")
    messagebox.showerror = lambda *a, **k: print(f"[showerror] {a}")

    from app.gui.main_window import AnonymizerApp, FileStatus

    app = AnonymizerApp()
    app.update()

    buttons = h.toolbar_buttons(app)
    h.click_widget(buttons["Dodaj pliki..."])
    h.pump(app, 0.3)
    assert len(app.items) == 3
    keys = list(app.items)
    h.screenshot("s03", "1_after_add")

    # --- czesc A: anulowanie w trakcie wsadu ---
    h.click_widget(buttons["Anonimizuj zaznaczone"])
    h.pump(app, 0.05)  # dac pierwszemu plikowi ruszyc, ale nie skonczyc calego wsadu
    h.click_widget(buttons["Anuluj"])
    h.pump(app, 2.0)
    h.screenshot("s03", "2_after_cancel")

    statuses = {k: app.items[k].status for k in keys}
    print("Statusy po anulowaniu:", {Path(k).name: s.value for k, s in statuses.items()})
    non_terminal = [k for k, s in statuses.items() if s == FileStatus.PRZETWARZANIE]
    assert not non_terminal, f"Pliki utkniete w PRZETWARZANIE po anulowaniu: {non_terminal}"
    assert any(s == FileStatus.POMINIETY for s in statuses.values()), (
        "Oczekiwano co najmniej jednego POMINIETY po anulowaniu wsadu"
    )
    assert str(buttons["Anuluj"].cget("state")) == "disabled", (
        "Przycisk Anuluj powinien wrocic do stanu disabled po zakonczeniu wsadu"
    )

    # --- czesc B: usuwanie zaznaczonych z listy ---
    # jeden z plikow moze byc DO_WERYFIKACJI (mial czas dokonczyc), inny POMINIETY -
    # usuwamy WSZYSTKIE zaznaczone (domyslnie wszystkie checkboxy sa zaznaczone)
    before_count = len(app.items)
    h.click_widget(buttons["Usuń zaznaczone z listy"])
    h.pump(app, 0.3)
    h.screenshot("s03", "3_after_remove")

    assert len(app.items) == 0, f"Oczekiwano pustej listy po usunieciu wszystkich, zostalo {len(app.items)}"
    assert len(app.row_widgets) == 0, "Wiersze GUI powinny zniknac po usunieciu"

    app.destroy()
    print("\nOK s03: anulowanie wsadu i usuwanie zaznaczonych dzialaja poprawnie.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
