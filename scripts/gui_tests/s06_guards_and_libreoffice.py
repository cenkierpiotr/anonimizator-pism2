"""Scenariusz 6: guardy pustego zaznaczenia ("Anonimizuj zaznaczone" i
"Konwertuj do PDF" bez zadnego wybranego pliku), realna sciezka bledu
"Konwertuj do PDF" gdy LibreOffice nie jest zainstalowany (prawdziwy blad w
tym srodowisku, bez monkeypatcha), oraz "Zainstaluj obsluge .doc" z
monkeypatchowanym download_libreoffice (sukces i porazka) - zeby uniknac
prawdziwego ~300MB pobrania w automatycznym tescie."""

from __future__ import annotations

import sys
from pathlib import Path
from tkinter import filedialog, messagebox

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.gui_tests import harness as h

TMP = Path("/tmp/gui_tests_s06")
TMP.mkdir(exist_ok=True)


def main() -> int:
    docx_file = h.make_docx(TMP / "a.docx", "Tresc bez PII istotnych do tego scenariusza.")

    info_messages = []
    error_messages = []
    filedialog.askopenfilenames = lambda **kwargs: (str(docx_file),)
    filedialog.askdirectory = lambda **kwargs: str(TMP)
    messagebox.showinfo = lambda *a, **k: info_messages.append(a) or print(f"[showinfo] {a}")
    messagebox.showerror = lambda *a, **k: error_messages.append(a) or print(f"[showerror] {a}")

    from app.gui.main_window import AnonymizerApp
    from app.pipeline.legacy_convert import is_libreoffice_available

    assert not is_libreoffice_available(), (
        "Ten scenariusz zaklada BRAK LibreOffice w srodowisku testowym - "
        "jesli to sie zmieni, sciezka bledu ponizej trzeba przeprojektowac"
    )

    app = AnonymizerApp()
    app.update()
    buttons = h.toolbar_buttons(app)

    # --- A: guard pustego zaznaczenia dla "Anonimizuj zaznaczone" (pusta kolejka) ---
    h.click_widget(buttons["Anonimizuj zaznaczone"])
    h.pump(app, 0.2)
    assert info_messages, "Oczekiwano komunikatu guard przy pustej kolejce (Anonimizuj)"
    assert "co najmniej jeden plik oczekujący" in info_messages[-1][1]
    info_messages.clear()
    h.screenshot("s06", "1_guard_anonymize_empty")

    # --- B: guard pustego zaznaczenia dla "Konwertuj do PDF" (nic niezaznaczone) ---
    h.click_widget(buttons["Dodaj pliki..."])
    h.pump(app, 0.3)
    assert len(app.items) == 1
    key = list(app.items)[0]
    app.row_widgets[key]["check_var"].set(False)
    h.click_widget(buttons["Konwertuj do PDF"])
    h.pump(app, 0.2)
    assert info_messages, "Oczekiwano komunikatu guard przy braku zaznaczenia (Konwertuj do PDF)"
    assert "co najmniej jeden plik do konwersji" in info_messages[-1][1]
    info_messages.clear()
    h.screenshot("s06", "2_guard_convert_empty")

    # --- C: realna sciezka bledu "Konwertuj do PDF" bez LibreOffice ---
    # `convert_many_to_pdf` lapie WSZYSTKIE wyjatki per-plik (w tym
    # LibreOfficeNotAvailableError) i zwraca je w liscie wynikow zamiast je
    # propagowac - `_on_convert_to_pdf` (main_window.py) juz nie ma wiec
    # zadnego try/except wokol tego wywolania (martwa galaz usunieta).
    # Realna sciezka to showinfo z "Skonwertowano 0/N" + szczegoly bledu.
    app.row_widgets[key]["check_var"].set(True)
    h.click_widget(buttons["Konwertuj do PDF"])
    h.pump(app, 0.3)
    h.screenshot("s06", "3_convert_no_libreoffice")
    assert not error_messages, "Nieoczekiwany showerror przy braku LibreOffice"
    assert info_messages, "Oczekiwano showinfo z podsumowaniem konwersji (0/N, z bledem LibreOffice)"
    assert "Skonwertowano 0/1" in info_messages[-1][1]
    assert "LibreOffice" in info_messages[-1][1]
    info_messages.clear()

    # --- D: "Zainstaluj obsluge .doc" - monkeypatch download_libreoffice: sukces ---
    import app.gui.main_window as mw

    mw.download_libreoffice = lambda: None
    h.click_widget(buttons["Zainstaluj obsługę .doc"])
    h.pump(app, 0.2)
    assert info_messages, "Oczekiwano komunikatu sukcesu po (zamockowanej) instalacji"
    assert "zainstalowany pomyślnie" in info_messages[-1][1]
    info_messages.clear()
    h.screenshot("s06", "4_install_libreoffice_success")

    # --- E: "Zainstaluj obsluge .doc" - monkeypatch download_libreoffice: porazka ---
    def _boom():
        raise RuntimeError("Brak polaczenia z siecia (symulacja)")

    mw.download_libreoffice = _boom
    h.click_widget(buttons["Zainstaluj obsługę .doc"])
    h.pump(app, 0.2)
    assert error_messages, "Oczekiwano komunikatu bledu po (zamockowanej) nieudanej instalacji"
    assert "Nie udało się zainstalować" in error_messages[-1][1]
    h.screenshot("s06", "5_install_libreoffice_failure")

    app.destroy()
    print("\nOK s06: guardy pustego zaznaczenia oraz sciezki LibreOffice dzialaja poprawnie.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
