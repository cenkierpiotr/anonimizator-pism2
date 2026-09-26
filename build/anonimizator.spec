# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec dla "Anonimizator Pism" - build one-dir (NIE one-file).

UWAGA: PyInstaller nie kompiluje krzyżowo - ten plik faktycznie wykonuje się
tylko przez `pyinstaller build/anonimizator.spec` na runnerze `windows-latest`
w GitHub Actions (patrz .github/workflows/build-windows.yml).

Dlaczego one-dir, nie one-file: przy tym rozmiarze bundla (model spaCy,
Tesseract, gazetteery) one-file rozpakowywałby się do katalogu tymczasowego
przy KAŻDYM starcie aplikacji - kilkanaście sekund i setki MB zapisu na dysk
za każdym uruchomieniem. Inno Setup (`build/installer.iss`) instaluje cały
katalog wyjściowy `dist/AnonimizatorPism/` jako jedną paczkę.

Entry point (`Analysis([_ENTRY_SCRIPT])` niżej) wskazuje na
`app/gui/main_window.py`, który ma standardowy wzorzec:

    def main() -> None:
        app = AnonymizerApp()
        app.mainloop()
    if __name__ == "__main__":
        main()

PyInstaller uruchomi ten plik jako `__main__`, co wywoła `main()`.

LibreOffice i model GLiNER są bundlowane build-time (zamiast runtime
download-on-demand), bo repo tego projektu jest prywatne - anonimowy
`urllib`/`curl` na `browser_download_url` GitHub Release zwraca 404
nieautoryzowanemu klientowi, więc mechanizm "pobierz na żądanie"
(`app/pipeline/legacy_convert.py::download_libreoffice()` /
`app/pipeline/gliner_layer.py::download_gliner_model()`) nie działa dla
realnego użytkownika końcowego offline/bez tokenu GitHub. Oba mechanizmy
runtime zostają w kodzie jako opcjonalny manualny fallback (patrz ich
docstringi), ale priorytetowa ścieżka jest teraz build-time:

- LibreOffice: vendorowany przez Chocolatey w CI (`choco install
  libreoffice-still`) do `build/vendor/libreoffice/`, podłączony niżej
  (blok `_libreoffice_vendor_dir`) - ten sam wzorzec binaries/datas co
  Tesseract poniżej, bo LibreOffice ma własne .exe/.dll.
- Model GLiNER (eksport ONNX, ~150-300MB): pobierany authenticated (`gh
  release download`, token CI) z prywatnego Release tego samego repo do
  `build/vendor/gliner_model/`, podłączony niżej (blok
  `_gliner_model_vendor_dir`). Wszystkie pliki tego katalogu (JSON
  config/tokenizer + .onnx) to dane, nie binarki wykonywalne - idą do
  `datas`, nie `binaries`.

Sam pakiet `gliner` (kod Pythona) + jego zależności (`onnxruntime`, `torch`,
`transformers`) są bundlowane niezależnie od pliku modelu - patrz bloki
`hiddenimports`/`collect_all` niżej.

Tesseract (binarka, nie tylko dane językowe): `resources/tessdata/*.traineddata`
to tylko dane językowe OCR - do działania OCR potrzebna jest też sama binarka
`tesseract.exe` + jej DLL-e, bo `pytesseract` woła ją jako zewnętrzny proces
(`app/pipeline/ocr.py`), nie ma jej wbudowanej w żaden pakiet pip. Workflow
CI (`build-windows.yml`) instaluje portable Tesseract przez Chocolatey i kopiuje
go do `build/vendor/tesseract/` przed uruchomieniem tego spec-a - blok
`_TESSERACT_VENDOR_DIR` niżej podłącza go do bundla, jeśli katalog istnieje.
Runtime, `app/gui/main_window.py` ustawia
`pytesseract.pytesseract.tesseract_cmd` na
`Path(sys.executable).parent / "tesseract" / "tesseract.exe"` (folder obok
głównego .exe w one-dir).
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

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

# Build-time vendorowany plik modelu GLiNER (eksport ONNX + config/tokenizer,
# patrz module docstring wyżej) - pobrany authenticated `gh release download`
# w CI do build/vendor/gliner_model/ PRZED wywołaniem tego spec-a. Guard
# `is_dir()` identyczny jak dla Tesseracta - brak tego katalogu (np. lokalny
# `compile()`-check na Linuksie, albo release usunięty/niedostępny w CI) nie
# wywala parsowania/budowania spec-a, tylko skutkuje aplikacją bez
# zbundlowanego modelu (opcjonalny manualny fallback download_gliner_model()
# nadal działa). Wszystko tu to dane (JSON/ONNX), nie binarki wykonywalne -
# idzie w całości do _datas, bez rozróżnienia jak przy Tesseract/LibreOffice.
_gliner_model_vendor_dir = _PROJECT_ROOT / "build" / "vendor" / "gliner_model"
if _gliner_model_vendor_dir.is_dir():
    for f in _gliner_model_vendor_dir.rglob("*"):
        if f.is_file():
            rel_parent = f.parent.relative_to(_gliner_model_vendor_dir)
            _datas.append((str(f), str(Path("gliner_model") / rel_parent)))

# Build-time vendorowany portable LibreOffice - przygotowywany przez workflow
# CI (choco install libreoffice-still, potem Copy-Item katalogu instalacji do
# build/vendor/libreoffice) PRZED wywołaniem tego spec-a. Ten sam wzorzec
# klasyfikacji binaries/datas co Tesseract wyżej (LibreOffice ma własne
# .exe/.dll), docelowy podkatalog "libreoffice/" obok głównego .exe -
# `legacy_convert._frozen_bundled_soffice_path()` oczekuje go tam.
_libreoffice_vendor_dir = _PROJECT_ROOT / "build" / "vendor" / "libreoffice"
_libreoffice_binaries = []
if _libreoffice_vendor_dir.is_dir():
    for f in _libreoffice_vendor_dir.rglob("*"):
        if f.is_file():
            rel_parent = f.parent.relative_to(_libreoffice_vendor_dir)
            dest = str(Path("libreoffice") / rel_parent)
            is_binary = (
                f.suffix.lower() in (".dll", ".exe")
                or f.suffix.lower() == ".so"
                or ".so." in f.name
                or f.name == "soffice"
            )
            if is_binary:
                _libreoffice_binaries.append((str(f), dest))
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
    # GLiNER (zero-shot NER, patrz app/pipeline/gliner_layer.py) - podobnie do
    # spaCy, komponenty i backendy są ładowane dynamicznie po nazwie.
    "gliner",
    "onnxruntime",
    "onnxruntime.capi",
    "onnxruntime.capi._pybind_state",
    "transformers",
    "torch",
]

# collect_submodules na najbardziej "dynamicznych" pakietach - taniej i
# bezpieczniej niż ręcznie wymieniać każdy możliwy submoduł, a znacznie
# tańsze niż collect_all na całym spacy (które wciągnęłoby też testy/docs).
for _pkg in ("spacy", "thinc", "srsly", "catalogue", "odf", "gliner", "onnxruntime"):
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

# GLiNER - dane pakietu (configi domyślne, brak wag - te są w pliku modelu
# pobieranym na żądanie, patrz komentarz w module docstring wyżej). collect_all
# zwraca (datas, binaries, hiddenimports) tak jak dla modelu spaCy powyżej.
_gliner_binaries = []
try:
    _gliner_datas, _gliner_binaries, _gliner_hidden = collect_all("gliner")
    _datas.extend(_gliner_datas)
    _hiddenimports.extend(_gliner_hidden)
except Exception:
    # `gliner` może nie być zainstalowany w środowisku, w którym ten plik jest
    # tylko parsowany (`compile()`-check na Linuksie) - w CI Windows jest
    # zainstalowany z requirements.txt (patrz komentarz tam o GLiNER).
    pass

# onnxruntime - biblioteka natywna (.dll na Windows, .so na Linuksie) jest
# dystrybuowana jako część pakietu wheela (onnxruntime/capi/*), nie jako
# zwykły kod Pythona - `collect_dynamic_libs` wyszukuje takie pliki binarne
# wewnątrz zainstalowanego pakietu (analogicznie do ręcznego vendoringu
# Tesseracta wyżej, ale tu ścieżka jest już znana z instalacji pip, więc nie
# trzeba osobnego kroku CI).
try:
    _onnxruntime_binaries = collect_dynamic_libs("onnxruntime")
except Exception:
    _onnxruntime_binaries = []

# transformers/torch - biblioteki dodatkowe ciągnięte przez `gliner`; torch
# ma też natywne biblioteki (.dll/.so) dystrybuowane jako część pakietu.
try:
    _torch_datas, _torch_binaries, _torch_hidden = collect_all("torch")
    _datas.extend(_torch_datas)
    _hiddenimports.extend(_torch_hidden)
except Exception:
    _torch_binaries = []

try:
    _datas.extend(collect_data_files("transformers"))
except Exception:
    pass


a = Analysis(
    [_ENTRY_SCRIPT],
    pathex=[str(_PROJECT_ROOT)],
    binaries=_tesseract_binaries + _libreoffice_binaries + _model_binaries + _gliner_binaries + _onnxruntime_binaries + _torch_binaries,
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
