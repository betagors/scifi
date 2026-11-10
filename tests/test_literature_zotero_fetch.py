# tests/test_literature_zotero_fetch.py
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from scifi.literature.fetcher import find_local_pdf
from scifi.literature.models import PaperRecord, PaperIdentifierRecord


@pytest.fixture(autouse=True)
def mock_zotero_reader_init(monkeypatch):
    """Ensure ZoteroLocalReader doesn't require a real local Zotero installation in CI."""
    monkeypatch.setattr(
        "scifi.literature.zotero.reader.ZoteroLocalReader.__init__",
        lambda self, *args, **kwargs: None,
    )


def test_find_local_pdf_resolves_from_zotero_identifier(tmp_path, monkeypatch):
    storage_dir = tmp_path / "Zotero" / "storage" / "UAVKEY"
    storage_dir.mkdir(parents=True)
    pdf_file = storage_dir / "Zhang2020.pdf"
    pdf_file.touch()
    
    # Mock Zotero reader returning pdf_file
    monkeypatch.setattr(
        "scifi.literature.zotero.reader.ZoteroLocalReader.get_pdf_path",
        lambda self, key: pdf_file if key == "UAVKEY" else None
    )
    
    paper = PaperRecord(
        id="10.1109/TWC.2020.3011881",
        title="Cache-Enabling UAV Communications",
        identifiers=[PaperIdentifierRecord(paper_id="10.1109/TWC.2020.3011881", provider="zotero", external_id="UAVKEY")]
    )
    
    resolved = find_local_pdf(paper)
    assert resolved == pdf_file

def test_find_local_pdf_resolves_from_zotero_doi(tmp_path, monkeypatch):
    storage_dir = tmp_path / "Zotero" / "storage" / "DOIKEY"
    storage_dir.mkdir(parents=True)
    pdf_file = storage_dir / "PaperByDoi.pdf"
    pdf_file.touch()
    
    class FakeItem:
        pdf_path = pdf_file

    monkeypatch.setattr(
        "scifi.literature.zotero.reader.ZoteroLocalReader.get_item_by_doi",
        lambda self, doi: FakeItem() if "3011881" in doi else None
    )
    
    paper = PaperRecord(
        id="10.1109/TWC.2020.3011881",
        title="Cache-Enabling UAV Communications",
        identifiers=[PaperIdentifierRecord(paper_id="10.1109/TWC.2020.3011881", provider="doi", external_id="10.1109/TWC.2020.3011881")]
    )
    
    resolved = find_local_pdf(paper)
    assert resolved == pdf_file


def test_find_local_pdf_resolves_with_explicit_reader(tmp_path):
    pdf_file = tmp_path / "custom.pdf"
    pdf_file.touch()
    mock_reader = MagicMock()
    mock_reader.get_pdf_path.return_value = pdf_file

    paper = PaperRecord(
        id="10.1109/TWC.2020.3011881",
        title="Cache-Enabling UAV Communications",
        identifiers=[PaperIdentifierRecord(paper_id="10.1109/TWC.2020.3011881", provider="zotero", external_id="KEY1")]
    )

    resolved = find_local_pdf(paper, zotero_reader=mock_reader)
    assert resolved == pdf_file

