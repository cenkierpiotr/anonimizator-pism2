"""Wspolny fundament dla scenariuszy testow GUI (pod Xvfb, xdotool).

Dlaczego nie pytest: kazdy scenariusz tworzy WLASNE okno CTk (AnonymizerApp)
i wykonuje realne klikniecia myszy na wyrenderowanych widgetach - to nie sa
testy jednostkowe wywolujace metody bezposrednio, tylko odtworzenie tego co
robi czlowiek. Uruchamiane recznie (`python3 scripts/gui_tests/run_all.py`),
nie wchodza do pytest/CI (patrz pytest.ini: testpaths=tests) - wymagaja
srodowiska graficznego (Xvfb) i xdotool, ktorych CI Windows/Linux nie ma.

Jedyne monkeypatche to natywne dialogi systemowe (askopenfilenames/
asksaveasfilename/askdirectory/messagebox/CTkInputDialog) - okna spoza
drzewa widgetow aplikacji, nie do wyrenderowania w zrzucie ekranu apki ani
do sensownej automatyzacji bez zaleznosci od motywu/lokalizacji systemu.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

SCREEN_ROOT = Path("/tmp/gui_tests_screens")
SCREEN_ROOT.mkdir(exist_ok=True)


def xdotool(*args: str) -> str:
    return subprocess.run(["xdotool", *args], capture_output=True, text=True).stdout.strip()


def click_widget(widget) -> None:
    widget.update_idletasks()
    x = widget.winfo_rootx() + widget.winfo_width() // 2
    y = widget.winfo_rooty() + widget.winfo_height() // 2
    xdotool("mousemove", "--sync", str(x), str(y))
    xdotool("click", "1")


def screenshot(scenario: str, name: str) -> None:
    subdir = SCREEN_ROOT / scenario
    subdir.mkdir(exist_ok=True)
    path = subdir / f"{name}.xwd"
    subprocess.run(["bash", "-c", f"xwd -root -display $DISPLAY -out '{path}'"], check=False)
    print(f"screenshot: {path} (exists={path.exists()})")


def pump(app, seconds: float = 0.2) -> None:
    """Przepompowuje petle zdarzen Tk przez zadany czas - odpowiednik
    czekania czlowieka na reakcje interfejsu."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.update()
        time.sleep(0.02)


def wait_for_status(app, key: str, status, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.update()
        if app.items[key].status == status:
            return
        time.sleep(0.1)
    raise AssertionError(
        f"Timeout czekania na status {status} dla {key} - pozostal {app.items[key].status}"
    )


def toolbar_buttons(app) -> dict:
    buttons = {}
    for child in app.winfo_children()[0].winfo_children():
        text = child.cget("text") if hasattr(child, "cget") else None
        if text:
            buttons[text] = child
    return buttons


def find_toplevel_button(app, text: str):
    for w in app.winfo_children():
        if w.winfo_class() != "Toplevel":
            continue
        found = _find_button_recursive(w, text)
        if found is not None:
            return found
    return None


def _find_button_recursive(widget, text: str):
    for child in widget.winfo_children():
        if hasattr(child, "cget"):
            try:
                if child.cget("text") == text:
                    return child
            except Exception:
                pass
        found = _find_button_recursive(child, text)
        if found is not None:
            return found
    return None


def find_open_toplevel(app):
    for w in app.winfo_children():
        if w.winfo_class() == "Toplevel":
            return w
    return None


# ---------------------------------------------------------------------------
# Generatory plikow testowych
# ---------------------------------------------------------------------------


def make_docx(path: Path, text: str) -> Path:
    import docx

    document = docx.Document()
    document.add_paragraph(text)
    document.save(path)
    return path


def make_txt(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def make_pdf_text(path: Path, text: str) -> Path:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 8, text)
    pdf.output(str(path))
    return path


def make_pdf_scanned(path: Path, text: str) -> Path:
    """PDF bez warstwy tekstowej - tylko rasterowy obraz, wymusza sciezke OCR.

    Uzywa duzej czcionki DejaVuSans (nie domyslnej mikroskopijnej czcionki
    bitmapowej PIL) - inaczej Tesseract myli pojedyncze cyfry (np. 9 -> 8),
    co psuje sume kontrolna PESEL i daje falszywe 0 wykrytych encji - to
    byla usterka fixture'a testowego, nie aplikacji (zdiagnozowane przez
    porownanie z tests/test_ocr.py i bezposrednie sprawdzenie is_valid_pesel).
    """
    from fpdf import FPDF
    from PIL import Image, ImageDraw, ImageFont

    image_path = path.with_suffix(".png")
    img = Image.new("RGB", (1400, 200), "white")
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
    ImageDraw.Draw(img).text((20, 60), text, fill="black", font=font)
    img.save(image_path)

    pdf = FPDF()
    pdf.add_page()
    pdf.image(str(image_path), x=10, y=10, w=180)
    pdf.output(str(path))
    return path


def make_pdf_password(path: Path, text: str, password: str) -> Path:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 8, text)
    pdf.set_encryption(owner_password=password, user_password=password)
    pdf.output(str(path))
    return path


def make_unsupported(path: Path) -> Path:
    path.write_bytes(b"\x00\x01\x02 to nie jest zaden znany format dokumentu")
    return path


def make_corrupted_docx(path: Path) -> Path:
    """Nazwa .docx, ale nie jest to prawidlowy ZIP/OOXML - test odpornosci
    detekcji formatu/parsera, nie tylko rozszerzenia pliku."""
    path.write_bytes(b"PK\x03\x04 to nie jest prawdziwy plik docx" + b"\x00" * 50)
    return path
