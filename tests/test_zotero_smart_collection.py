# tests/test_zotero_smart_collection.py
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from scifi.literature.zotero.reader import ZoteroLocalReader
from scifi.literature.zotero.writer import ZoteroLocalWriter
from scifi.adapt import adapt_project


@pytest.fixture
def mock_zotero_multi_collection_db(tmp_path):
    db_path = tmp_path / "zotero.sqlite"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE collections (collectionID INTEGER PRIMARY KEY, collectionName TEXT, parentCollectionID INT)")
    cur.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT)")
    cur.execute("CREATE TABLE collectionItems (collectionID INT, itemID INT, PRIMARY KEY(collectionID, itemID))")
    cur.execute("CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT)")
    cur.execute("CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT)")
    cur.execute("CREATE TABLE itemData (itemID INT, fieldID INT, valueID INT)")
    cur.execute("CREATE TABLE itemAttachments (itemID INTEGER PRIMARY KEY, parentItemID INT, path TEXT, contentType TEXT)")
    cur.execute("CREATE TABLE itemAnnotations (itemID INTEGER PRIMARY KEY, parentItemID INT, type INT, text TEXT, comment TEXT, color TEXT, pageLabel TEXT)")
    cur.execute("CREATE TABLE tags (tagID INTEGER PRIMARY KEY, name TEXT)")
    cur.execute("CREATE TABLE itemTags (itemID INT, tagID INT)")

    # Collections
    cur.execute("INSERT INTO collections VALUES (1, 'UAV Caching', NULL)")
    cur.execute("INSERT INTO collections VALUES (2, 'Robotics', NULL)")

    # Items
    cur.execute("INSERT INTO items VALUES (10, 'KEY_UAV_1'), (11, 'KEY_UAV_2'), (12, 'KEY_ROB_1')")
    cur.execute("INSERT INTO collectionItems VALUES (1, 10), (1, 11), (2, 12)")

    # Fields
    cur.execute("INSERT INTO fields VALUES (1, 'title'), (2, 'DOI')")
    cur.execute("INSERT INTO itemDataValues VALUES (1, 'UAV Paper 1'), (2, '10.1109/UAV.1'), (3, 'UAV Paper 2'), (4, '10.1109/UAV.2'), (5, 'Robotics Paper'), (6, '10.1109/ROB.1')")

    cur.execute("INSERT INTO itemData VALUES (10, 1, 1), (10, 2, 2)")
    cur.execute("INSERT INTO itemData VALUES (11, 1, 3), (11, 2, 4)")
    cur.execute("INSERT INTO itemData VALUES (12, 1, 5), (12, 2, 6)")

    conn.commit()
    conn.close()
    return tmp_path


def test_find_best_matching_collection(mock_zotero_multi_collection_db):
    reader = ZoteroLocalReader(data_dir=mock_zotero_multi_collection_db)
    citations = [
        {"doi": "10.1109/UAV.1", "title": "UAV Paper 1"},
        {"doi": "10.1109/UAV.2", "title": "UAV Paper 2"},
    ]
    best_col, count = reader.find_best_matching_collection(citations)
    assert best_col == "UAV Caching"
    assert count == 2


def test_create_collection_offline_staging(tmp_path):
    queue_file = tmp_path / "zotero_write_queue.json"
    writer = ZoteroLocalWriter(port=23999, stage_file=queue_file)

    res = writer.create_collection("Autonomous Fleets")
    assert res["status"] == "STAGED"
    assert queue_file.is_file()
    import json
    data = json.loads(queue_file.read_text(encoding="utf-8"))
    assert data[-1]["type"] == "create_collection"
    assert data[-1]["name"] == "Autonomous Fleets"


def test_create_collection_online():
    writer = ZoteroLocalWriter()
    with patch.object(writer, "is_server_available", return_value=True), \
         patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"key": "NEWCOLKEY"})
        res = writer.create_collection("Autonomous Fleets")
        assert res["status"] in ("CREATED", "SUCCESS")
        assert mock_post.called


def test_adapt_auto_detects_collection(tmp_path, mock_zotero_multi_collection_db, monkeypatch):
    monkeypatch.setattr("scifi.adapt.auto_detect_zotero_dir", lambda: mock_zotero_multi_collection_db)
    monkeypatch.setattr("scifi.literature.zotero.reader.auto_detect_zotero_dir", lambda: mock_zotero_multi_collection_db)

    flat_repo = tmp_path / "auto_detect_repo"
    flat_repo.mkdir()
    (flat_repo / "paper.tex").write_text(r"\documentclass{article}\begin{document}Hello\end{document}", encoding="utf-8")
    (flat_repo / "refs.bib").write_text(
        "@article{p1, doi={10.1109/UAV.1}, title={UAV Paper 1}}\n"
        "@article{p2, doi={10.1109/UAV.2}, title={UAV Paper 2}}\n",
        encoding="utf-8"
    )

    res = adapt_project(flat_repo, venue="ieee", collection=None, dry_run=False)
    assert res["status"] == "SUCCESS"
    assert res["collection"] == "UAV Caching"

    config_text = (flat_repo / ".scifi" / "config.toml").read_text(encoding="utf-8")
    assert 'collection = "UAV Caching"' in config_text
