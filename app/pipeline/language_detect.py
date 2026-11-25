"""Prosta, zależna wyłącznie od stdlib heurystyka "czy to polski tekst".

Model NER (`pl_core_news_md`) jest trenowany na polskim korpusie - puszczony
na czysto obcojęzycznym tekście da prawie zerowy recall bez żadnej informacji
zwrotnej dla użytkownika (patrz plan, sekcja "Obsługa przypadków brzegowych
plików wejściowych"). To nie jest pełny detektor języka (nie ma tu miejsca na
ciężką zależność w rodzaju `langdetect`/`fasttext` w projekcie, który ma
pozostać lekki i w pełni offline) - to tani sygnał ostrzegawczy, nie blokada.
"""

from __future__ import annotations

import re

# Celowo BEZ krótkich/dwuznacznych słów kolidujących z angielskimi (a, i, o,
# w, z, to, on...) - inaczej niemal każdy dłuższy tekst angielski (zawierający
# powszechne "a"/"to") fałszywie przekroczyłby próg i heurystyka nigdy by nie
# ostrzegła, mimo pozornie sensownego wyniku na krótkich próbkach.
_POLISH_STOPWORDS = frozenset(
    {
        "na", "nie", "że", "się", "jest", "dla", "oraz", "przez",
        "który", "która", "które", "być", "są", "był", "była", "były",
        "ze", "we", "czy", "tak", "ale", "gdy", "aby", "bez", "pod", "nad",
        "jak", "co",
    }
)

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_MIN_WORDS_FOR_DECISION = 30
_POLISH_RATIO_THRESHOLD = 0.03
_DIACRITIC_CHARS = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")


def looks_polish(text: str) -> bool:
    """Zwraca False tylko gdy tekst jest wystarczająco długi ORAZ nie ma w nim
    prawie żadnych polskich znaków diakrytycznych ani powszechnych polskich
    słów funkcyjnych - inaczej (za krótki tekst / dwuznaczny sygnał) zwraca
    True, żeby nie fałszywie alarmować na krótkich/mieszanych dokumentach."""
    words = _WORD_RE.findall(text.lower())
    if len(words) < _MIN_WORDS_FOR_DECISION:
        return True

    if any(ch in _DIACRITIC_CHARS for ch in text):
        return True

    polish_hits = sum(1 for w in words if w in _POLISH_STOPWORDS)
    return (polish_hits / len(words)) >= _POLISH_RATIO_THRESHOLD
