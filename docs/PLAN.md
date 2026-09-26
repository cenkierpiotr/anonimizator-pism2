# Anonimizator Dokumentów — plan projektu i uzasadnienia architektoniczne

*(Projekt powstawał pod roboczą nazwą "Anonimizator Pism" — poniższy plan
używa jeszcze tej nazwy w niektórych miejscach jako historyczny zapis decyzji;
produkt finalnie nazywa się "Anonimizator Dokumentów", zakres funkcjonalny
się nie zmienił.)

## Kontekst

Prawnik potrzebuje aplikacji na Windows (ikonka na pulpicie, jeden instalator, zero wiedzy technicznej wymaganej) która przyjmuje dowolny dokument (PDF z tekstem, PDF skan, DOCX, DOC, ODT, TXT, obraz skanu) i zwraca .docx z zanonimizowanymi danymi wrażliwymi, zachowując przy tym czytelność i kontekst prawny (np. "545433987" → "[numer telefonu]"). Wymóg krytyczny: **100% lokalnie, offline, bez GPU, bez preinstalowanych zależności** (żadnego Pythona, Ollamy itp. u użytkownika końcowego) — bo dokumenty prawnicze bywają poufne. Anonimizacja ma być **nieodwracalna** (żaden klucz mapujący nie jest nigdzie zapisywany), ale w ramach jednego dokumentu różne osoby dostają numerowane etykiety ("[Osoba 1]", "[Osoba 2]") żeby nie tracić informacji "kto jest kim" w danym piśmie — etykieta żyje tylko w pamięci procesu, nigdy nie trafia na dysk.

Ważne ograniczenie środowiska deweloperskiego: aplikacja była pisana na Linuksie, ale docelowy build to Windows .exe. PyInstaller nie kompiluje krzyżowo — cały kod Python/logikę pisze się i testuje na Linuksie (Tesseract, spaCy, python-docx działają identycznie na Linuksie), ale finalny `.exe`/instalator musi powstać na Windows — przez GitHub Actions z hostowanym runnerem `windows-latest`.

## Decyzje projektowe

- Przetwarzanie w pełni lokalne/offline, ma działać na typowym PC bez dedykowanej karty graficznej.
- Anonimizacja nieodwracalna — bez zapisywanego klucza.
- **Wszystkie kategorie** (nie tylko osoby) dostają numerowane etykiety w ramach jednego dokumentu, np. `[numer telefonu 1]`, `[numer telefonu 2]`, `[Osoba 1]`, `[adres 1]`, `[data 1]` — ta sama zanonimizowana wartość w różnych miejscach dokumentu dostaje ten sam numer, różne wartości w tej samej kategorii dostają różne numery. Zachowuje pełny kontekst (widać że to ciągle ten sam telefon/osoba/adres), wciąż w pełni nieodwracalne — numeracja żyje tylko w pamięci procesu na czas przetwarzania jednego pliku, nigdy nie jest zapisywana na dysk.
- **Żaden model NER nie daje 100% skuteczności** — dlatego oprócz spaCy dodajemy wzorce kontekstowe wyzwalane tytułami prawniczymi oraz **obowiązkowy ekran podglądu przed zapisem pliku**, żeby użytkownik mógł zweryfikować/dopisać ręcznie wykryte dane (patrz sekcja "Jakość detekcji i warstwa bezpieczeństwa" niżej).
- Zachowanie układu/formatowania oryginału w wyjściowym .docx.
- Dystrybucja: jeden plik instalacyjny .exe ze skrótem na pulpicie.
- **.doc nie wchodzi do głównego instalatora** — LibreOffice (potrzebny do konwersji .doc→.docx) jest pobierany na żądanie: albo przyciskiem w interfejsie, albo automatycznie wyzwalany gdy użytkownik wrzuci plik .doc (z potwierdzeniem "potrzebny dodatkowy komponent ~300MB, pobrać teraz?"). Dzięki temu bazowy instalator zostaje mały, a .doc działa przy pierwszym użyciu po jednorazowym pobraniu i cache'owaniu w folderze aplikacji (`%LOCALAPPDATA%\AnonimizatorPism\libreoffice\`).

## Kategorie danych do anonimizacji

**Podstawowe (zawsze numerowane, ta sama wartość = ten sam numer):**
- numery telefonów (w tym formaty zagraniczne: `+49`, `+44`, `0048`, oraz różne separatory `601-234-567`, `(22) 123 45 67`)
- adresy (ulica + numer, kod pocztowy, miejscowość — w tym adresy bez formalnego prefiksu ulicy, np. "Marszałkowska 10/12")
- adresy e-mail
- nazwy i adresy sądów oraz innych instytucji/organów (prokuratura, urzędy, KRS)
- PESEL, NIP, REGON, KRS
- numer księgi wieczystej (format `XXXX/NNNNNNNN/N`, z checksumem wag 1,3,7) — kluczowe w aktach notarialnych/sprawach o nieruchomości
- numer działki ewidencyjnej + obręb, identyfikator TERYT działki
- IBAN / numer rachunku bankowego (PL: `PL` + 26 cyfr, checksum mod 97) — częste w pozwach o zapłatę, sprawach frankowych
- numery faktur i umów (w tym kredytowych, np. `nr 123/2008/CHF`)
- numery polis ubezpieczeniowych i numery szkód
- dowód osobisty (z checksumem), paszport, karta pobytu, prawo jazdy
- VIN pojazdu i numer rejestracyjny — sprawy komunikacyjne/ubezpieczeniowe
- NPWZ (numer prawa wykonywania zawodu lekarza) — sprawy o błąd medyczny
- sygnatury akt — rozbite na podtypy wzorców (nie jedna wspólna kategoria): cywilne/gospodarcze (`I C`, `Nc`, `GC`, `Ns`), karne (`II K`, `Ko`, `Kp`), prokuratorskie (`PR 1 Ds. 123.2026`), policyjne (`RSD-123/26`), administracyjne (`II SA/Wa`, `I OSK`), SN/KIO, komornicze (`Km`, `Kmp`, `GKm`)
- numer aktu notarialnego (np. "Rep. A Nr 1234/2026")
- numer aktu stanu cywilnego USC, numer aktu poświadczenia dziedziczenia, wpis w Rejestrze Spadkowym
- dane cyfrowe: adres IP (v4/v6), IMEI, URL-e, nazwy użytkownika/profile social media (istotne w sprawach o dobra osobiste/naruszenia)
- imiona i nazwiska (klastrowane i numerowane per dokument: `[Osoba 1]`, `[Osoba 2]`...)
- dane notariusza (imię, nazwisko, nazwa i adres kancelarii) → `[notariusz N]` / `[kancelaria notarialna N]`
- dane pełnomocników/adwokatów/radców prawnych, w tym numer wpisu na listę (`WAW/Adw/1234`, `KR-1234`) → `[pełnomocnik N]`

**Kategorie z osobną, nie-numerowaną (lub inaczej numerowaną) polityką:**
- daty → domyślnie **zostawione** (terminy są sednem pisma), z wyjątkiem dat urodzenia/zgonu wykrywanych kontekstowo → `[data urodzenia N]`; opcjonalny tryb *date shifting*
- kwoty pieniężne → domyślnie `[kwota]` **bez numeru** (albo zostawione — rzadko identyfikują, a są kluczowe dla sensu pisma)

**Uwaga o kolizji nazwa-firmy/nazwisko:** jeśli nazwa firmy zawiera nazwisko (np. "Jan Kowalski Usługi Bud-Mont"), oba span-y są anonimizowane osobno (etykieta zagnieżdżona), a nie tylko jako ORG — inaczej osoba wyciekłaby przez nazwę jednoosobowej działalności.

## Architektura pipeline'u

```
Plik wejściowy
   │
[1] Wykrycie formatu (rozszerzenie + sniff nagłówka; wykrycie hasła/szyfrowania → czytelny komunikat zamiast wyjątku)
   ├─ .docx ────────► otwarcie jako ZIP+XML (lxml, nie tylko python-docx — patrz "Podmiana tekstu" niżej)
   ├─ .doc  ────────► sprawdź czy LibreOffice pobrany; jeśli nie: prompt "pobierz komponent (~300MB)"
   │                  → soffice --headless --convert-to docx → wraca do gałęzi .docx
   ├─ .odt  ────────► odfpy (lekki, pure-Python; fallback: soffice jeśli nietypowa struktura)
   ├─ .txt  ────────► zwykły tekst → syntetyczne akapity
   ├─ .pdf  ────────► pypdfium2 per-strona: heurystyka "czy to realny tekst czy śmieci" (gęstość znaków,
   │                     udział polskich słów, pokrycie strony obrazem, obecność pól AcroForm/adnotacji)
   │                     wynik wysoki → tekst z layoutem; wynik niski/śmieciowy → OCR mimo obecnej warstwy
   │                  → get_pixmap(dpi=300) → OCR (pytesseract, lang="pol+eng", z detekcją języka)
   └─ .jpg/.png/.tiff ► PIL.Image → OCR (pytesseract, lang="pol+eng")
   │
   Obrazy osadzone WEWNĄTRZ .docx/.pdf-z-tekstem (skany pełnomocnictw, pieczątki, wklejone KW) też
   przechodzą przez OCR — inaczej dane w nich przechodzą nietknięte mimo komunikatu "zanonimizowano".
   │
[2] Wewnętrzny model dokumentu: lista bloków (akapit/nagłówek/komórka tabeli/nagłówek-stopka/przypis/
    komentarz) z runami i formatowaniem
   │
[3] Detekcja encji na złączonym tekście każdego bloku:
     a. Detektory regex+checksum (PESEL, NIP, REGON, KRS, KW, IBAN, dowód/paszport, VIN, telefon, email,
        sygnatury wg podtypów, akty notarialne/USC) — najwyższy priorytet, z tolerancją typowych pomyłek
        OCR (O/0, l/1/I, S/5, B/8, Z/2) oznaczaną jako "niepewne" w ekranie weryfikacji
     b. Gazetteer instytucji/sądów + adresy (prefiks ulicy + kod pocztowy + NER-LOC + gazetteer miejscowości)
        + gazetteer imion (wysoka precyzja, samodzielny sygnał) i nazwisk z rejestru PESEL/dane.gov.pl
        (NIE samodzielny sygnał — nazwiska pokrywają się ze słownikiem pospolitym, wymaga drugiego sygnału:
        wielka litera nie na początku zdania + sąsiedztwo imienia/tytułu/roli)
     c. Wzorce kontekstowe wg roli prawnej (`legal_roles.py`) — tytuł/rola + sekwencja wielkich liter
     d. spaCy NER — PERSON/ORG/LOC kandydaci
     e. Drugi przebieg literalny: gdy warstwy a-d znajdą konkretne nazwisko, wygeneruj jego formy
        fleksyjne (reguły końcówek: -ski/-skiego/-skiej/-cki/-icz/-a/-y/-ę + lista nazwisk nieodmiennych)
        i przeszukaj cały dokument dosłownie — łapie wystąpienia pominięte przez NER w tabelach/nagłówkach/
        sentencjach pisanych wersalikami. Tania warstwa, prawdopodobnie największy pojedynczy wzrost recall.
     Rozstrzyganie nakładających się span-ów: interval resolution — sortowanie po (priorytet, długość),
     greedy, z jawną obsługą ZAGNIEŻDŻENIA inaczej niż częściowego nakładania
   │
[4] Etykietowanie — kanonikalizacja WARTOŚCI przed przydzieleniem numeru (żeby "+48 601 234 567" i
    "601-234-567" dostały ten sam numer, a nie dwa różne):
     - kategorie identyfikujące obiekt: numerowane, ta sama kanoniczna wartość = ten sam numer w pamięci
       procesu na czas przetwarzania pliku
     - PERSON → klastrowanie tożsamości po parze (imię, nazwisko), NIE po samym nazwisku; niejednoznaczne
       przypadki trafiają do ekranu weryfikacji jako decyzja użytkownika
     - daty i kwoty: osobna, NIE-numerowana domyślnie polityka
     - idempotencja: jeśli dokument już zawiera literalne "[Osoba 1]", wykryć i nie mylić z nową etykietą
   │
[5] Zapis wyjścia:
     - PRZED zapisem: re-scan całego wygenerowanego dokumentu regexami z checksumem (leak test) —
       blokada zapisu jeśli jakikolwiek zwalidowany identyfikator przetrwał
     - czyszczenie metadanych: docProps/core.xml, docProps/app.xml, metadane PDF, nazwa pliku wyjściowego
     - źródło docx/doc/odt: podmiana tekstu z zachowaniem formatowania (patrz "Podmiana tekstu" niżej)
     - źródło PDF/OCR/obraz: odtworzony .docx (best-effort układ, oznaczone w UI jako przybliżone)
   │
Wyjście: <nazwa neutralna>_zanonimizowany.docx
```

### Kluczowy szczegół: podmiana tekstu — lxml po całym pakiecie .docx, nie tylko API python-docx

`python-docx`'owe `paragraph.runs` pomija większość miejsc, gdzie realnie bywa tekst w dokumencie prawniczym: `w:hyperlink` (URL/mailto siedzi w `.rels`, nie w tekście widocznym), pola `w:instrText`/`w:fldSimple` (MERGEFIELD, HYPERLINK), `w:txbxContent` (pola tekstowe/kształty), przypisy (`footnotes.xml`/`endnotes.xml`), komentarze (`comments.xml`), nagłówki/stopki każdej sekcji osobno, oraz `w:delText` — tekst usunięty przy włączonym śledzeniu zmian, fizycznie wciąż obecny w pliku i widoczny po włączeniu recenzji w Wordzie. Dla dokumentu prawniczego to ostatnie jest najgroźniejsze: pozornie "zanonimizowany" plik może zawierać w sobie nieusunięte dane w historii zmian.

**Decyzja projektowa:** `docx_writer.py` operuje na lxml bezpośrednio na wszystkich częściach pakietu (`document.xml`, `header*.xml`, `footer*.xml`, `footnotes.xml`, `endnotes.xml`, `comments.xml`), iterując po wszystkich węzłach `w:t`/`w:delText`/`w:instrText`, a nie tylko po `paragraph.runs`. Osobno czyszczone: `.rels` (adresy w hyperlinkach), `docProps/*` (metadane). Przed przetworzeniem dokumentu z aktywnym śledzeniem zmian: jawne pytanie do użytkownika czy zaakceptować czy odrzucić zmiany.

W ramach każdej pojedynczej części XML: jeden akapit bywa podzielony na wiele `w:r`/`w:t` o różnym formatowaniu, więc detekcja działa na złączonym tekście z mapą offsetów do poszczególnych węzłów tekstowych, a podmiana rozbija span na wiele węzłów. To najbardziej newralgiczny kawałek kodu w całym projekcie, z testem "rozpakuj i przeszukaj cały XML pakietu" jako najważniejszym testem całej suity.

## Jakość detekcji i warstwa bezpieczeństwa

Szczera odpowiedź: **nie ma modelu NER (nawet znacznie droższego, transformerowego), który da 100% skuteczności** na dowolnym tekście prawniczym — szczególnie na nietypowo odmienionych nazwiskach, rzadkich nazwiskach obcego pochodzenia, czy nazwiskach w gęstym, sformalizowanym kontekście. spaCy `pl_core_news_md` jest solidnym wyborem (dobry balans jakość/szybkość/rozmiar na CPU), ale traktowany jako jedna z kilku warstw, nie jedyne źródło prawdy:

1. **spaCy NER** — kandydaci PERSON/ORG/LOC.
2. **Wzorce kontekstowe wyzwalane rolą prawną** — detektor `detectors/legal_roles.py` szukający sekwencji: tytuł/rola (`Pan|Pani|Mec\.|notariusz|adwokat|radca prawny|pełnomocnik|powód|pozwany|świadek|wnioskodawca|uczestnik`) + następująca sekwencja wielkich liter.
3. **Gazetteer imion i nazwisk** (dane.gov.pl / rejestr PESEL, otwarte, CC0) — imiona: samodzielny sygnał wysokiej precyzji. Nazwiska: NIE samodzielny sygnał (mnóstwo nazwisk to zwykłe rzeczowniki pospolite), liczy się dopiero z drugim sygnałem.
4. **Drugi przebieg literalny** — po znalezieniu konkretnego nazwiska pierwszą warstwą, wygeneruj jego formy fleksyjne i przeszukaj cały dokument dosłownie.
5. **Tryb dokładny (opcjonalny, wolniejszy)** — do rozważenia: skwantyzowany int8 model HerBERT NER uruchamiany przez ONNX Runtime jako dodatkowy przebieg podnoszący recall kosztem czasu, decyzja na podstawie metryk ze złotego zbioru, nie z góry.
6. **Klasa "podejrzane, nieoznaczone" w ekranie weryfikacji** — każdy token z wielkiej litery (nie na początku zdania), który nie jest znanym rzeczownikiem pospolitym i nie został złapany przez żadną warstwę, trafia na osobną listę "potencjalnie pominięte, sprawdź".
7. **Obowiązkowy ekran podglądu przed zapisem** — po przetworzeniu dokumentu aplikacja pokazuje listę wszystkich wykrytych i podmienionych fragmentów pogrupowaną wg kategorii (plus listę "potencjalnie pominięte"), z podglądem dokumentu z podświetleniami. Użytkownik może odznaczyć błędnie wykryty fragment, ręcznie dodać pominięty, dopiero potem zatwierdzić i zapisać finalny .docx.
8. **Ostrzeżenie przy niskiej jakości OCR** — `image_to_data` daje confidence per słowo; przy niskiej średniej, twarde ostrzeżenie w UI + detektory regex/checksum pracują w trybie tolerancyjnym na typowe pomyłki OCR, oznaczając trafienia jako "niepewne".

### Adresy — jak podnosimy skuteczność

Bazowa hybryda (prefiks ulicy `ul./al./pl./os.` + kod pocztowy `NN-NNN` jako wysoko-precyzyjna kotwica + NER `LOC/GPE`) jest wzmocniona o:
- **Gazetteer nazw miejscowości** (`resources/gazetteers/cities_pl.txt`, dane z rejestru TERYT/GUS) jako sygnał niezależny od NER.
- **Frazy-kotwice** (`zamieszkał[ya]? w`, `z siedzibą w`, `adres(:|zamieszkania|do korespondencji)`) — gdy taka fraza występuje, kolejny fragment tekstu jest traktowany jako kandydat na adres z podwyższonym priorytetem, nawet bez formalnego prefiksu ulicy.
- Scalanie: kod pocztowy > gazetteer miejscowości + fraza-kotwica > sam NER LOC bez żadnej kotwicy.
- Dodatkowe kotwice specyficzne dla aktów notarialnych: `legitymujący się`, `działający w imieniu`, sąsiedztwo `PESEL`.

## Daty i kwoty: dlaczego nie numerujemy ich tak samo jak resztę

Numerowanie ma sens tam, gdzie **identyczność wartości oznacza identyczność obiektu** (osoba, adres, telefon, PESEL, IBAN, sygnatura). Dla dat i kwot to założenie jest fałszywe: dwie różne kwoty po 5000 zł (czynsz i osobna kara umowna) albo data pisma i data urodzenia przypadające tego samego dnia dostałyby ten sam numer, sugerując czytelnikowi nieistniejący związek między faktami.

Do tego dochodzi drugi problem: **terminy są sednem sprawy** (czy dochowano 14 dni, czy roszczenie się przedawniło, kolejność zdarzeń) — masowe usuwanie wszystkich dat niszczy merytoryczną użyteczność pisma.

**Domyślna polityka (konfigurowalna per kategoria w `config.py`, tryby: `usuń i numeruj` / `usuń bez numeru` / `zostaw`):**
- **daty** → domyślnie **zostaw**, z wyjątkiem dat urodzenia/zgonu wykrytych kontekstowo → `[data urodzenia N]`. Opcjonalny tryb **date shifting**: przesunięcie wszystkich dat w dokumencie o ten sam losowy offset — zachowuje odstępy między zdarzeniami, nieodwracalne bez znajomości offsetu, standard w de-identyfikacji medycznej.
- **kwoty** → domyślnie `[kwota]` **bez numeru** (albo zostaw).
- Świadomie zaakceptowany efekt uboczny: liczba etykiet ujawnia ile jest osób/adresów w sprawie; usunięcie PESEL przy pozostawieniu daty urodzenia i płci daje razem quasi-identyfikator — te dwie kategorie muszą być konfigurowane spójnie.

## Stack technologiczny

| Warstwa | Wybór | Uzasadnienie |
|---|---|---|
| GUI | CustomTkinter (Tkinter) | Zero dodatkowych zależności runtime, lekkie, sprawdzone w PyInstallerze |
| OCR | Tesseract 5.x + `pol.traineddata` | Jedyny dojrzały, w pełni offline silnik OCR bez GPU z polskim modelem, mały footprint |
| PDF | `pypdfium2` (Apache/BSD) zamiast PyMuPDF | PyMuPDF/MuPDF jest na licencji AGPL v3 (lub płatnej komercyjnej) — dystrybucja `.exe` bez udostępnienia źródeł całej aplikacji naruszałaby AGPL. `pypdfium2` (oparty o bibliotekę PDFium z Chromium) daje tę samą funkcjonalność bez tego ryzyka |
| .doc/.odt | LibreOffice headless (`soffice --convert-to docx`), pobierany na żądanie; .odt woli `odfpy` gdy się da | Jedyny niezawodny sposób konwersji starego .doc z zachowaniem formatowania |
| NER | spaCy `pl_core_news_md` | Lekki (bez torch), szybki na CPU |
| Regex/checksumy | własne moduły: PESEL, NIP, REGON, KRS, KW, IBAN, dowód/paszport, VIN, telefon, email, daty, kwoty, sygnatury akt (wg podtypów), akty notarialne/USC | Wysoka precyzja dla ustrukturyzowanych identyfikatorów |
| Adresy | hybryda: prefiks ulicy + kod pocztowy + NER-LOC + gazetteer miejscowości (TERYT) + frazy-kotwice | spaCy PL nie ma natywnej encji adresu |

Licencja modelu `pl_core_news_md` (bazuje na korpusie NKJP, bywa CC BY-SA — wymaga co najmniej atrybucji przy redystrybucji) — patrz `resources/gazetteers/SOURCES.md` i sekcja "Zależności i licencje" w README.

## Pobieranie LibreOffice na żądanie (mechanizm .doc)

- `legacy_convert.py` sprawdza czy `%LOCALAPPDATA%\AnonimizatorPism\libreoffice\soffice.exe` istnieje.
- Jeśli nie: w GUI pojawia się okno "Do obsługi starych plików .doc potrzebny jest dodatkowy komponent (ok. 300MB). Pobrać teraz?" — zarówno wywoływane automatycznie przy wrzuceniu pliku .doc, jak i dostępne jako przycisk "Zainstaluj obsługę .doc" w ustawieniach aplikacji.
- Po zgodzie: pobranie z własnego GitHub Releases projektu, zweryfikowane checksumem, rozpakowanie do folderu cache, potem konwersja działa lokalnie tak samo jak reszta pipeline'u.
- Instalator bazowy nie zawiera LibreOffice wcale — obsługuje od razu docx/pdf/odt/txt/obrazy.
- **Zastrzeżenie**: aplikacja reklamowana jako "100% offline" wykonuje w tym jednym miejscu połączenie sieciowe — trzeba to powiedzieć wprost użytkownikowi, plus dać ścieżkę w pełni offline: możliwość wskazania już zainstalowanego LibreOffice na dysku, albo instalacja z pliku pobranego ręcznie na innym komputerze.

## Higiena plików tymczasowych i logów

Deklaracja "nieodwracalne, nic nie trafia na dysk" jest łamana, jeśli nie zaadresować tego świadomie:
- `soffice --headless --convert-to docx` zapisuje **nieanonimizowany** plik pośredni do katalogu tymczasowego i tworzy profil użytkownika LibreOffice z historią dokumentów.
- Rasteryzacja PDF do OCR i przekazywanie obrazu do `pytesseract` może przechodzić przez pliki tymczasowe.
- Traceback zawierający fragment treści dokumentu w logu błędów = wyciek.

Zasady wdrożone: dedykowany katalog temp per-uruchomienie, czyszczony w `finally` i przy starcie po ewentualnym crashu z poprzedniej sesji; profil LibreOffice w kontrolowanym, czyszczonym katalogu; twarda zasada w całym kodzie "nigdy nie loguj zawartości dokumentu, tylko offsety/nazwy kategorii/liczby trafień"; wyłączone crash-dumpy z zawartością pamięci.

## Obsługa przypadków brzegowych plików wejściowych

- **PDF z hasłem**: wykrywane (`needs_pass`), aplikacja prosi o hasło zamiast wywalić się niejasnym błędem.
- **DOCX zaszyfrowany hasłem** (kontener OLE, nie ZIP): wykrywana sygnatura pliku, czytelny komunikat zamiast surowego wyjątku.
- **DOCX z ochroną edycji** (`w:documentProtection`): odczyt działa, zapis wyniku świadomie usuwa tę ochronę.
- **Dokumenty obcojęzyczne**: `eng.traineddata` jest bundlowany i realnie używany (`lang="pol+eng"` domyślnie w OCR). Prosta detekcja języka tekstu przed NER — przy wykryciu obcego języka aplikacja pokazuje jawne ostrzeżenie "dokument obcojęzyczny, detekcja osób może być ograniczona".

## Wydajność i responsywność GUI

Realistyczny budżet: OCR przy 300 DPI to ok. 2-5 s/strona na CPU, więc 200-stronicowy skan to 10-20 minut przetwarzania. Konsekwencje:
- Pipeline działa w osobnym wątku — GUI zamrożone w wątku głównym pokazałoby się użytkownikowi jako "nie odpowiada".
- Pasek postępu per strona/blok i przycisk anulowania.
- Adaptacyjny dobór DPI/`--psm` zamiast sztywnej wartości, plus podstawowy preprocessing OCR (deskew, binaryzacja, redukcja szumu).

## Pakowanie: one-dir + podpis kodu

- **PyInstaller one-dir, nie one-file** — przy tym rozmiarze bundla (Tesseract, model spaCy, opcjonalnie LibreOffice) one-file rozpakowywałby się do katalogu tymczasowego przy KAŻDYM starcie. Inno Setup instaluje cały katalog one-dir i tworzy skrót.
- **Brak podpisu kodu = niemal pewny SmartScreen "Windows chronił Twój komputer" i wysokie ryzyko fałszywego alarmu antywirusa** (PyInstaller jest notorycznie flagowany). Do zaplanowania: certyfikat podpisywania kodu (OV/EV) po pierwszym wydaniu — do czasu jego zdobycia, gotowa instrukcja dla użytkownika "co zrobić gdy Windows/antywirus ostrzega".
- GitHub Actions: cache modelu spaCy i binariów Tesseract między buildami.

## Weryfikacja

- **Detektory**: testy jednostkowe z fixture'ami zawierającymi znane wartości PESEL/NIP/KW/IBAN/telefon/daty/kwoty/sygnatur wg podtypów.
- **`docx_writer.py`**: testy sprawdzające że formatowanie (bold/italic/rozmiar) nietkniętych fragmentów przetrwa podmianę, że span rozbity na wiele węzłów tekstowych zamienia się w jedną poprawną etykietę, oraz że nagłówki/stopki/przypisy/komentarze/`w:delText`/hyperlinki (`.rels`) są objęte.
- **Test "leak" (najważniejszy pojedynczy test w całej suicie)**: po zapisie rozpakować wynikowy .docx i przeszukać CAŁY XML wszystkich części pakietu (nie tylko `document.xml`) za każdą wartością testową z fixture'a. Ten sam test uruchamiany automatycznie jako `leak_check.py` przed każdym realnym zapisem w aplikacji.
- **Złoty zbiór z metrykami recall/precision per kategoria**: generator syntetycznych pism (szablony pozwu, aktu notarialnego, wyroku, wezwania do zapłaty) wypełniany losowymi danymi z gazetteerów — patrz `scripts/golden_dataset.py` i `scripts/golden_report.md`. Dodatkowo: możliwość rozszerzenia o ręcznie zaadnotowane realne pisma trzymane poza repo (nigdy w git), jeśli takie kiedyś będą dostępne.
- Pipeline end-to-end: przepuszczenie przykładowego pisma sądowego (docx i skan PDF) przez cały proces i ręczna weryfikacja że wszystkie kategorie danych zostały zamienione, a tekst pozostał czytelny.
- Finalny .exe: pobranie artefaktu z GitHub Actions i uruchomienie na realnym/VM Windows bez Pythona zainstalowanego — sprawdzenie że OCR, NER i (opcjonalnie) pobieranie LibreOffice działają "z pudełka", oraz sprawdzenie zachowania SmartScreen/antywirusa przy braku podpisu kodu.
