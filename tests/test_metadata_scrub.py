import zipfile

import docx
from lxml import etree

from app.pipeline import metadata_scrub


def test_scrub_removes_author_and_last_modified_by(tmp_path):
    path = tmp_path / "doc.docx"
    document = docx.Document()
    document.core_properties.author = "Jan Kowalski"
    document.core_properties.last_modified_by = "Jan Kowalski"
    document.core_properties.title = "Pozew przeciwko Annie Nowak"
    document.add_paragraph("Treść.")
    document.save(path)

    metadata_scrub.scrub_docx_metadata(path)

    with zipfile.ZipFile(path) as zf:
        core_xml = zf.read("docProps/core.xml")
    root = etree.fromstring(core_xml)
    texts = [t for t in root.itertext() if t.strip()]
    assert "Jan Kowalski" not in texts
    assert "Pozew przeciwko Annie Nowak" not in texts


def test_neutral_output_filename_is_stable():
    assert metadata_scrub.neutral_output_filename() == "dokument_zanonimizowany.docx"
