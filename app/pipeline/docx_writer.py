"""Podmiana tekstu w pakiecie .docx na poziomie lxml, obejmująca CAŁY pakiet.

python-docx'owe `paragraph.runs` pomija hyperlinki (.rels), pola (w:instrText),
przypisy/komentarze, nagłówki/stopki każdej sekcji osobno oraz w:delText (tekst
usunięty przy śledzeniu zmian, wciąż fizycznie obecny w pliku). Ten moduł operuje
bezpośrednio na XML wszystkich części pakietu, żeby żadne z tych miejsc nie
zostało pominięte przy anonimizacji.

Zakres skanowania (części pakietu, węzły tekstowe, wartości atrybutów) musi
pozostać identyczny z `leak_check.py` — inaczej walidacja "widzi" więcej niż
ten moduł potrafi realnie podmienić, co prowadzi do sytuacji "wykryto, ale nie
zanonimizowano" (blokada zapisu bez możliwości naprawy). Dlatego skanujemy
KAŻDĄ część `.xml`/`.rels` pakietu (nie tylko document/header/footer/...),
KAŻDY tekst elementu (`.text` i `.tail`, nie tylko `w:t`/`w:delText`/
`w:instrText`) oraz KAŻDĄ wartość atrybutu (np. `w:docVar` w settings.xml,
`Target` w .rels, opisy alt-text) — dane wrażliwe w dokumentach prawniczych
(zwłaszcza szablonach z polami scalania) potrafią siedzieć w każdym z tych
miejsc.
"""

from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": W_NS}

# Lokalne nazwy atrybutów spec-owo gwarantowane jako czysto techniczne
# (identyfikatory sesji edycji/rewizji, referencje relacyjne) — nigdy nie
# niosą treści dokumentu, więc pomijamy je przy skanowaniu atrybutów jako
# optymalizację wydajności (nie jako założenie o bezpieczeństwie: wszystko
# poza tą krótką listą i tak przechodzi przez pełną detekcję).
_TECHNICAL_ATTR_LOCALNAMES = frozenset(
    {
        "rsid", "rsidR", "rsidRDefault", "rsidRPr", "rsidP", "rsidTr", "rsidSect", "rsidRoot",
        "id", "embed", "link",
    }
)

# Części pakietu, w których tekst bywa fizycznie rozbity na wiele sąsiednich
# węzłów (np. jeden PESEL na dwa `w:r`/`w:t` o różnym formatowaniu) — tu
# złączenie MUSI iść bez separatora, inaczej detekcja przeoczy rozbitą wartość
# (patrz test_split_run_replacement). Każda inna część (docProps/metadane,
# customXml, settings/styles/numbering/theme/fontTable/webSettings, .rels) ma
# osobne, samodzielne wartości w oddzielnych elementach - złączenie ich bez
# separatora tworzy fałszywe dopasowania na granicy dwóch niepowiązanych
# wartości (np. rewizja "1" + data ISO doklejona wprost do kolejnej daty ISO
# złożyły się w ciąg cyfr wyglądający jak numer telefonu - realny błąd
# znaleziony testem e2e). Dlatego te części łączymy z separatorem.
_FLOW_CONTENT_PART_PREFIXES = (
    "word/document.xml",
    "word/header",
    "word/footer",
    "word/footnotes.xml",
    "word/endnotes.xml",
    "word/comments.xml",
)


def _is_flow_content_part(part_name: str) -> bool:
    return any(part_name.startswith(prefix) for prefix in _FLOW_CONTENT_PART_PREFIXES)


@dataclass
class TextNode:
    """Węzeł tekstowy XML wraz z jego pozycją w złączonym tekście części."""

    element: etree._Element
    start: int
    end: int  # koniec wyłączny
    attr: str = "text"  # "text" albo "tail"


@dataclass
class PartText:
    """Złączony tekst jednej części XML pakietu, z mapą offsetów do węzłów."""

    part_name: str
    tree: etree._ElementTree
    text: str
    nodes: list[TextNode]


def _iter_text_locations(elem: etree._Element) -> Iterable[tuple[etree._Element, str]]:
    """Odtwarza kolejność `lxml`-owego `itertext()` (self.text, potem dla
    każdego dziecka: cała jego poddrzewna treść, potem child.tail), ale zamiast
    samego tekstu zwraca (element, "text"|"tail") — żeby offsety zbudowane tu
    dokładnie odpowiadały temu, co widzi `leak_check._all_text_parts` przez
    `root.itertext()`."""
    if elem.text:
        yield (elem, "text")
    for child in elem:
        yield from _iter_text_locations(child)
        if child.tail:
            yield (child, "tail")


def load_part_text(part_name: str, xml_bytes: bytes) -> PartText:
    """Parsuje jedną część XML i buduje złączony tekst z mapą offsetów.

    W częściach "przepływowych" (patrz `_FLOW_CONTENT_PART_PREFIXES`) fragmenty
    są łączone bez separatora, żeby wartość rozbita na sąsiednie węzły (różne
    formatowanie w jednym akapicie) dalej tworzyła jeden ciągły tekst do
    detekcji. W pozostałych częściach (metadane, style, .rels...) wstawiamy
    separator między fragmentami, żeby dwie niepowiązane wartości nigdy się
    przypadkowo nie skleiły w fałszywe dopasowanie."""
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.fromstring(xml_bytes, parser=parser).getroottree()
    root = tree.getroot()
    flow = _is_flow_content_part(part_name)
    separator = "" if flow else "\n"

    nodes: list[TextNode] = []
    pieces: list[str] = []
    offset = 0
    for elem, attr in _iter_text_locations(root):
        content = getattr(elem, attr) or ""
        if content == "":
            continue
        if pieces:
            offset += len(separator)
        nodes.append(TextNode(element=elem, start=offset, end=offset + len(content), attr=attr))
        pieces.append(content)
        offset += len(content)

    return PartText(part_name=part_name, tree=tree, text=separator.join(pieces), nodes=nodes)


def apply_replacements(part: PartText, spans: list[tuple[int, int, str]]) -> bool:
    """Nakłada podmiany (start, end, etykieta) na węzły tekstowe danej części.

    `spans` odnosi się do offsetów w `part.text` (jak zwrócone przez detektory).
    Zwraca True jeśli cokolwiek zmieniono.
    """
    if not spans:
        return False

    # `spans` pochodzi z `detect_all.detect_in_text`, który przez
    # `merge.collapse_for_replacement` już gwarantuje brak nakładających się
    # span-ów (z każdego zagnieżdżonego klastra wybrany jest jeden, o
    # najwyższym priorytecie) - bezpiecznie sortować i nakładać wprost.
    #
    # Sortuj malejąco po starcie, żeby podmiana jednego spana nie przesuwała
    # offsetów pozostałych (operujemy na kopii tekstu per-węzeł, nie na part.text).
    spans_sorted = sorted(spans, key=lambda s: s[0], reverse=True)
    changed = False

    for start, end, label in spans_sorted:
        affected = [n for n in part.nodes if n.start < end and n.end > start]
        if not affected:
            continue
        changed = True
        affected.sort(key=lambda n: n.start)

        label_written = False
        for node in affected:
            local_start = max(start, node.start) - node.start
            local_end = min(end, node.end) - node.start
            original = getattr(node.element, node.attr) or ""
            before = original[:local_start]
            after = original[local_end:]

            if not label_written:
                setattr(node.element, node.attr, before + label + after)
                label_written = True
            else:
                setattr(node.element, node.attr, before + after)

    return changed


def _replace_spans_in_string(text: str, spans: list[tuple[int, int, str]]) -> str:
    for start, end, label in sorted(spans, key=lambda s: s[0], reverse=True):
        text = text[:start] + label + text[end:]
    return text


def _attr_localname(key: str) -> str:
    if key.startswith("{"):
        return key.split("}", 1)[1]
    return key


# [Content_Types].xml nie niesie żadnej treści dokumentu — same rozszerzenia
# plików i referencje do nazw części pakietu (`PartName`). Te referencje są
# STRUKTURALNE: muszą się dosłownie zgadzać z rzeczywistymi nazwami wpisów w
# archiwum ZIP, więc ta część jest pominięta w skanowaniu w całości (nie
# ryzykujemy fałszywego trafienia detektora psującego integralność pakietu).
_STRUCTURAL_ONLY_PARTS_EXACT = frozenset({"[Content_Types].xml"})

# Części czysto strukturalne/typograficzne (katalog stylów, definicje list,
# tabela czcionek, motyw kolorów, ustawienia web) — nigdy nie niosą treści
# dokumentu, tylko nazwy/identyfikatory/maski bitowe. Realny błąd znaleziony
# testem e2e: nazwa czcionki "Times New Roman" i maski hex w fontTable.xml
# fałszywie dopasowywały się do detektorów (instytucja/Osoba/IMEI), a po
# podmianie dokument tracił oryginalne formatowanie - sprzecznie z wymogiem
# zachowania układu/formatowania oryginału. `word/settings.xml` CELOWO nie
# jest tu wykluczone - to właśnie tam żyją `w:docVar` z realnymi danymi
# (np. NIP wstrzyknięty przez pole scalania w szablonie pisma).
_STRUCTURAL_ONLY_PARTS_PREFIXES = (
    "word/fontTable.xml",
    "word/numbering.xml",
    "word/styles.xml",
    "word/stylesWithEffects.xml",
    "word/theme/",
    "word/webSettings.xml",
)


def _is_structural_only_part(part_name: str) -> bool:
    if part_name in _STRUCTURAL_ONLY_PARTS_EXACT:
        return True
    return any(part_name.startswith(prefix) for prefix in _STRUCTURAL_ONLY_PARTS_PREFIXES)


def apply_attribute_replacements(
    part_name: str, root: etree._Element, detect_fn: Callable[[str], list[tuple[int, int, str]]]
) -> bool:
    """Skanuje i podmienia dane wrażliwe zaszyte w WARTOŚCIACH atrybutów XML
    (np. `w:docVar` w settings.xml, `Target` zewnętrznych hiperłączy w .rels,
    alt-text obrazów, aliasy/tagi kontrolek zawartości) — miejsca, których
    żaden węzeł `.text`/`.tail` nie obejmuje, a które `leak_check.py` i tak
    przeszukuje.

    Każda wartość atrybutu jest niezależnym łańcuchem znaków (nie częścią
    złączonego `part.text`), więc `detect_fn` jest wywoływane osobno per
    wartość — nadal na tym samym, per-dokumentowym rejestrze tożsamości
    (ta sama zamknięta funkcja `detect_fn`), więc numeracja etykiet
    pozostaje spójna z resztą dokumentu.

    Uwaga bezpieczeństwa: w plikach `.rels` atrybut `Target` bywa
    WEWNĘTRZNĄ ścieżką do innej części pakietu (np. `docProps/thumbnail.jpeg`,
    `media/image1.png`) — musi zostać dosłownie nietknięty, inaczej podmiana
    (nawet jeden fałszywie dodatni fragment) psuje archiwum ZIP w sposób
    nie do naprawienia. Dlatego w `.rels` skanujemy WYŁĄCZNIE `Target`
    relacji z `TargetMode="External"` (rzeczywiste URL-e/mailto, nigdy
    referencje do części pakietu) — `Id`/`Type`/wewnętrzny `Target` zostają
    zawsze bez zmian.
    """
    if _is_structural_only_part(part_name):
        return False

    changed = False
    is_rels = part_name.endswith(".rels")

    for elem in root.iter():
        if not isinstance(elem.tag, str):
            continue  # pomiń komentarze/PI XML (tag nie jest stringiem)

        if is_rels:
            if _attr_localname(elem.tag) != "Relationship" or elem.get("TargetMode") != "External":
                continue
            value = elem.get("Target")
            if not value:
                continue
            spans = detect_fn(value)
            if not spans:
                continue
            new_value = _replace_spans_in_string(value, spans)
            if new_value != value:
                elem.set("Target", new_value)
                changed = True
            continue

        for key, value in list(elem.attrib.items()):
            if not value or _attr_localname(key) in _TECHNICAL_ATTR_LOCALNAMES:
                continue
            spans = detect_fn(value)
            if not spans:
                continue
            new_value = _replace_spans_in_string(value, spans)
            if new_value != value:
                elem.attrib[key] = new_value
                changed = True
    return changed


def _iterate_target_parts(zf: zipfile.ZipFile) -> list[str]:
    """Wszystkie części pakietu, które mogą nieść tekst/atrybuty XML —
    świadomie tak samo szerokie jak `leak_check._all_text_parts` (`.xml` i
    `.rels`), żeby to, co widzi walidacja przed zapisem, dokładnie odpowiadało
    temu, co ten moduł faktycznie skanuje i potrafi podmienić."""
    return sorted(n for n in zf.namelist() if n.endswith(".xml") or n.endswith(".rels"))


def process_docx(
    input_path: str | Path,
    output_path: str | Path,
    detect_fn: Callable[[str], list[tuple[int, int, str]]],
) -> list[str]:
    """Wczytuje .docx, uruchamia `detect_fn` na tekście każdej istotnej części
    pakietu, nakłada podmiany i zapisuje wynikowy plik, zachowując resztę
    pakietu (obrazy, style, .rels itd.) bez zmian.

    `detect_fn` przyjmuje złączony tekst części i zwraca listę
    (start, end, etykieta) do podmiany.

    Zwraca listę nazw części, w których faktycznie coś podmieniono
    (do celów logowania bez treści — patrz higiena logów w planie).
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    shutil.copyfile(input_path, output_path)

    with zipfile.ZipFile(input_path, "r") as zin:
        target_names = _iterate_target_parts(zin)
        original_bytes = {name: zin.read(name) for name in target_names}

    modified_bytes: dict[str, bytes] = {}
    changed_parts: list[str] = []

    for name, xml_bytes in original_bytes.items():
        if _is_structural_only_part(name):
            continue

        try:
            part = load_part_text(name, xml_bytes)
        except etree.XMLSyntaxError:
            continue

        part_changed = False
        if part.text:
            spans = detect_fn(part.text)
            if apply_replacements(part, spans):
                part_changed = True

        if apply_attribute_replacements(name, part.tree.getroot(), detect_fn):
            part_changed = True

        if part_changed:
            changed_parts.append(name)
            modified_bytes[name] = etree.tostring(
                part.tree, xml_declaration=True, encoding="UTF-8", standalone=True
            )

    if modified_bytes:
        _rewrite_zip_parts(output_path, modified_bytes)

    return changed_parts


def _rewrite_zip_parts(docx_path: Path, replacements: dict[str, bytes]) -> None:
    """Podmienia wybrane części w istniejącym pliku .docx (ZIP), zachowując
    resztę archiwum bajt-w-bajt (obrazy, fonty, style, .rels itd.)."""
    tmp_path = docx_path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(docx_path, "r") as zin, zipfile.ZipFile(
        tmp_path, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            data = replacements.get(item.filename, zin.read(item.filename))
            zout.writestr(item, data)
    tmp_path.replace(docx_path)


def has_tracked_changes(docx_path: str | Path) -> bool:
    """Wykrywa czy dokument ma aktywne śledzenie zmian (w:ins/w:del w treści)."""
    with zipfile.ZipFile(docx_path, "r") as zf:
        if "word/document.xml" not in zf.namelist():
            return False
        xml_bytes = zf.read("word/document.xml")
    root = etree.fromstring(xml_bytes)
    return bool(root.find(f".//{{{W_NS}}}ins") is not None or root.find(f".//{{{W_NS}}}del") is not None)


def has_document_protection(docx_path: str | Path) -> bool:
    """Wykrywa `w:documentProtection` w `word/settings.xml` (ochrona edycji/
    formularza/śledzenia zmian narzucona na dokument wejściowy — patrz plan,
    sekcja "Obsługa przypadków brzegowych plików wejściowych")."""
    with zipfile.ZipFile(docx_path, "r") as zf:
        if "word/settings.xml" not in zf.namelist():
            return False
        xml_bytes = zf.read("word/settings.xml")
    root = etree.fromstring(xml_bytes)
    return root.find(f".//{{{W_NS}}}documentProtection") is not None


def remove_document_protection(docx_path: str | Path) -> bool:
    """Usuwa `w:documentProtection` z `word/settings.xml`, jeśli obecny.

    Decyzja projektowa: wynikowy plik zanonimizowany ma być swobodnie
    edytowalny przez prawnika (np. do dalszych poprawek pisma) - ochrona
    edycji odziedziczona z oryginału nie ma tu żadnej wartości ochronnej
    (dokument i tak trafia do rąk tej samej osoby), a jej zachowanie
    utrudniałoby dalszą pracę z wynikiem bez wyraźnej korzyści.

    Zwraca True jeśli coś faktycznie usunięto.
    """
    docx_path = Path(docx_path)
    with zipfile.ZipFile(docx_path, "r") as zf:
        if "word/settings.xml" not in zf.namelist():
            return False
        xml_bytes = zf.read("word/settings.xml")

    root = etree.fromstring(xml_bytes)
    protection_nodes = root.findall(f".//{{{W_NS}}}documentProtection")
    if not protection_nodes:
        return False

    for node in protection_nodes:
        node.getparent().remove(node)

    new_bytes = etree.tostring(
        root.getroottree(), xml_declaration=True, encoding="UTF-8", standalone=True
    )
    _rewrite_zip_parts(docx_path, {"word/settings.xml": new_bytes})
    return True
