# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec dla "Anonimizator Pism" - build one-dir (NIE one-file).

WAŻNE OGRANICZENIE ŚRODOWISKA: ten plik jest pisany i weryfikowany składniowo
na Linuksie, ale PyInstaller NIE kompiluje krzyżowo - musi zostać faktycznie
URUCHOMIONY przez `pyinstaller build/anonimizator.spec` na runnerze
`windows-latest` w GitHub Actions (patrz .github/workflows/build-windows.yml).
Nic w tym pliku nie zostało tu wykonane ani przetestowane end-to-end - tylko
sprawdzone `compile()`-em pod kątem poprawności składni Pythona.

Dlaczego one-dir, nie one-file: przy tym rozmiarze bundla (model spaCy,
Tesseract, gazetteery) one-file rozpakowywałby się do katalogu tymczasowego
przy KAŻDYM starcie aplikacji - kilkanaście sekund i setki MB zapisu na dysk
za każdym uruchomieniem. Inno Setup (`build/installer.iss`) instaluje cały
katalog wyjściowy `dist/AnonimizatorPism/` jako jedną paczkę.

ZAŁOŻENIE O ENTRY POINCIE: w chwili gdy zaczynałem pisać ten plik, `app/gui/`
zawierał tylko pusty `__init__.py` (GUI jeszcze nie istniało) - założyłem
standardowy wzorzec `if __name__ == "__main__": ...`. Równoległy agent
dokończył GUI w międzyczasie (commit "Faza 3: GUI (CustomTkinter)") - realny
plik `app/gui/main_window.py` faktycznie ma dokładnie ten wzorzec:

    def main() -> None:
        app = AnonymizerApp()
        app.mainloop()
    if __name__ == "__main__":
        main()

Czyli `Analysis([_ENTRY_SCRIPT])` poniżej wskazujący na
`app/gui/main_window.py` jest poprawny bez zmian - PyInstaller uruchomi ten
plik jako `__main__`, co wywoła `main()`.

NIE bundlujemy LibreOffice - to komponent pobierany na żądanie w runtime
(patrz `app/pipeline/legacy_convert.py`, sekcja planu "Pobieranie LibreOffice
na żądanie"), świadomie pominięty tutaj.

TODO (Tesseract - binarka, nie tylko dane): `resources/tessdata/*.traineddata`
to tylko dane językowe OCR - do faktycznego działania OCR na czystym Windows
(wymóg "zero preinstalowanych zależności") potrzebna jest też sama binarka
`tesseract.exe` + jej DLL-e, bo `pytesseract` woła ją jako zewnętrzny proces
(`app/pipeline/ocr.py`), nie ma jej wbudowanej w żaden pakiet pip. Workflow
CI (`build-windows.yml`) instaluje portable Tesseract przez Chocolatey i kopiuje
go do `build/vendor/tesseract/` PRZED uruchomieniem tego spec-a - blok
`_TESSERACT_VENDOR_DIR` niżej podłącza go do bundla, jeśli katalog istnieje
(guard, żeby lokalny `compile()`-check na Linuksie i ewentualne uruchomienie
bez wcześniejszego kroku vendoringu nie wywalały się na starcie). Zwrócenie
uwagi zespołu GUI: po stronie `app/gui/main_window.py` trzeba w runtime
ustawić `pytesseract.pytesseract.tesseract_cmd` na
`Path(sys.executable).parent / "tesseract" / "tesseract.exe"` (folder obok
głównego .exe w one-dir) - to nie jest zrobione automatycznie przez samo
zbundlowanie plików.
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None

# SPECPATH jest wstrzykiwane przez PyInstaller do przestrzeni nazw tego pliku
# (katalog zawierający ten .spec) - użycie go zamiast os.getcwd() sprawia,
# że spec działa niezależnie od katalogu, z którego wywołano `pyinstaller`.
try:
    _SPEC_DIR = Path(SPECPATH)  # type: ignore[name-defined]
except NameError:
    _SPEC_DIR = Path(os.getcwd()) / "build"

_PROJECT_ROOT = (_SPEC_DIR / "..").resolve()
_APP_NAME = "AnonimizatorPism"

# Zakładany entry point GUI - patrz uwaga w module docstring wyżej.
_ENTRY_SCRIPT = str(_PROJECT_ROOT / "app" / "gui" / "main_window.py")

# --- Zasoby własne aplikacji (nie zależności pip) --------------------------

_datas = []

_tessdata_dir = _PROJECT_ROOT / "resources" / "tessdata"
if _tessdata_dir.is_dir():
    for f in _tessdata_dir.glob("*.traineddata"):
        _datas.append((str(f), "resources/tessdata"))

_gazetteers_dir = _PROJECT_ROOT / "resources" / "gazetteers"
if _gazetteers_dir.is_dir():
    for f in _gazetteers_dir.glob("*.txt"):
        _datas.append((str(f), "resources/gazetteers"))

# Portable Tesseract (binarka + DLL-e + własny tessdata domyślny silnika) -
# przygotowywany przez workflow CI (choco install tesseract-ocr, potem
# robocopy katalogu instalacji do build/vendor/tesseract) PRZED wywołaniem
# tego spec-a. Guard `is_dir()` żeby brak tego kroku (np. lokalny test na
# Linuksie) nie wywalał parsowania/budowania spec-a - po prostu build wtedy
# nie ma działającego OCR, co i tak nie da się tu wykryć bez Windows.
_tesseract_vendor_dir = _PROJECT_ROOT / "build" / "vendor" / "tesseract"
_tesseract_binaries = []
if _tesseract_vendor_dir.is_dir():
    for f in _tesseract_vendor_dir.rglob("*"):
        if f.is_file():
            rel_parent = f.parent.relative_to(_tesseract_vendor_dir)
            dest = str(Path("tesseract") / rel_parent)
            # Windows: DLL/EXE. Linux: biblioteki .so (także wersjonowane,
            # np. "libtesseract.so.5") oraz sama binarka "tesseract" bez
            # rozszerzenia (patrz build-linux.yml - vendoring przez ldd) -
            # to są jedyne pliki wykonywalne/biblioteki w tym katalogu,
            # `_configure_bundled_tesseract` w app/pipeline/ocr.py oczekuje
            # ich w podkatalogu "tesseract" obok głównego pliku wykonywalnego.
            is_binary = (
                f.suffix.lower() in (".dll", ".exe")
                or f.suffix.lower() == ".so"
                or ".so." in f.name
                or f.name == "tesseract"
            )
            if is_binary:
                _tesseract_binaries.append((str(f), dest))
            else:
                _datas.append((str(f), dest))

# --- Zależności pip z danymi/dynamicznymi importami -------------------------

_hiddenimports = [
    # pytesseract - woła tesseract.exe jako subprocess, ale sam moduł ma
    # kilka opcjonalnych gałęzi importu (np. shutil, pandas przy
    # output_type=DATAFRAME) których PyInstaller nie wykrywa statycznie.
    "pytesseract",
    # pypdfium2 - bindingi ctypes do natywnej biblioteki PDFium; moduły
    # pomocnicze bywają importowane dynamicznie z _helpers.
    "pypdfium2",
    "pypdfium2_raw",
    "pypdfium2._helpers",
    "pypdfium2._helpers.textpage",
    "pypdfium2._helpers.document",
    "pypdfium2._helpers.page",
    # odfpy (import jako "odf") - submoduły ładowane po nazwie klasy elementu
    # XML (np. odf.text, odf.style) - collect_submodules niżej i tak to łapie,
    # ale wypisujemy też jawnie najczęściej używane, dla czytelności/pewności.
    "odf",
    "odf.opendocument",
    "odf.text",
    "odf.style",
    "odf.teletype",
    # python-docx - nazwa pakietu importu to "docx", nie "python_docx".
    "docx",
    "docx.oxml",
    # Pillow - wtyczki formatów obrazów rejestrują się dynamicznie.
    "PIL",
    "PIL.Image",
    "PIL.ImageOps",
    "PIL.ImageDraw",
    # spaCy - fabryki komponentów pipeline'u i language-specific submoduły
    # są ładowane dynamicznie po nazwie (np. "pl" -> spacy.lang.pl), co
    # statyczna analiza importów PyInstallera regularnie przegapia.
    "spacy.lang.pl",
    "spacy.lang.en",
    "spacy.pipeline",
    "spacy.pipeline.ner",
    "spacy.pipeline.tagger",
    "spacy.pipeline.lemmatizer",
    "spacy.kb",
    "thinc.api",
    "thinc.backends.numpy_ops",
    "srsly.msgpack.util",
    "catalogue",
    "wasabi",
    "blis",
    "murmurhash",
    "preshed",
    # Model językowy spaCy - pakiet PyPI-podobny zainstalowany z wheela
    # w requirements.txt jako "pl_core_news_md" (nie na PyPI pod prostą nazwą,
    # patrz komentarz w requirements.txt).
    "pl_core_news_md",
    # tkinterdnd2 (przeciągnij-i-upuść w GUI) - moduł sam w sobie jest
    # statycznie importowany wprost w main_window.py, więc PyInstaller by go
    # znalazł i tak; jawny wpis tu tylko dla czytelności obok collect_data_files
    # niżej, które wciąga natywną binarkę tkdnd (bez niej `TkinterDnD._require`
    # rzuci RuntimeError w runtime na czystym Windows).
    "tkinterdnd2",
]

# collect_submodules na najbardziej "dynamicznych" pakietach - taniej i
# bezpieczniej niż ręcznie wymieniać każdy możliwy submoduł, a znacznie
# tańsze niż collect_all na całym spacy (które wciągnęłoby też testy/docs).
for _pkg in ("spacy", "thinc", "srsly", "catalogue", "odf"):
    try:
        _hiddenimports.extend(collect_submodules(_pkg))
    except Exception:
        # Pakiet może nie być zainstalowany w środowisku, w którym ten plik
        # jest tylko parsowany (np. `compile()`-check na Linuksie bez
        # PyInstallera) - nieszkodliwe, w CI Windows wszystko jest zainstalowane
        # przez `pip install -r requirements.txt`.
        pass

# Dane pakietu modelu spaCy (wagi, config.cfg, słowniki wektorów) -
# collect_all zwraca (datas, binaries, hiddenimports) w jednej krotce.
_model_binaries = []
try:
    _model_datas, _model_binaries, _model_hidden = collect_all("pl_core_news_md")
    _datas.extend(_model_datas)
    _hiddenimports.extend(_model_hidden)
except Exception:
    # W środowisku bez zainstalowanego modelu (np. ten sam `compile()`-check
    # na Linuksie) collect_all rzuci wyjątek importu - w CI Windows model jest
    # zainstalowany z requirements.txt przed uruchomieniem pyinstaller.
    pass

# Dane samego pakietu spacy (lookups, słowniki, licencje) - bez tego niektóre
# komponenty pipeline'u (np. lemmatizer regułowy) nie znajdą swoich zasobów.
try:
    _datas.extend(collect_data_files("spacy"))
    _datas.extend(collect_data_files("spacy_lookups_data"))
except Exception:
    pass

# tkinterdnd2 - natywna biblioteka tkdnd (per-platforma, w tym Windows .dll)
# jest dystrybuowana jako dane pakietu pod tkinterdnd2/tkdnd/, nie jako kod
# Pythona - bez tego collect_data_files GUI wystartuje, ale przeciągnij-i-upuść
# cicho się wyłączy (patrz obsługa RuntimeError w main_window._setup_drag_and_drop).
try:
    _datas.extend(collect_data_files("tkinterdnd2"))
except Exception:
    pass


a = Analysis(
    [_ENTRY_SCRIPT],
    pathex=[str(_PROJECT_ROOT)],
    binaries=_tesseract_binaries + _model_binaries,
    datas=_datas,
    hiddenimports=_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Nigdy nie potrzebne w runtime, a bywają ciągnięte transytywnie -
        # wycinamy dla mniejszego bundla. matplotlib/tkinter.test itp.
        "matplotlib",
        "notebook",
        "IPython",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=_APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX bywa flagowany przez AV jako podejrzany packer - wyłączone
    console=False,  # aplikacja GUI, bez okna konsoli
    # TODO (Faza 5, świadomie odłożone): brak podpisu kodu (code signing).
    # Bez certyfikatu OV/EV SmartScreen prawie na pewno pokaże "Windows
    # chronił Twój komputer" przy pierwszym uruchomieniu, a niektóre AV mogą
    # fałszywie zaflagować plik (PyInstaller jest w tym notorycznie częsty).
    # Certyfikat kosztuje i wymaga procesu weryfikacji wydawcy - do kupienia
    # i wpięcia (np. przez `signtool sign /f cert.pfx ...` jako krok CI po
    # tym spec-u) w osobnej fazie. Nie próbować obchodzić tego teraz.
    icon=None,  # TODO: dodać resources/icon.ico gdy powstanie grafika aplikacji
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=_APP_NAME,
)
