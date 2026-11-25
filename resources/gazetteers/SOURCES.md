# Źródła danych gazetteerów

Wszystkie trzy listy pochodzą z oficjalnych, otwartych rejestrów administracji
publicznej (nie z danych własnych/prywatnych), pobrane i przetworzone
19.07.2026 skryptem jednorazowym (deduplikacja, ujednolicenie wielkości liter,
usunięcie wpisów-śmieci typu `-`/`.`).

## `nazwiska_pl.txt`

Źródło: **"Nazwiska osób żyjących występujące w rejestrze PESEL"**, Ministerstwo
Spraw Wewnętrznych i Administracji, https://dane.gov.pl/pl/dataset/1681 —
zbiory "Nazwiska męskie" i "Nazwiska żeńskie" (stan na 2025-01-22), licencja
**CC0 1.0** (domena publiczna).

Zastosowany próg: tylko nazwiska występujące u co najmniej **5 osób** w
rejestrze (odcina długi ogon literówek/pojedynczych błędnych wpisów, zachowuje
286 267 unikalnych nazwisk).

## `imiona_pl.txt`

Źródło: **"Lista imion występujących w rejestrze PESEL"** (pole "imię
pierwsze"), MSWiA, https://dane.gov.pl/pl/dataset/1667 — zbiory imion męskich
i żeńskich (stan na 2020-01-21), licencja **CC0 1.0** (domena publiczna).
Bez progu odcięcia — 36 327 unikalnych imion.

## `cities_pl.txt`

Źródło: rejestr **TERYT SIMC** (System Identyfikacji Miejscowości i Ulic),
Główny Urząd Statystyczny — dane sektora publicznego podlegające ustawie o
ponownym wykorzystywaniu informacji sektora publicznego (wymagana atrybucja
źródła przy dalszym rozpowszechnianiu, co niniejszym czynimy). Lista pobrana
z przetworzonego mirrora: https://gist.github.com/bbasinski/eba5d67ac52defdf1aeed4e11e64ee0f
58 043 unikalnych nazw miejscowości (po deduplikacji).

## Uwaga o ponownym wykorzystaniu

Osoba pobierająca to repozytorium i chcąca zaktualizować którąkolwiek z list
(np. nowszym rocznikiem) może odtworzyć powyższy proces z aktualnych zasobów
dane.gov.pl — API `https://api.dane.gov.pl/1.4/datasets/{id}/resources` zwraca
bezpośrednie linki do plików CSV/XLSX dla podanych wyżej identyfikatorów
datasetów (1681, 1667).
