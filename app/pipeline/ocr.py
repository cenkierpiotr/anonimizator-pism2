"""OCR obrazów (skany, obrazy osadzone w dokumentach) przez Tesseract.

Preprocessing (patrz plan, sekcja "Wydajność i responsywność GUI" - adaptacyjne
DPI/PSM, deskew, binaryzacja, redukcja szumu) mocno podnosi jakość na typowych
skanach z kancelarii, które bywają lekko przekrzywione (skaner z podajnikiem),
w niskiej rozdzielczości (osadzone miniatury) i zaszumione (ziarno skanera).

`image_to_data` daje confidence per słowo - średnia poniżej progu oznacza
dokument do ostrzeżenia w UI ("niska jakość OCR, wyniki detekcji mniej
pewne") ORAZ sygnał do adaptacyjnej zmiany PSM (page segmentation mode):
domyślny PSM 6 (jednolity blok tekstu) sprawdza się na typowych pismach, ale
przy niskim confidence próbujemy PSM 3 (pełna automatyka układu) i PSM 11
(rozproszony tekst - tabele, formularze), zatrzymując najlepszy wynik.
"""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytesseract
from PIL import Image, ImageFilter, ImageOps

_DEFAULT_LANG = "pol+eng"
_LOW_CONFIDENCE_THRESHOLD = 60.0

# Adaptacyjne DPI: obrazy węższe niż to (np. osadzone miniatury w DOCX/ODT,
# skany zapisane w niskiej rozdzielczości) skalujemy w górę przed OCR -
# Tesseract wyraźnie traci jakość poniżej ~150-200 DPI efektywnego, a typowy
# render PDF-a w tym projekcie to już ok. 300 DPI (patrz pdf_reader.py), więc
# próg dotyczy głównie obrazów spoza tej ścieżki.
_MIN_OCR_WIDTH_PX = 1500

# Deskew metodą profilu projekcji: wystarcza do korekty kilku stopni typowych
# dla skanów z automatycznego podajnika (ADF), bez potrzeby OpenCV/Hough.
_DESKEW_MAX_ANGLE = 5.0
_DESKEW_STEP = 0.5

# Kolejność prób PSM przy adaptacyjnym retry - patrz docstring modułu.
_PSM_ATTEMPTS: tuple[int, ...] = (6, 3, 11)


def _configure_bundled_tesseract() -> None:
    """W buildzie PyInstaller (patrz `build/anonimizator.spec`) binarka
    Tesseract jest zvendorowana obok .exe w podkatalogu `tesseract/`, bo
    `pytesseract` woła ją jako zewnętrzny proces, nie przez import - bez tego
    ustawienia zbundlowana aplikacja szukałaby `tesseract` w systemowym PATH,
    którego na czystym Windows/Linuksie użytkownika końcowego nie ma.

    Na Linuksie binarka `tesseract` (bez rozszerzenia) jest wynoszona razem z
    jej rozwiązanymi bibliotekami współdzielonymi (.so) do tego samego
    podkatalogu (patrz `.github/workflows/build-linux.yml`) - ustawiamy tam
    dodatkowo `LD_LIBRARY_PATH`, żeby dynamiczny linker sięgnął po
    zvendorowane wersje, a nie po (niepewne, zależne od dystrybucji)
    biblioteki systemowe. `TESSDATA_PREFIX` wskazujemy jawnie na bundlowany
    `resources/tessdata`, bo systemowy pakiet Tesseract na Linuksie ma swój
    własny, inny domyślny katalog danych językowych."""
    if not getattr(sys, "frozen", False):
        return
    bundled_dir = Path(sys.executable).parent / "tesseract"
    binary_name = "tesseract.exe" if platform.system() == "Windows" else "tesseract"
    bundled = bundled_dir / binary_name
    if bundled.exists():
        pytesseract.pytesseract.tesseract_cmd = str(bundled)
        if platform.system() != "Windows":
            existing_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
            os.environ["LD_LIBRARY_PATH"] = (
                f"{bundled_dir}{os.pathsep}{existing_ld_path}" if existing_ld_path else str(bundled_dir)
            )

    tessdata_dir = Path(sys.executable).parent / "resources" / "tessdata"
    if tessdata_dir.is_dir():
        os.environ["TESSDATA_PREFIX"] = str(tessdata_dir)


_configure_bundled_tesseract()


@dataclass(frozen=True)
class OcrResult:
    text: str
    mean_confidence: float
    # Który PSM dał finalny wynik - przydatne do debugowania/telemetrii, nie
    # zmienia istniejącego API (pole ma wartość domyślną).
    psm_used: int = _PSM_ATTEMPTS[0]

    @property
    def is_low_quality(self) -> bool:
        return self.mean_confidence < _LOW_CONFIDENCE_THRESHOLD


def _otsu_threshold(gray: np.ndarray) -> int:
    """Klasyczny próg Otsu (maksymalizacja wariancji międzyklasowej) liczony
    ręcznie na histogramie 256-kubełkowym - bez zależności od OpenCV. Radzi
    sobie lepiej niż stały próg na skanach o zmiennym oświetleniu/kontraście
    niż jeden sztywno dobrany próg (poprzednia wersja: stałe 180)."""
    histogram, _ = np.histogram(gray, bins=256, range=(0, 256))
    total = int(gray.size)
    sum_total = float(np.dot(np.arange(256), histogram))

    sum_bg = 0.0
    weight_bg = 0
    max_variance = -1.0
    threshold = 127

    for t in range(256):
        weight_bg += int(histogram[t])
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += t * histogram[t]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_total - sum_bg) / weight_fg
        variance = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if variance > max_variance:
            max_variance = variance
            threshold = t

    return threshold


def estimate_skew_angle(grayscale: Image.Image) -> float:
    """Szacuje kąt przekrzywienia (w stopniach) metodą profilu projekcji: dla
    każdego kandydującego kąta w zakresie +/-`_DESKEW_MAX_ANGLE` obraca
    miniaturę obrazu i liczy wariancję sum jasności w wierszach pikseli.
    Poziomo ułożone linie tekstu dają ostre naprzemienne pasma jasny/ciemny
    (wysoka wariancja rzędów), przekrzywienie je rozmywa (niska wariancja) -
    kąt maksymalizujący wariancję to najlepsza estymata korekty. Liczone na
    pomniejszonej miniaturze dla szybkości."""
    thumb = grayscale.copy()
    thumb.thumbnail((600, 600))

    best_angle = 0.0
    best_score = -1.0
    angle = -_DESKEW_MAX_ANGLE
    while angle <= _DESKEW_MAX_ANGLE + 1e-9:
        if angle == 0.0:
            rotated = thumb
        else:
            rotated = thumb.rotate(angle, expand=True, fillcolor=255, resample=Image.BICUBIC)
        arr = np.asarray(rotated, dtype=np.float64)
        row_sums = arr.sum(axis=1)
        score = float(np.var(row_sums))
        if score > best_score:
            best_score = score
            best_angle = angle
        angle += _DESKEW_STEP

    return best_angle


def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """Pełny pipeline preprocessingu: skala szarości -> adaptacyjne
    skalowanie DPI -> deskew -> redukcja szumu -> binaryzacja progiem Otsu."""
    grayscale = ImageOps.grayscale(image)

    if grayscale.width < _MIN_OCR_WIDTH_PX:
        scale = _MIN_OCR_WIDTH_PX / grayscale.width
        new_size = (round(grayscale.width * scale), round(grayscale.height * scale))
        grayscale = grayscale.resize(new_size, resample=Image.LANCZOS)

    angle = estimate_skew_angle(grayscale)
    if abs(angle) >= _DESKEW_STEP:
        grayscale = grayscale.rotate(angle, expand=True, fillcolor=255, resample=Image.BICUBIC)

    # Redukcja szumu (ziarno skanera/plamki) filtrem medianowym - zachowuje
    # krawędzie liter lepiej niż rozmycie Gaussa, co ma znaczenie tuż przed
    # binaryzacją progiem.
    denoised = grayscale.filter(ImageFilter.MedianFilter(size=3))

    arr = np.asarray(denoised)
    threshold = _otsu_threshold(arr)
    return denoised.point(lambda p, t=threshold: 255 if p > t else 0)


def _ocr_attempt(image: Image.Image, lang: str, psm: int) -> OcrResult:
    config = f"--psm {psm}"
    data = pytesseract.image_to_data(
        image, lang=lang, config=config, output_type=pytesseract.Output.DICT
    )
    # Tesseract czasem przypisuje wysoki `conf` tokenom, których rozpoznany
    # tekst jest pusty/samą spacją (widmowe wykrycie "słowa" bez żadnych
    # rozpoznanych znaków) - bez odfiltrowania ich tutaj, PSM który nie
    # przeczytał NIC może dostać wyższą średnią pewność niż PSM, który
    # faktycznie coś odczytał, i adaptacyjny retry wybierze ten gorszy,
    # milczący wynik jako "najlepszy" (ostrzeżenie o niskiej jakości nigdy
    # się wtedy nie pojawi, mimo braku odczytanego tekstu).
    confidences = [
        int(conf)
        for conf, text in zip(data.get("conf", []), data.get("text", []))
        if conf not in ("-1", -1) and text.strip()
    ]
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    text = pytesseract.image_to_string(image, lang=lang, config=config)
    return OcrResult(text=text, mean_confidence=mean_confidence, psm_used=psm)


def run_ocr(image: Image.Image, lang: str = _DEFAULT_LANG) -> OcrResult:
    """Uruchamia OCR z preprocessingiem i adaptacyjnym doborem PSM: zaczyna od
    domyślnego PSM 6 (jednolity blok tekstu - typowe dla pism prawniczych), a
    jeśli wynik ma niską pewność, próbuje kolejnych trybów z `_PSM_ATTEMPTS`
    (PSM 3 - pełna automatyka układu strony, PSM 11 - tekst rozproszony,
    dobre dla tabel/formularzy), zatrzymując najlepszy uzyskany wynik."""
    preprocessed = preprocess_for_ocr(image)

    best = _ocr_attempt(preprocessed, lang, _PSM_ATTEMPTS[0])

    for psm in _PSM_ATTEMPTS[1:]:
        if not best.is_low_quality:
            break
        candidate = _ocr_attempt(preprocessed, lang, psm)
        if candidate.mean_confidence > best.mean_confidence:
            best = candidate

    return best
