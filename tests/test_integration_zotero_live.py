# tests/test_integration_zotero_live.py

import pytest

from scifi.env import auto_detect_zotero_dir
from scifi.literature.zotero.reader import ZoteroLocalReader


def test_live_local_zotero_library_reads():
    z_dir = auto_detect_zotero_dir()
    if not z_dir or not (z_dir / "zotero.sqlite").is_file():
        pytest.skip("Local Zotero library not found on this machine.")

    reader = ZoteroLocalReader(data_dir=z_dir)
    cols = reader.get_collections()
    assert len(cols) > 0, "No collections found in local Zotero library"

    # Find a collection that contains PDFs (e.g. Review Article or others)
    found_pdf = False
    for col in cols:
        items = reader.get_collection_items(col.name)
        pdf_items = [i for i in items if i.pdf_path is not None]
        if pdf_items:
            first_pdf = pdf_items[0].pdf_path
            assert first_pdf.is_file(), f"PDF does not exist on disk: {first_pdf}"
            found_pdf = True
            break

    assert found_pdf, "Expected at least one collection with local PDFs in Zotero library"
