# Anonimizator Dokumentów

Lokalna, w pełni offline aplikacja Windows do anonimizacji dokumentów (ze
szczególnym uwzględnieniem pism prawniczych — pozwów, umów, aktów notarialnych,
wyroków — ale nie tylko). Przyjmuje dowolny format wejściowy (PDF z tekstem,
PDF skan, DOCX, DOC, ODT, TXT, obraz skanu) i zwraca `.docx` z zanonimizowanymi
danymi wrażliwymi, zachowując czytelność i kontekst dokumentu.

Anonimizacja jest **nieodwracalna**: numeracja etykiet (`[Osoba 1]`, `[numer telefonu 2]`)
żyje wyłącznie w pamięci procesu na czas przetwarzania jednego pliku i nigdy nie jest
zapisywana na dysk. Przed zapisem finalnego pliku aplikacja pokazuje obowiązkowy ekran
weryfikacji (wykryte encje + lista "potencjalnie pominięte" do ręcznego sprawdzenia).

Pełny opis architektury, decyzji projektowych i uzasadnień: [docs/PLAN.md](docs/PLAN.md)
(plan projektu — źródło prawdy dla zakresu funkcjonalnego).

## Dla kogo jest ta aplikacja

Dla prawników, kancelarii i każdego, kto musi udostępnić treść dokumentu —
pisma sądowego, umowy, aktu notarialnego, wezwania do zapłaty, ale też innej
korespondencji czy dokumentacji zawierającej dane osobowe (np. do publikacji,
szkolenia, konsultacji, wzoru) — bez ujawniania danych osobowych stron.
Wszystko dzieje się lokalnie na komputerze użytkownika — dokument **nigdy nie
jest wysyłany donikąd** (z jednym wyjątkiem opisanym w sekcji "Uwaga o trybie
offline" niżej).

## Instalacja (dla użytkowników nietechnicznych — jeden plik, jeden klik)

1. Przejdź do zakładki **[Releases](../../releases)** tego repozytorium (link
   widoczny też po prawej stronie strony głównej repo na GitHubie, sekcja
   "Releases").
2. Pobierz najnowszy plik z rozszerzeniem `.exe` (np. `AnonimizatorDokumentow-Setup-0.1.0.exe`)
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
6. Po instalacji na pulpicie pojawi się skrót **"Anonimizator Dokumentów"** — gotowe,
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

- Obsługa formatów wejściowych: PDF z warstwą tekstową, PDF-skan (bez tekstu), DOCX, DOC (przez opcjonalny, pobierany na żądanie LibreOffice), ODT, TXT, obrazy (JPG/PNG/TIFF)
- OCR (Tesseract, `pol+eng`) z ostrzeżeniem przy niskiej pewności rozpoznania i tolerancją typowych pomyłek OCR w danych ze checksumem (O/0, l/1/I, S/5, B/8, Z/2)
- Automatyczne rozpoznanie obcojęzycznego dokumentu i ostrzeżenie, że detekcja osób może być ograniczona (modele trenowane na polskim korpusie)
- Wielowarstwowa detekcja danych łącząca regexy z checksumami, gazetteery zbudowane z pełnych oficjalnych rejestrów publicznych, wzorce ról prawnych, model NER oraz drugi przebieg literalny na formach fleksyjnych znalezionych nazwisk — patrz sekcja "Zastosowane modele i mechanizmy detekcji" niżej
- Numerowanie etykiet per kategoria i per dokument (`[Osoba 1]`, `[Osoba 2]`, `[numer telefonu 1]`...) — ta sama wartość w różnych miejscach dokumentu dostaje ten sam numer, różne wartości różne numery, więc kontekst "kto jest kim" zostaje zachowany mimo anonimizacji
- Obsługa zagnieżdżeń i kolizji (np. nazwisko wewnątrz nazwy jednoosobowej działalności gospodarczej) — oba fragmenty anonimizowane osobno, żadna dana nie wycieka przez nadrzędną encję
- Zachowanie formatowania i układu oryginału w wyjściowym `.docx`, łącznie z nagłówkami, stopkami, przypisami, komentarzami, polami tekstowymi i hiperłączami
- Obowiązkowy ekran weryfikacji przed zapisem: lista wszystkich wykrytych i podmienionych fragmentów pogrupowana wg kategorii, podgląd dokumentu z podświetleniami, możliwość odznaczenia błędnego trafienia lub ręcznego dopisania pominiętego fragmentu
- Heurystyka "potencjalnie pominięte": każdy token pisany wielką literą (nie na początku zdania), nieznany jako rzeczownik pospolity i niezłapany przez żadną warstwę detekcji, trafia na osobną listę do ręcznego sprawdzenia — zamiast być cicho pomijany
- Kolejka wielu plików jednocześnie w GUI, każdy plik z własną, niezależną numeracją etykiet
- Osobna funkcja "Konwertuj do PDF" (DOC/DOCX → PDF), niezależna od anonimizacji
- Opcjonalny tryb date-shifting: przesunięcie wszystkich dat w dokumencie o ten sam losowy offset — zachowuje odstępy między zdarzeniami (czytelne terminy/przedawnienia), a jednocześnie ukrywa rzeczywiste daty
- Wykrywanie i usuwanie ochrony edycji dokumentu (`w:documentProtection`) w pliku wynikowym
- Obowiązkowy re-skan "leak" całego wygenerowanego pliku przed zapisem — blokada zapisu, jeśli jakikolwiek zwalidowany identyfikator (PESEL, NIP, IBAN, itd.) przetrwał w dowolnej części pakietu `.docx`
- Czyszczenie metadanych dokumentu (`docProps`, autor, nazwa pliku wyjściowa) tak, by sam plik wynikowy też nie ujawniał danych osobowych
- Obsługa PDF zabezpieczonych hasłem — czytelny monit o hasło zamiast surowego błędu
- Higiena plików tymczasowych: dedykowany katalog roboczy per uruchomienie, czyszczony automatycznie, katalogi stagingu starsze niż 24h sprzątane przy starcie aplikacji
- Pipeline przetwarzania w osobnym wątku z paskiem postępu i przyciskiem anulowania — GUI nie zamraża się przy długim OCR

## Wykrywane i anonimizowane kategorie danych

Etykiety numerowane (ta sama wartość = ten sam numer w obrębie jednego dokumentu):

- imiona i nazwiska osób (klastrowane per dokument: `[Osoba 1]`, `[Osoba 2]`...)
- numery telefonów, w tym formaty zagraniczne i różne zapisy separatorów
- adresy zamieszkania/siedziby (ulica, numer, kod pocztowy, miejscowość), także zapisy skrócone bez prefiksu ulicy, samą nazwę ulicy bez numeru budynku (np. "ul. Moniuszki") oraz wyliczenia kilku ulic po jednym wspólnym słowie "ulicami" (typowe w opisach granic działek)
- adresy e-mail
- nazwy i adresy sądów oraz innych instytucji/organów (prokuratura, urzędy, KRS), a także nazwy spółek/firm rozpoznawane po przyrostku formy prawnej (sp. z o.o., S.A., sp. k., sp. j., s.c. i warianty)
- PESEL
- NIP
- REGON
- numer KRS
- numer księgi wieczystej (z walidacją sumy kontrolnej)
- numer działki ewidencyjnej i obręb, identyfikator TERYT działki
- IBAN / numer rachunku bankowego (z walidacją sumy kontrolnej; numery o poprawnym kształcie, ale niezgodne z sumą kontrolną — np. wskutek literówki lub błędu OCR — są dodatkowo wykrywane niżej-priorytetowym wzorcem zapasowym, żeby nie przepuścić ich cicho)
- numery faktur i umów, w tym kredytowych
- numery polis ubezpieczeniowych i numery szkód
- numer dowodu osobistego (z walidacją sumy kontrolnej), paszportu, karty pobytu, prawa jazdy
- numer VIN pojazdu i numer rejestracyjny
- NPWZ (numer prawa wykonywania zawodu lekarza)
- sygnatury akt sądowych, rozpoznawane osobno wg podtypu: cywilne/gospodarcze, karne, prokuratorskie, policyjne, administracyjne, Sądu Najwyższego/KIO, komornicze
- numer aktu notarialnego
- numer aktu stanu cywilnego (USC), numer aktu poświadczenia dziedziczenia, wpis w Rejestrze Spadkowym
- adres IP (v4/v6), IMEI, adresy URL, nazwy użytkownika/profile w mediach społecznościowych
- dane notariusza (imię, nazwisko, nazwa i adres kancelarii)
- dane pełnomocników/adwokatów/radców prawnych, w tym numer wpisu na listę zawodową

Kategorie z osobną polityką (nienumerowane domyślnie, bo identyczna wartość nie oznacza tu tego samego obiektu):

- daty — domyślnie pozostawione (terminy są sednem dokumentu), poza datami urodzenia/zgonu wykrywanymi kontekstowo; opcjonalny tryb date-shifting
- kwoty pieniężne — domyślnie zamieniane na `[kwota]` bez numeru (numerowanie sugerowałoby nieistniejący związek między różnymi kwotami)

## Zastosowane modele i mechanizmy detekcji

Żaden pojedynczy model nie wykrywa 100% danych wrażliwych w dowolnym tekście —
dlatego aplikacja łączy kilka niezależnych warstw zamiast polegać na jednym
"AI", a wynik zawsze przechodzi przez obowiązkową weryfikację użytkownika:

- **Model NER (Named Entity Recognition) — spaCy `pl_core_news_md`.**
  Statystyczny model rozpoznawania nazwanych encji wytrenowany na polskim
  korpusie językowym (NKJP), rozpoznaje kandydatów na kategorie
  PERSON (osoby), ORG (organizacje/instytucje) i LOC (miejsca). Działa w
  pełni lokalnie na CPU, bez GPU, bez łączności z internetem — model jest
  zapisany w instalatorze. Ograniczenie: jak każdy model NER, myli się na
  rzadkich/nietypowo odmienionych nazwiskach i tekstach mocno odbiegających
  stylistycznie od danych treningowych (stąd kolejne, uzupełniające warstwy
  poniżej).
- **OCR — Tesseract 5.x z modelami językowymi `pol` i `eng`.** Silnik
  rozpoznawania tekstu z obrazu/skanu, z podstawowym preprocessingiem
  (deskew, binaryzacja) i adaptacyjnym doborem parametrów. Podaje też pewność
  rozpoznania per słowo — przy niskiej średniej aplikacja pokazuje ostrzeżenie,
  a detektory ze sumą kontrolną przechodzą w tryb tolerancyjny na typowe
  pomyłki znaków.
- **Gazetteery (słowniki referencyjne) imion, nazwisk i miejscowości** —
  zbudowane z pełnych, oficjalnych, otwartych rejestrów publicznych (rejestr
  PESEL przez dane.gov.pl, TERYT/GUS — pełne pochodzenie i licencje w
  [resources/gazetteers/SOURCES.md](resources/gazetteers/SOURCES.md)). To nie
  model uczenia maszynowego, tylko duży, dokładny słownik — imiona są
  samodzielnym sygnałem wysokiej precyzji, nazwiska (bo pokrywają się ze
  zwykłymi rzeczownikami) wymagają dodatkowego sygnału kontekstowego.
- **Wzorce kontekstowe ról prawnych** — reguły wykrywające sekwencję
  tytuł/rola prawna (np. "Pan", "Mec.", "notariusz", "powód", "pozwany",
  "świadek") + następujący ciąg wielkich liter, dopełniające model NER tam,
  gdzie ten nie rozpoznaje nietypowego dla siebie kontekstu pism sądowych.
- **Drugi przebieg literalny** — po znalezieniu konkretnego nazwiska przez
  którąkolwiek z powyższych warstw, generowane są jego polskie formy
  fleksyjne (odmiana przez przypadki) i cały dokument jest przeszukiwany
  dosłownie — łapie wystąpienia pominięte w tabelach, nagłówkach czy
  fragmentach pisanych wersalikami.
- **Detektory regexowe z sumą kontrolną** dla danych o ścisłej strukturze
  (PESEL, NIP, REGON, KRS, IBAN, numer księgi wieczystej, dowód osobisty
  i inne) — to nie modele AI, tylko wysoko precyzyjne wzorce matematyczne,
  ale kluczowe uzupełnienie modeli statystycznych.
- **Rozstrzyganie nakładających się wykryć wg priorytetu, nie szerokości
  spanu.** Gdy dwie warstwy trafiają w ten sam fragment tekstu (np. ogólny
  detektor instytucji łapiący całe "KW nr XXXX/NNNNNNNN/N" jako jedną nazwę,
  mimo że w środku jest ściślejszy, zwalidowany sumą kontrolną numer księgi
  wieczystej), do faktycznej podmiany zawsze wygrywa span o wyższym
  priorytecie (dokładniejszy detektor), niezależnie czy jest szerszy czy
  węższy od konkurenta — zapobiega to niespójnemu etykietowaniu tej samej
  wartości w różnych miejscach dokumentu.

Wszystkie modele i dane działają **lokalnie, offline, bez GPU** — żaden
fragment dokumentu nie jest nigdy wysyłany do zewnętrznego API czy usługi
chmurowej AI.

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

To repozytorium jest obecnie prywatne. Zgłoszenia błędów i propozycje —
przez zakładkę Issues tego repozytorium (dla osób z dostępem).
