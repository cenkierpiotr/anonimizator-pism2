# Licencje zależności

Ten projekt (kod własny w tym repozytorium) jest na licencji MIT — patrz [LICENSE](LICENSE).
Poniżej lista kluczowych zależności runtime i ich licencji, ważna przy dystrybucji
zbudowanego instalatora `.exe`.

| Zależność | Licencja | Uwagi |
|---|---|---|
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | Apache-2.0 / BSD-3-Clause | Świadomie wybrane zamiast PyMuPDF (AGPL v3) — patrz [docs/PLAN.md](docs/PLAN.md), sekcja "Stack technologiczny". |
| [python-docx](https://github.com/python-openxml/python-docx) | MIT | |
| [lxml](https://lxml.de/) | BSD-3-Clause | |
| [pytesseract](https://github.com/madmaze/pytesseract) | Apache-2.0 | Wrapper Pythona; sam silnik Tesseract OCR (dołączony do instalatora binarnie) też Apache-2.0. |
| [Pillow](https://python-pillow.org/) | MIT-CMU (HPND) | |
| [numpy](https://numpy.org/) | BSD-3-Clause | |
| [spaCy](https://spacy.io/) | MIT | |
| Model `pl_core_news_md` | MIT (kod modelu) | Model treningowy bazuje częściowo na korpusie NKJP (Narodowy Korpus Języka Polskiego), który bywa udostępniany na licencji **CC BY-SA** — przy redystrybucji wymagana jest co najmniej atrybucja. Ten plik stanowi tę atrybucję. |
| [odfpy](https://github.com/eea/odfpy) | Apache-2.0 (GPL-2.0 dla części historycznych) | Używane tylko do odczytu `.odt`. |
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | MIT | |
| Tesseract OCR + dane `pol.traineddata`/`eng.traineddata` | Apache-2.0 | |
| LibreOffice (pobierany opcjonalnie na żądanie, nie wchodzi do bazowego instalatora) | MPL-2.0 | Hostowany we własnym GitHub Releases projektu — dozwolone na licencji MPL. |

Dane gazetteerów (imiona, nazwiska, miejscowości) — pochodzenie i licencje opisane
osobno w [resources/gazetteers/SOURCES.md](resources/gazetteers/SOURCES.md)
(wszystkie źródła to otwarte rejestry publiczne, CC0 lub wymagające jedynie atrybucji).
