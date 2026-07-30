# Anonimizator Pism

Lokalna, w pełni offline aplikacja Windows do anonimizacji dokumentów prawniczych.
Przyjmuje dowolny format wejściowy (PDF z tekstem, PDF skan, DOCX, DOC, ODT, TXT,
obraz skanu) i zwraca `.docx` z zanonimizowanymi danymi wrażliwymi (osoby, adresy,
telefony, PESEL/NIP/REGON/KRS, numery ksiąg wieczystych, IBAN, sygnatury akt i wiele
innych kategorii — pełna lista w planie projektu, patrz niżej).

Anonimizacja jest **nieodwracalna**: numeracja etykiet (`[Osoba 1]`, `[numer telefonu 2]`)
żyje wyłącznie w pamięci procesu na czas przetwarzania jednego pliku i nigdy nie jest
zapisywana na dysk. Przed zapisem finalnego pliku aplikacja pokazuje obowiązkowy ekran
weryfikacji (wykryte encje + lista "potencjalnie pominięte" do ręcznego sprawdzenia).

Pełny opis architektury, decyzji projektowych i uzasadnień: `/config/.claude/plans/concurrent-stirring-panda.md`
(plan projektu — źródło prawdy dla zakresu funkcjonalnego).

## Funkcje

- Obsługa formatów: PDF (tekst i skan), DOCX, DOC (przez opcjonalny, pobierany na
  żądanie LibreOffice), ODT, TXT, obrazy (JPG/PNG/TIFF).
- OCR (Tesseract, `pol+eng`) z ostrzeżeniem przy niskiej pewności rozpoznania.
- Detekcja wielowarstwowa: regexy z checksumami, gazetteery (imiona/nazwiska/miejscowości),
  wzorce ról prawnych, spaCy NER (`pl_core_news_md`), drugi przebieg literalny (formy
  fleksyjne znalezionych nazwisk), heurystyka "potencjalnie pominięte" (tokeny z wielkiej
  litery nie złapane przez żadną warstwę — sygnał do ręcznego sprawdzenia, nie automatyczna
  anonimizacja).
- Kolejka wielu plików jednocześnie w GUI, każdy plik z własną, niezależną numeracją.
- Osobna funkcja "Konwertuj do PDF" (DOC/DOCX → PDF), niezależna od anonimizacji.
- Opcjonalny tryb date-shifting (przesunięcie wszystkich dat w dokumencie o ten sam
  losowy offset — zachowuje odstępy między zdarzeniami, ukrywa rzeczywiste daty).
- Wykrywanie i usuwanie ochrony edycji dokumentu (`w:documentProtection`) w wyniku.
- Ostrzeżenie przy dokumencie obcojęzycznym (NER trenowany na polskim korpusie).
- Czyszczenie metadanych (`docProps`, nazwa pliku) i obowiązkowy re-skan "leak" przed
  każdym zapisem — blokada zapisu, jeśli jakikolwiek zwalidowany identyfikator przetrwał.
- Higiena plików tymczasowych: katalogi stagingu starsze niż 24h sprzątane przy starcie.

## Rozwój (Linux, ten katalog)

Kod i logika (detektory, pipeline, GUI przez Tk) są w pełni testowalne na Linuksie.
Tylko finalny `.exe`/instalator Windows wymaga natywnego builda — patrz sekcja "Build
Windows" niżej.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

Model NER (`pl_core_news_md`) jest już przypięty w `requirements.txt` jako bezpośredni
URL do wheela z GitHub Releases spaCy — `pip install -r requirements.txt` go instaluje,
nie trzeba osobnego `python -m spacy download`.

Uruchomienie GUI lokalnie (wymaga środowiska z wyświetlaczem/X11):

```
python -m app.gui.main_window
```

## Build Windows

Finalny `.exe`/instalator powstaje wyłącznie przez GitHub Actions
(`.github/workflows/build-windows.yml`, runner `windows-latest`) — PyInstaller nie
kompiluje krzyżowo z Linuksa. Workflow uruchamia się automatycznie przy push do `main`
oraz ręcznie (`workflow_dispatch`). Kroki: `pyinstaller build/anonimizator.spec`
(one-dir, nie one-file — patrz uzasadnienie w pliku `.spec`) → `iscc build/installer.iss`
(Inno Setup, instalacja per-user do `%LOCALAPPDATA%`, bez wymogu uprawnień admina).

**Instalator jest obecnie niepodpisany** (brak certyfikatu OV/EV — świadomie odłożone
do Fazy 5 planu). Przy pierwszym uruchomieniu na komputerze użytkownika SmartScreen
niemal na pewno pokaże ostrzeżenie "Windows chronił Twój komputer", a niektóre
antywirusy mogą fałszywie zaflagować plik (PyInstaller jest w tym notorycznie częsty).
To oczekiwane, nie błąd builda.

## Zależności i licencje

Kluczowe wybory biblioteczne i uzasadnienia (pełne w planie projektu):

- `pypdfium2` (nie PyMuPDF) do obsługi PDF — PyMuPDF jest na AGPL v3, co
  wymagałoby udostępnienia źródeł całej aplikacji przy dystrybucji `.exe`.
- `pl_core_news_md` (nie `_lg`) — bazuje na korpusie NKJP (bywa CC BY-SA, wymaga
  co najmniej atrybucji przy redystrybucji — do uwzględnienia w pliku licencji
  dołączanym do instalatora przed pierwszym wydaniem).
- LibreOffice (obsługa `.doc`) pobierany na żądanie z GitHub Releases projektu,
  nie wchodzi do bazowego instalatora — patrz `app/pipeline/legacy_convert.py`.
