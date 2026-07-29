# Anonimizator Pism

Lokalna, w pełni offline aplikacja Windows do anonimizacji dokumentów prawniczych
(PDF, DOCX, DOC, ODT, TXT, skany). Pełny opis architektury: patrz plan projektu.

## Rozwój (Linux, ten katalog)

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download pl_core_news_lg
pytest
```

Finalny `.exe`/instalator Windows powstaje wyłącznie przez GitHub Actions
(`.github/workflows/build-windows.yml`) — PyInstaller nie kompiluje krzyżowo z Linuksa.
