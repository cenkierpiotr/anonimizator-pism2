# Anonimizator Pism

Lokalna, w pełni offline aplikacja Windows do anonimizacji dokumentów prawniczych.
Przyjmuje dowolny format wejściowy (PDF z tekstem, PDF skan, DOCX, DOC, ODT, TXT,
obraz skanu) i zwraca `.docx` z zanonimizowanymi danymi wrażliwymi (osoby, adresy,
telefony, PESEL/NIP/REGON/KRS, numery ksiąg wieczystych, IBAN, sygnatury akt i wiele
innych kategorii — pełny opis w [docs/PLAN.md](docs/PLAN.md)).

Anonimizacja jest **nieodwracalna**: numeracja etykiet (`[Osoba 1]`, `[numer telefonu 2]`)
żyje wyłącznie w pamięci procesu na czas przetwarzania jednego pliku i nigdy nie jest
zapisywana na dysk. Przed zapisem finalnego pliku aplikacja pokazuje obowiązkowy ekran
weryfikacji (wykryte encje + lista "potencjalnie pominięte" do ręcznego sprawdzenia).

Pełny opis architektury, decyzji projektowych i uzasadnień: [docs/PLAN.md](docs/PLAN.md)
(plan projektu — źródło prawdy dla zakresu funkcjonalnego).

## Dla kogo jest ta aplikacja

Dla prawników, kancelarii i każdego, kto musi udostępnić treść pisma sądowego,
umowy, aktu notarialnego czy wezwania do zapłaty (np. do publikacji, szkolenia,
konsultacji, wzoru) bez ujawniania danych osobowych stron. Wszystko dzieje się
lokalnie na komputerze użytkownika — dokument **nigdy nie jest wysyłany donikąd**
(z jednym wyjątkiem opisanym w sekcji "Uwaga o trybie offline" niżej).

## Instalacja (dla użytkowników nietechnicznych — jeden plik, jeden klik)

1. Przejdź do zakładki **[Releases](../../releases)** tego repozytorium (link
   widoczny też po prawej stronie strony głównej repo na GitHubie, sekcja
   "Releases").
2. Pobierz najnowszy plik z rozszerzeniem `.exe` (np. `AnonimizatorPism-Setup-0.1.0.exe`)
   — to jest jedyny plik potrzebny do instalacji.
3. Uruchom pobrany plik podwójnym kliknięciem.
4. **Windows prawie na pewno pokaże niebieski ekran "Windows chronił Twój
   komputer" (SmartScreen)** — to nie oznacza wirusa, tylko brak (kosztownego)
   cyfrowego podpisu instalatora. Kliknij **"Więcej informacji"**, a następnie
   **"Uruchom mimo to"**.
   - Z tego samego powodu niektóre antywirusy mogą chwilowo oznaczyć plik jako
     podejrzany (PyInstaller, którym zbudowana jest aplikacja, jest w tym
     notorycznie częsty — to fałszywy alarm, nie prawdziwe zagrożenie).
5. Instalator nie wymaga uprawnień administratora — instaluje się tylko dla
   Twojego konta użytkownika. Kliknij **Dalej → Dalej → Zainstaluj**.
6. Po instalacji na pulpicie pojawi się skrót **"Anonimizator Pism"** — gotowe,
   aplikacja jest zainstalowana i gotowa do użycia.
7. Przy pierwszym wrzuceniu pliku `.doc` (stary format Worda) aplikacja
   zapyta o pobranie dodatkowego komponentu (~300 MB, LibreOffice, potrzebny
   tylko do konwersji `.doc`) — to jedyny moment, w którym aplikacja łączy się
   z internetem, patrz uwaga niżej.

Nie trzeba niczego więcej instalować — żadnego Pythona, żadnych dodatkowych
programów. Wszystko potrzebne (silnik OCR, model rozpoznawania danych) jest już
w instalatorze.

### Jak korzystać

1. Otwórz aplikację ze skrótu na pulpicie.
2. Przeciągnij plik (lub kilka plików naraz) do okna aplikacji albo użyj
   przycisku wyboru pliku.
3. Poczekaj na przetworzenie (skany OCR mogą potrwać dłużej — pasek postępu
   pokazuje stan).
4. Sprawdź ekran weryfikacji: lista wykrytych i podmienionych danych, oraz
   osobna lista "potencjalnie pominięte" do ręcznego sprawdzenia. Możesz
   odznaczyć błędnie wykryty fragment albo ręcznie dodać pominięty.
5. Zatwierdź i zapisz — powstaje plik `<nazwa>_zanonimizowany.docx`.

### Uwaga o trybie offline

Aplikacja przetwarza dokumenty w 100% lokalnie i nigdy nie wysyła ich treści
donikąd. Jedyny wyjątek: opcjonalna obsługa starych plików `.doc` wymaga
jednorazowego pobrania LibreOffice (~300 MB) — dzieje się to tylko za Twoją
wyraźną zgodą, tylko raz (plik jest potem cache'owany lokalnie), i **nie jest
wymagane**, jeśli nie pracujesz z plikami `.doc`. Jeśli komputer jest odcięty
od internetu, można wskazać aplikacji już zainstalowany LibreOffice na dysku
albo zainstalować komponent z pliku pobranego wcześniej na innym komputerze.

## Funkcje

- Obsługa formatów: PDF (tekst i skan), DOCX, DOC (przez opcjonalny, pobierany na
  żądanie LibreOffice), ODT, TXT, obrazy (JPG/PNG/TIFF).
- OCR (Tesseract, `pol+eng`) z ostrzeżeniem przy niskiej pewności rozpoznania.
- Detekcja wielowarstwowa: regexy z checksumami, gazetteery (imiona/nazwiska/miejscowości,
  zbudowane z pełnych oficjalnych rejestrów publicznych — patrz
  [resources/gazetteers/SOURCES.md](resources/gazetteers/SOURCES.md)), wzorce ról
  prawnych, spaCy NER (`pl_core_news_md`), drugi przebieg literalny (formy
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

## Ograniczenia i uczciwe zastrzeżenia

Żaden automatyczny system detekcji (włącznie z modelami NER znacznie droższymi
niż te użyte tutaj) nie gwarantuje 100% wykrycia wszystkich danych wrażliwych w
dowolnym tekście. Dlatego:

- Aplikacja pokazuje **obowiązkowy ekran weryfikacji przed zapisem** — to
  narzędzie ma wspierać ludzką weryfikację, nie zastępować jej.
- Sekcja "potencjalnie pominięte" na tym ekranie to aktywne narzędzie wykrywania
  fałszywych negatywów, nie tylko formalność — warto ją przejrzeć przy
  poufnych dokumentach.
- Instalator jest **niepodpisany cyfrowo** (brak certyfikatu OV/EV) — stąd
  ostrzeżenie SmartScreen opisane w instrukcji instalacji. To nie oznacza
  niższej jakości kodu, tylko brak opłaconego certyfikatu.
- Jakość detekcji jest mierzona na syntetycznym złotym zbiorze
  (`scripts/golden_dataset.py`, wyniki w `scripts/golden_report.md`) — 100%
  recall na tym zbiorze nie jest gwarancją 100% recall na każdym możliwym
  dokumencie realnym.

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

Uruchomienie GUI lokalnie (wymaga środowiska z wyświetlaczem/X11 albo Xvfb):

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
Gotowy plik `.exe` trafia jako artefakt workflow (`anonimizator-pism-installer`) oraz,
przy publikacji release'u, do zakładki Releases repozytorium.

**Instalator jest obecnie niepodpisany** (brak certyfikatu OV/EV — świadomie odłożone
do późniejszej fazy). Przy pierwszym uruchomieniu na komputerze użytkownika SmartScreen
niemal na pewno pokaże ostrzeżenie "Windows chronił Twój komputer", a niektóre
antywirusy mogą fałszywie zaflagować plik (PyInstaller jest w tym notorycznie częsty).
To oczekiwane, nie błąd builda — patrz instrukcja instalacji wyżej.

## Zależności i licencje

Ten projekt jest na licencji **MIT** — patrz [LICENSE](LICENSE). Pełna lista
licencji zależności runtime (w tym uzasadnienie wyboru `pypdfium2` zamiast
PyMuPDF ze względu na AGPL) — patrz [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
Pochodzenie danych gazetteerów (imiona/nazwiska/miejscowości) — patrz
[resources/gazetteers/SOURCES.md](resources/gazetteers/SOURCES.md).

## Golden dataset / jakość detekcji

`scripts/golden_dataset.py` generuje syntetyczne pisma prawnicze (pozew, akt
notarialny, wyrok, wezwanie do zapłaty) wypełnione losowymi, ale poprawnymi pod
względem checksumy danymi (PESEL/NIP/IBAN) oraz imionami/nazwiskami/
miejscowościami z tych samych gazetteerów co produkcyjny pipeline, ze znanym z
góry rozmieszczeniem danych wrażliwych (ground truth). Uruchamia na nich
prawdziwy pipeline detekcji (`detect_in_text`) i liczy recall/precision per
kategoria — patrz [docs/PLAN.md](docs/PLAN.md), sekcja "Weryfikacja". To narzędzie
deweloperskie (nie jest częścią wysyłanej aplikacji, celowo nie jest wpięte w
CI/pytest — regresja jakości detekcji ma być widoczna dla człowieka przy
ręcznym uruchomieniu, nie automatycznie czerwienić builda).

```
source .venv/bin/activate
python3 scripts/golden_dataset.py --n 30 --seed 42
```

Wynik trafia na stdout i do `scripts/golden_report.md`.

## Zgłaszanie problemów

To repozytorium jest obecnie prywatne / w przygotowaniu do publikacji. Po
udostępnieniu — zgłoszenia błędów i propozycje przez zakładkę Issues tego
repozytorium.
