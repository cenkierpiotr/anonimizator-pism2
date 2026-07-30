# Golden dataset - raport recall/precision

Wygenerowano 30 syntetycznych dokumentów (seed=42), typy: akt_notarialny, pozew, wezwanie_do_zaplaty, wyrok.

## Recall per kategoria

| Kategoria | Ground truth | Wykryte | Recall |
|---|---:|---:|---:|
| address | 60 | 60 | 100.0% |
| case_number | 15 | 15 | 100.0% |
| email | 37 | 37 | 100.0% |
| iban | 23 | 23 | 100.0% |
| legal_role_person | 37 | 37 | 100.0% |
| nip | 23 | 23 | 100.0% |
| pesel | 37 | 37 | 100.0% |
| phone | 37 | 37 | 100.0% |

**Recall ogółem: 100.0%** (269/269 zaplanowanych encji wykrytych).

## Precyzja (zbiorcza, nie per kategoria)

Wszystkich detekcji w całym zbiorze: 398. Z tego pokrywających się z jakąś zaplanowaną encją: 269 -> **precyzja zbiorcza: 67.6%**.

Uwaga: część detekcji spoza ground truth to NIE fałszywe alarmy w sensie użytkowym, tylko poprawne działanie warstw, których nie modelujemy w tym generatorze (np. `institution` na nazwie sądu/spółki w nagłówku, `date`/`amount` we frazach szablonu, dodatkowe wystąpienia nazwiska w drugim przebiegu literalnym). Realna precyzja "czy to naprawdę PII" jest więc prawdopodobnie WYŻSZA niż liczba powyżej sugeruje - to ograniczenie metodologii, nie pipeline'u.
