import zipfile

import docx
import pytest
from lxml import etree

from app.detectors.nip import detector as nip_detector
from app.detectors.pesel import detector as pesel_detector
from app.pipeline import docx_writer, leak_check


def _detect_pesel(text: str) -> list[tuple[int, int, str]]:
    return [(m.start, m.end, "[PESEL 1]") for m in pesel_detector.find_all(text)]


def _detect_nip(text: str) -> list[tuple[int, int, str]]:
    return [(m.start, m.end, "[NIP 1]") for m in nip_detector.find_all(text)]


def _inject_settings_docvar(docx_path, name: str, value: str) -> None:
    """Wstrzykuje `w:docVar` (pole scalania/zmienną dokumentu, częste w
    szablonach pism prawniczych) do word/settings.xml — wartość siedzi w
    ATRYBUCIE `w:val`, nie w tekście węzła, więc odtwarza dokładnie ten sam
    kształt danych co zgłoszony błąd (NIP wykryty przez leak_check, ale nie
    zanonimizowany przez writer)."""
    settings_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:settings xmlns:w="{docx_writer.W_NS}">'
        f'<w:docVars><w:docVar w:name="{name}" w:val="{value}"/></w:docVars>'
        f"</w:settings>"
    ).encode("utf-8")

    tmp_path = docx_path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(docx_path, "r") as zin, zipfile.ZipFile(
        tmp_path, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        written_settings = False
        for item in zin.infolist():
            if item.filename == "word/settings.xml":
                zout.writestr(item, settings_xml)
                written_settings = True
            else:
                zout.writestr(item, zin.read(item.filename))
        if not written_settings:
            zout.writestr("word/settings.xml", settings_xml)
    tmp_path.replace(docx_path)


@pytest.fixture
def sample_docx(tmp_path):
    path = tmp_path / "input.docx"
    document = docx.Document()
    document.add_paragraph("Powód, PESEL 44051401359, wnosi o...")
    document.add_paragraph("Fragment bez danych wrażliwych.")
    document.save(path)
    return path


def test_process_docx_replaces_pesel_and_keeps_rest(sample_docx, tmp_path):
    output = tmp_path / "output.docx"
    changed = docx_writer.process_docx(sample_docx, output, _detect_pesel)

    assert "word/document.xml" in changed

    result = docx.Document(output)
    paragraphs = [p.text for p in result.paragraphs]
    assert paragraphs[0] == "Powód, PESEL [PESEL 1], wnosi o..."
    assert paragraphs[1] == "Fragment bez danych wrażliwych."


def test_process_docx_preserves_other_zip_parts(sample_docx, tmp_path):
    output = tmp_path / "output.docx"
    docx_writer.process_docx(sample_docx, output, _detect_pesel)

    with zipfile.ZipFile(sample_docx) as zin, zipfile.ZipFile(output) as zout:
        assert set(zin.namelist()) == set(zout.namelist())
        # Style'e i inne nietknięte części pakietu muszą zostać identyczne.
        for name in zin.namelist():
            if name == "word/document.xml":
                continue
            assert zin.read(name) == zout.read(name), name


def test_split_run_replacement(tmp_path):
    """PESEL rozbity na wiele w:r/w:t o różnym formatowaniu (np. pogrubienie
    części numeru) musi zostać zamieniony na jedną poprawną etykietę."""
    path = tmp_path / "split.docx"
    document = docx.Document()
    p = document.add_paragraph()
    p.add_run("PESEL: 440514")
    p.add_run("01359").bold = True
    p.add_run(" powoda.")
    document.save(path)

    output = tmp_path / "split_out.docx"
    docx_writer.process_docx(path, output, _detect_pesel)

    result = docx.Document(output)
    assert result.paragraphs[0].text == "PESEL: [PESEL 1] powoda."


def test_replaces_nip_hidden_in_settings_docvar_attribute(tmp_path):
    """Regresja na zgłoszony błąd: NIP zaszyty w atrybucie `w:val` zmiennej
    dokumentu (word/settings.xml), a nie w tekście widocznym akapitu, musi
    zostać wykryty I podmieniony przez writer — a nie tylko przez leak_check,
    bo inaczej zapis zawsze się blokuje bez możliwości naprawy."""
    input_path = tmp_path / "input.docx"
    document = docx.Document()
    document.add_paragraph("Fragment bez danych wrażliwych.")
    document.save(input_path)
    _inject_settings_docvar(input_path, "NIP_Klienta", "526-000-12-46")

    output = tmp_path / "output.docx"
    changed = docx_writer.process_docx(input_path, output, _detect_nip)

    assert "word/settings.xml" in changed

    with zipfile.ZipFile(output) as zf:
        settings_bytes = zf.read("word/settings.xml")
    root = etree.fromstring(settings_bytes)
    doc_var = root.find(f".//{{{docx_writer.W_NS}}}docVar")
    assert doc_var.get(f"{{{docx_writer.W_NS}}}val") == "[NIP 1]"

    # Ten sam re-skan, który blokuje zapis w aplikacji, musi teraz przechodzić.
    assert leak_check.check_docx(output) == []
    leak_check.assert_clean(output)


def _detect_if_contains(needle: str):
    """Symuluje detektor (np. NER) trafiający fałszywie dodatnio na konkretną
    wartość - celowo wąski (nie "dopasuj wszystko"), żeby test nie psuł przy
    okazji niepowiązanych atrybutów liczbowych (np. rozmiaru strony w
    document.xml) i skupiał się wyłącznie na sprawdzanej ścieżce kodu."""

    def _fn(text: str) -> list[tuple[int, int, str]]:
        return [(0, len(text), "[Osoba 1]")] if needle in text else []

    return _fn


def test_internal_rels_target_never_touched_even_on_false_positive_match(tmp_path):
    """Regresja na realny incydent znaleziony w e2e teście: domyślny szablon
    python-docx ma w `_rels/.rels` `Relationship Target="docProps/thumbnail.jpeg"`
    BEZ `TargetMode` (czyli wewnętrzny, strukturalny — musi się zgadzać z
    rzeczywistą nazwą części w archiwum ZIP). Gdy detektor (tu celowo
    najbardziej agresywny możliwy, `_match_everything`) dopasował fragment tej
    wartości, writer nadpisał ją na coś w stylu `[Osoba 4]/thumbnail.jpeg` -
    nazwa nie istniała już w archiwum i wynikowy plik był nie do otwarcia.
    Wewnętrzny `Target` musi zostać dosłownie nietknięty niezależnie od tego,
    co zwróci detect_fn."""
    input_path = tmp_path / "input.docx"
    document = docx.Document()
    document.add_paragraph("Fragment bez danych wrażliwych.")
    document.save(input_path)

    with zipfile.ZipFile(input_path) as zin:
        original_rels = zin.read("_rels/.rels")
    assert b'Target="docProps/thumbnail.jpeg"' in original_rels
    assert b"TargetMode" not in original_rels  # zakłada wewnętrzny target

    output = tmp_path / "output.docx"
    docx_writer.process_docx(input_path, output, _detect_if_contains("docProps"))

    with zipfile.ZipFile(output) as zout:
        result_names = set(zout.namelist())
        result_rels = zout.read("_rels/.rels")

    assert "docProps/thumbnail.jpeg" in result_names
    assert result_rels == original_rels  # wewnętrzny .rels bez zmian, bajt-w-bajt

    # Plik musi wciąż być poprawnym, otwieralnym pakietem .docx.
    docx.Document(output)


def test_external_rels_target_still_anonymized(tmp_path):
    """Kontrast do powyższego: URL zewnętrznego hiperłącza (`TargetMode="External"`)
    to realna treść dokumentu (np. mailto: w stopce pisma) i MUSI zostać
    zanonimizowany, tylko wewnętrzne referencje do części pakietu są chronione."""
    input_path = tmp_path / "input.docx"
    document = docx.Document()
    document.add_paragraph("Fragment bez danych wrażliwych.")
    document.save(input_path)

    with zipfile.ZipFile(input_path, "r") as zin:
        items = {i.filename: zin.read(i.filename) for i in zin.infolist()}
    document_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId99" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
        'Target="mailto:kowalski@example.pl" TargetMode="External"/>'
        "</Relationships>"
    ).encode("utf-8")
    items["word/_rels/document.xml.rels"] = document_rels
    with zipfile.ZipFile(input_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in items.items():
            zout.writestr(name, data)

    output = tmp_path / "output.docx"
    docx_writer.process_docx(input_path, output, _detect_if_contains("kowalski"))

    with zipfile.ZipFile(output) as zf:
        result_rels = zf.read("word/_rels/document.xml.rels")
    root = etree.fromstring(result_rels)
    relationship = root.find("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
    assert relationship.get("Target") == "[Osoba 1]"


def test_has_tracked_changes_false_for_clean_doc(sample_docx):
    assert docx_writer.has_tracked_changes(sample_docx) is False


def _add_document_protection(docx_path):
    """Wstrzykuje `w:documentProtection` do word/settings.xml istniejącego
    .docx - python-docx nie ma dla tego API, więc manipulujemy XML wprost,
    tak jak zrobiłby to Word przy włączonej ochronie edycji."""
    from lxml import etree

    from app.pipeline.docx_writer import W_NS

    settings_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:settings xmlns:w="{W_NS}">'
        f'<w:documentProtection w:edit="readOnly" w:enforcement="1"/>'
        f"</w:settings>"
    ).encode("utf-8")

    tmp_path = docx_path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(docx_path, "r") as zin, zipfile.ZipFile(
        tmp_path, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        written_settings = False
        for item in zin.infolist():
            if item.filename == "word/settings.xml":
                zout.writestr(item, settings_xml)
                written_settings = True
            else:
                zout.writestr(item, zin.read(item.filename))
        if not written_settings:
            zout.writestr("word/settings.xml", settings_xml)
    tmp_path.replace(docx_path)
    # potwierdź że XML jest poprawny
    etree.fromstring(settings_xml)


def test_has_document_protection_true_when_present(sample_docx):
    _add_document_protection(sample_docx)
    assert docx_writer.has_document_protection(sample_docx) is True


def test_has_document_protection_false_for_clean_doc(sample_docx):
    assert docx_writer.has_document_protection(sample_docx) is False


def test_remove_document_protection_strips_node_and_reports_change(sample_docx):
    _add_document_protection(sample_docx)
    assert docx_writer.remove_document_protection(sample_docx) is True
    assert docx_writer.has_document_protection(sample_docx) is False
    # drugie wywołanie - nic już nie ma do usunięcia
    assert docx_writer.remove_document_protection(sample_docx) is False


def test_remove_document_protection_noop_when_no_settings_part(sample_docx):
    assert docx_writer.remove_document_protection(sample_docx) is False
