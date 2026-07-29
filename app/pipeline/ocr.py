"""OCR obrazów (skany, obrazy osadzone w dokumentach) przez Tesseract.

Podstawowy preprocessing (skala szarości, binaryzacja progiem Otsu) mocno
podnosi jakość na typowych skanach z kancelarii. `image_to_data` daje
confidence per słowo - średnia poniżej progu oznacza dokument do ostrzeżenia
w UI ("niska jakość OCR, wyniki detekcji mniej pewne").
"""

from __future__ import annotations

from dataclasses import dataclass

import pytesseract
from PIL import Image, ImageOps

_DEFAULT_LANG = "pol+eng"
_LOW_CONFIDENCE_THRESHOLD = 60.0


@dataclass(frozen=True)
class OcrResult:
    text: str
    mean_confidence: float

    @property
    def is_low_quality(self) -> bool:
        return self.mean_confidence < _LOW_CONFIDENCE_THRESHOLD


def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    grayscale = ImageOps.grayscale(image)
    # Binaryzacja prostym progiem (szybka, bez zależności od numpy/opencv).
    # Próg 180 sprawdza się dobrze na typowych skanach dokumentów tekstowych
    # (czarny tekst na jasnym tle) bez potrzeby liczenia histogramu Otsu.
    return grayscale.point(lambda p: 255 if p > 180 else 0)


def run_ocr(image: Image.Image, lang: str = _DEFAULT_LANG) -> OcrResult:
    preprocessed = preprocess_for_ocr(image)
    data = pytesseract.image_to_data(
        preprocessed, lang=lang, output_type=pytesseract.Output.DICT
    )
    confidences = [int(c) for c in data.get("conf", []) if c not in ("-1", -1)]
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    text = pytesseract.image_to_string(preprocessed, lang=lang)
    return OcrResult(text=text, mean_confidence=mean_confidence)
