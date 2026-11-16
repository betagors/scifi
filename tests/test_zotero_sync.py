# tests/test_zotero_sync.py
import json
import sqlite3
from unittest.mock import patch

import pytest

from scifi.cli import create_parser
from scifi.literature.zotero.sync import (
    ZoteroAutoSyncer,
    load_zotero_project_config,
    start_background_sync,
    stop_background_sync,
    sync_zotero_project,
)
from scifi.server import scifi_zotero_sync


@pytest.fixture
def zotero_project(tmp_path):
    """Create a minimal SciFi project + mock Zotero SQLite DB."""
    z_dir = tmp_path / "zotero_data"
    z_dir.mkdir()
    db_path = z_dir / "zotero.sqlite"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE collections (collectionID INTEGER PRIMARY KEY, collectionName TEXT, parentCollectionID INT)"
    )
    cur.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, itemTypeID INT, key TEXT)")
    cur.execute("CREATE TABLE itemTypes (itemTypeID INTEGER PRIMARY KEY, typeName TEXT)")
    cur.execute("CREATE TABLE collectionItems (collectionID INT, itemID INT, PRIMARY KEY(collectionID, itemID))")
    cur.execute("CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT)")
    cur.execute("CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT)")
    cur.execute("CREATE TABLE itemData (itemID INT, fieldID INT, valueID INT)")
    cur.execute(
        "CREATE TABLE itemAttachments (itemID INTEGER PRIMARY KEY, parentItemID INT, path TEXT, contentType TEXT)"
    )
    cur.execute("CREATE TABLE tags (tagID INTEGER PRIMARY KEY, name TEXT)")
    cur.execute("CREATE TABLE itemTags (itemID INT, tagID INT)")
    cur.execute("CREATE TABLE creators (creatorID INTEGER PRIMARY KEY, firstName TEXT, lastName TEXT, fieldMode INT)")
    cur.execute("CREATE TABLE itemCreators (itemID INT, creatorID INT, creatorTypeID INT, orderIndex INT)")

    cur.execute("INSERT INTO itemTypes VALUES (1, 'journalArticle')")
    cur.execute("INSERT INTO collections VALUES (1, 'MyPaper', NULL)")
    cur.execute("INSERT INTO items VALUES (10, 1, 'ZOTKEY10')")
    cur.execute("INSERT INTO items VALUES (20, 1, 'ZOTKEY20')")
    cur.execute("INSERT INTO collectionItems VALUES (1, 10)")

    cur.execute("INSERT INTO fields VALUES (1, 'title'), (2, 'DOI'), (3, 'date'), (4, 'publicationTitle')")
    cur.execute(
        "INSERT INTO itemDataValues VALUES "
        "(1, 'Adaptive Federated Learning'), (2, '10.1109/TWC.2025.001'), (3, '2025'), (4, 'IEEE TWC'), "
        "(5, 'Existing Library Paper'), (6, '10.1000/lib.2024')"
    )
    cur.execute("INSERT INTO itemData VALUES (10, 1, 1), (10, 2, 2), (10, 3, 3), (10, 4, 4)")
    cur.execute("INSERT INTO itemData VALUES (20, 1, 5), (20, 2, 6)")
    cur.execute("INSERT INTO creators VALUES (1, 'Alice', 'Smith', 0)")
    cur.execute("INSERT INTO itemCreators VALUES (10, 1, 1, 0)")
    conn.commit()
    conn.close()

    proj = tmp_path / "project"
    (proj / ".scifi").mkdir(parents=True)
    (proj / "paper").mkdir(parents=True)

    cfg_text = (
        '[project]\nname = "project"\n\n'
        '[manuscript]\npaper_dir = "paper"\nbib_file = "references.bib"\n\n'
        "[zotero]\n"
        "enabled = true\n"
        f'data_dir = "{str(z_dir).replace(chr(92), "/")}"\n'
        'collection = "MyPaper"\n'
        "port = 23119\n"
        'sync_bib = "references.bib"\n'
        "auto_sync = true\n"
        "sync_interval = 2.0\n"
    )
    (proj / ".scifi" / "config.toml").write_text(cfg_text, encoding="utf-8")

    # Seed references.bib with one paper already in Zotero library (not yet in collection) + one brand-new paper
    bib_text = (
        "@article{Lib2024,\n"
        "  title = {Existing Library Paper},\n"
        "  author = {Bob Jones},\n"
        "  year = {2024},\n"
        "  doi = {10.1000/lib.2024}\n"
        "}\n\n"
        "@inproceedings{New2026,\n"
        "  title = {Brand New Conference Paper},\n"
        "  author = {Carol Lee},\n"
        "  booktitle = {NeurIPS},\n"
        "  year = {2026},\n"
        "  doi = {10.1000/new.2026}\n"
        "}\n"
    )
    (proj / "paper" / "references.bib").write_text(bib_text, encoding="utf-8")
    return proj, z_dir


def test_load_zotero_project_config(zotero_project):
    proj, z_dir = zotero_project
    cfg = load_zotero_project_config(proj)
    assert cfg.enabled is True
    assert cfg.collection == "MyPaper"
    assert cfg.auto_sync is True
    assert cfg.sync_bib == "references.bib"
    assert cfg.sync_interval == 2.0


def test_bidirectional_sync_offline_stages_and_exports_bib(zotero_project):
    proj, _ = zotero_project
    with patch("scifi.literature.zotero.writer.ZoteroLocalWriter.is_server_available", return_value=False):
        res = sync_zotero_project(root=proj)

    assert res["status"] == "OFFLINE"
    assert res["collection_count"] == 1
    assert res["bib_added"] == 1
    assert res["zotero_staged"] == 2  # 1 linked + 1 created staged

    bib_content = (proj / "paper" / "references.bib").read_text(encoding="utf-8")
    assert "Smith2025Adaptive" in bib_content
    assert "10.1109/TWC.2025.001" in bib_content

    queue_file = proj / ".scifi" / "zotero_write_queue.json"
    assert queue_file.is_file()
    queue = json.loads(queue_file.read_text(encoding="utf-8"))
    types = {q["type"] for q in queue}
    assert "add_to_collection" in types
    assert "create_items" in types


def test_bidirectional_sync_online_flushes_queue(zotero_project):
    proj, _ = zotero_project
    queue_file = proj / ".scifi" / "zotero_write_queue.json"
    queue_file.write_text(
        json.dumps([{"type": "tags", "item_key": "ZOTKEY10", "tags": ["#scifi-audited"], "replace_scifi_tags": True}]),
        encoding="utf-8",
    )

    with (
        patch("scifi.literature.zotero.writer.ZoteroLocalWriter.is_server_available", return_value=True),
        patch(
            "scifi.literature.zotero.writer.ZoteroLocalWriter.flush_staged_writes", return_value=[{"status": "SUCCESS"}]
        ),
        patch("scifi.literature.zotero.writer.ZoteroLocalWriter.get_collection_key", return_value="COLKEY1"),
        patch("scifi.literature.zotero.writer.ZoteroLocalWriter.add_items_to_collection", return_value=1) as mock_link,
        patch("scifi.literature.zotero.writer.ZoteroLocalWriter.create_items", return_value=1) as mock_create,
    ):
        res = sync_zotero_project(root=proj)

    assert res["status"] == "SUCCESS"
    assert res["flushed"] == 1
    assert res["bib_added"] == 1
    assert res["zotero_linked"] == 1
    assert res["zotero_created"] == 1
    mock_link.assert_called_once_with("COLKEY1", ["ZOTKEY20"])
    assert mock_create.call_count == 1


def test_auto_syncer_skips_when_unchanged_and_runs_on_change(zotero_project):
    proj, _ = zotero_project
    syncer = ZoteroAutoSyncer(root=proj)

    with (
        patch("scifi.literature.zotero.sync.is_zotero_port_open", return_value=False),
        patch("scifi.literature.zotero.writer.is_zotero_port_open", return_value=False),
    ):
        first = syncer.sync_if_needed()
        assert first is not None
        assert first["bib_added"] == 1

        # Immediate second call with no file/port changes should skip
        second = syncer.sync_if_needed()
        assert second is None

        # Modify references.bib -> should trigger sync
        bib_path = proj / "paper" / "references.bib"
        bib_path.write_text(
            bib_path.read_text(encoding="utf-8")
            + "\n@article{Extra2026,\n  title = {Extra Paper},\n  year = {2026}\n}\n",
            encoding="utf-8",
        )
        third = syncer.sync_if_needed()
        assert third is not None


def test_background_sync_start_stop(zotero_project):
    proj, _ = zotero_project
    with (
        patch("scifi.literature.zotero.sync.is_zotero_port_open", return_value=False),
        patch("scifi.literature.zotero.writer.is_zotero_port_open", return_value=False),
    ):
        started = start_background_sync(root=proj, interval=1.0)
        assert started is True
        # Idempotent
        assert start_background_sync(root=proj, interval=1.0) is False
        stop_background_sync()


def test_cli_watch_parser_and_mcp_sync(zotero_project):
    parser = create_parser()
    args = parser.parse_args(["zotero", "watch", "--collection", "MyPaper", "--interval", "3"])
    assert args.zotero_action == "watch"
    assert args.collection == "MyPaper"
    assert args.interval == 3.0

    proj, _ = zotero_project
    with (
        patch("scifi.literature.zotero.writer.is_zotero_port_open", return_value=False),
        patch("scifi.literature.zotero.sync.Path.cwd", return_value=proj),
    ):
        res = scifi_zotero_sync()
        assert res["collection"] == "MyPaper"


def test_sync_skips_create_collection_when_present_in_live_api(zotero_project):
    proj, _ = zotero_project
    with (
        patch("scifi.literature.zotero.writer.ZoteroLocalWriter.is_server_available", return_value=True),
        patch("scifi.literature.zotero.writer.ZoteroLocalWriter.flush_staged_writes", return_value=[]),
        patch("scifi.literature.zotero.writer.ZoteroLocalWriter.get_collection_key", return_value="LIVEKEY1"),
        patch("scifi.literature.zotero.writer.ZoteroLocalWriter.create_collection") as mock_create_col,
        patch("scifi.literature.zotero.writer.ZoteroLocalWriter.add_items_to_collection", return_value=0),
        patch("scifi.literature.zotero.writer.ZoteroLocalWriter.create_items", return_value=0),
    ):
        res = sync_zotero_project(root=proj, collection="UncheckpointedCol")

    assert res["status"] == "SUCCESS"
    mock_create_col.assert_not_called()


def test_sync_skips_create_items_when_present_in_live_api(zotero_project):
    proj, _ = zotero_project
    live_items = [
        {"itemType": "journalArticle", "title": "Existing Library Paper", "DOI": "10.1000/lib.2024"},
        {"itemType": "conferencePaper", "title": "Brand New Conference Paper", "DOI": "10.1000/new.2026"},
    ]
    with (
        patch("scifi.literature.zotero.writer.ZoteroLocalWriter.is_server_available", return_value=True),
        patch("scifi.literature.zotero.writer.ZoteroLocalWriter.flush_staged_writes", return_value=[]),
        patch("scifi.literature.zotero.writer.ZoteroLocalWriter.get_collection_key", return_value="COLKEY1"),
        patch("scifi.literature.zotero.writer.ZoteroLocalWriter.get_collection_items_live", return_value=live_items),
        patch("scifi.literature.zotero.writer.ZoteroLocalWriter.create_items") as mock_create_items,
    ):
        res = sync_zotero_project(root=proj)

    assert res["status"] == "SUCCESS"
    assert res["zotero_created"] == 0
    mock_create_items.assert_not_called()


def test_cli_zotero_create_collection_links_config(tmp_path, monkeypatch):
    from scifi.commands.zotero import cmd_zotero

    proj = tmp_path / "proj"
    (proj / ".scifi").mkdir(parents=True)
    (proj / ".scifi" / "config.toml").write_text(
        '[project]\nname = "proj"\n\n[zotero]\nenabled = true\ncollection = ""\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(proj)
    monkeypatch.setenv("SCIFI_CONFIG_PATH", str(tmp_path / "global_config.json"))

    parser = create_parser()
    args = parser.parse_args(["zotero", "create-collection", "MyNewCol"])
    assert args.zotero_action == "create-collection"
    assert args.name == "MyNewCol"

    with patch(
        "scifi.literature.zotero.writer.ZoteroLocalWriter.create_collection",
        return_value={"status": "CREATED", "response": {}},
    ):
        rc = cmd_zotero(args)

    assert rc == 0
    assert 'collection = "MyNewCol"' in (proj / ".scifi" / "config.toml").read_text(encoding="utf-8")
