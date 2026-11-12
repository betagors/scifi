# tests/test_zotero_reader.py
import sqlite3

import pytest

from scifi.literature.zotero.reader import ZoteroLocalReader


@pytest.fixture
def mock_zotero_db(tmp_path):
    db_path = tmp_path / "zotero.sqlite"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE collections (collectionID INTEGER PRIMARY KEY, collectionName TEXT, parentCollectionID INT)"
    )
    cur.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT)")
    cur.execute("CREATE TABLE collectionItems (collectionID INT, itemID INT, PRIMARY KEY(collectionID, itemID))")
    cur.execute("CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT)")
    cur.execute("CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT)")
    cur.execute("CREATE TABLE itemData (itemID INT, fieldID INT, valueID INT)")
    cur.execute(
        "CREATE TABLE itemAttachments (itemID INTEGER PRIMARY KEY, parentItemID INT, path TEXT, contentType TEXT)"
    )
    cur.execute(
        "CREATE TABLE itemAnnotations (itemID INTEGER PRIMARY KEY, parentItemID INT, type INT, text TEXT, comment TEXT, color TEXT, pageLabel TEXT)"
    )
    cur.execute("CREATE TABLE tags (tagID INTEGER PRIMARY KEY, name TEXT)")
    cur.execute("CREATE TABLE itemTags (itemID INT, tagID INT)")

    # Insert test collection and item
    cur.execute("INSERT INTO collections VALUES (1, 'UAV', NULL)")
    cur.execute("INSERT INTO items VALUES (10, 'ITEMKEY1')")
    cur.execute("INSERT INTO items VALUES (11, 'ATTKEY1')")
    cur.execute("INSERT INTO items VALUES (12, 'ITEMKEY2')")
    cur.execute("INSERT INTO collectionItems VALUES (1, 10)")

    cur.execute(
        "INSERT INTO fields VALUES (1, 'title'), (2, 'DOI'), (3, 'extra'), (4, 'date'), (5, 'abstractNote'), (6, 'publicationTitle')"
    )
    cur.execute(
        "INSERT INTO itemDataValues VALUES (1, 'UAV Caching Study'), (2, '10.1109/TWC.2020.123'), (3, 'arXiv: 2301.12345'), (4, '2020'), (5, 'We study UAVs'), (6, 'IEEE TWC'), (7, 'Edge Computing'), (8, '10.1000/edge')"
    )

    # Item 10 fields
    cur.execute("INSERT INTO itemData VALUES (10, 1, 1), (10, 2, 2), (10, 3, 3), (10, 4, 4), (10, 5, 5), (10, 6, 6)")
    # Item 12 fields (not in UAV collection)
    cur.execute("INSERT INTO itemData VALUES (12, 1, 7), (12, 2, 8)")

    # Attachment for item 10
    cur.execute("INSERT INTO itemAttachments VALUES (11, 10, 'storage:paper.pdf', 'application/pdf')")
    # Annotation on attachment 11
    cur.execute("INSERT INTO itemAnnotations VALUES (20, 11, 1, 'Interesting result', 'Key theorem', '#ffd400', '3')")
    # Tag on item 10
    cur.execute("INSERT INTO tags VALUES (1, 'my-tag')")
    cur.execute("INSERT INTO itemTags VALUES (10, 1)")

    conn.commit()
    conn.close()

    storage_dir = tmp_path / "storage" / "ATTKEY1"
    storage_dir.mkdir(parents=True)
    (storage_dir / "paper.pdf").touch()
    return tmp_path


def test_reader_resolves_collections(mock_zotero_db):
    reader = ZoteroLocalReader(data_dir=mock_zotero_db)
    cols = reader.get_collections()
    assert len(cols) == 1
    assert cols[0].name == "UAV"
    assert cols[0].collection_id == 1


def test_reader_resolves_collection_items_and_pdf(mock_zotero_db):
    reader = ZoteroLocalReader(data_dir=mock_zotero_db)
    items = reader.get_collection_items("UAV")
    assert len(items) == 1
    item = items[0]
    assert item.key == "ITEMKEY1"
    assert item.title == "UAV Caching Study"
    assert item.doi == "10.1109/TWC.2020.123"
    assert item.arxiv_id == "2301.12345"
    assert item.year == 2020
    assert item.abstract == "We study UAVs"
    assert item.publication_title == "IEEE TWC"
    assert item.pdf_path is not None
    assert item.pdf_path.name == "paper.pdf"
    assert "my-tag" in item.tags


def test_reader_find_by_doi_and_arxiv(mock_zotero_db):
    reader = ZoteroLocalReader(data_dir=mock_zotero_db)
    item_doi = reader.get_item_by_doi("10.1109/TWC.2020.123")
    assert item_doi is not None
    assert item_doi.key == "ITEMKEY1"

    item_arx = reader.get_item_by_arxiv("2301.12345")
    assert item_arx is not None
    assert item_arx.key == "ITEMKEY1"

    item_none = reader.get_item_by_doi("nonexistent.doi")
    assert item_none is None


def test_reader_resolves_annotations(mock_zotero_db):
    reader = ZoteroLocalReader(data_dir=mock_zotero_db)
    annos = reader.get_user_annotations("ITEMKEY1")
    assert len(annos) == 1
    assert annos[0].text == "Interesting result"
    assert annos[0].comment == "Key theorem"
    assert annos[0].color == "#ffd400"
    assert annos[0].page_label == "3"
