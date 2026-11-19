import sqlite3
from pathlib import Path

from scifi.literature.zotero.models import ZoteroAuditCard, ZoteroNote
from scifi.literature.zotero.notes import (
    filter_items_by_tags,
    get_collection_notes,
    get_item_notes,
    strip_zotero_note_html,
)
from scifi.literature.zotero.reader import ZoteroLocalReader
from scifi.literature.zotero.writer import ZoteroLocalWriter


def _create_minimal_zotero_notes_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "zotero.sqlite"
    (tmp_path / "storage").mkdir(exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE itemTypes (itemTypeID INT PRIMARY KEY, typeName TEXT);
        INSERT INTO itemTypes VALUES (1, 'journalArticle'), (2, 'note'), (3, 'attachment');
        CREATE TABLE items (itemID INT PRIMARY KEY, itemTypeID INT, key TEXT);
        CREATE TABLE deletedItems (itemID INT PRIMARY KEY);
        CREATE TABLE fields (fieldID INT PRIMARY KEY, fieldName TEXT);
        INSERT INTO fields VALUES (1, 'title');
        CREATE TABLE itemDataValues (valueID INT PRIMARY KEY, value TEXT);
        CREATE TABLE itemData (itemID INT, fieldID INT, valueID INT);
        CREATE TABLE itemNotes (itemID INT PRIMARY KEY, parentItemID INT, note TEXT, title TEXT);
        CREATE TABLE tags (tagID INT PRIMARY KEY, name TEXT);
        CREATE TABLE itemTags (itemID INT, tagID INT);
        CREATE TABLE collections (collectionID INT PRIMARY KEY, collectionName TEXT, parentCollectionID INT);
        CREATE TABLE collectionItems (collectionID INT, itemID INT);
        CREATE TABLE itemAttachments (itemID INT PRIMARY KEY, parentItemID INT, contentType TEXT, path TEXT);
        """
    )
    cur.executemany(
        "INSERT INTO items VALUES (?, ?, ?)",
        [(10, 1, "PAP1"), (11, 2, "NOT1"), (12, 2, "DEL1"), (13, 2, "STN1")],
    )
    cur.execute("INSERT INTO deletedItems VALUES (12)")
    cur.execute("INSERT INTO itemDataValues VALUES (100, 'Lyapunov Safe MARL')")
    cur.execute("INSERT INTO itemData VALUES (10, 1, 100)")
    cur.executemany(
        "INSERT INTO itemNotes VALUES (?, ?, ?, ?)",
        [
            (
                11,
                10,
                '<div class="zotero-note"><h1>Gap Idea</h1><p>Missing <b>depot queue</b> &amp; wind coupling.</p><ul><li>Bridge A</li></ul></div>',
                "Gap Idea",
            ),
            (12, 10, "<p>Deleted note should not appear</p>", "Deleted"),
            (
                13,
                None,
                "<p>Standalone supervisor note on target venues: IEEE TVT vs RA-L.</p>",
                "Supervisor Note",
            ),
        ],
    )
    cur.executemany("INSERT INTO tags VALUES (?, ?)", [(1, "#foundation"), (2, "uav-charging")])
    cur.executemany("INSERT INTO itemTags VALUES (?, ?)", [(10, 1), (11, 2), (13, 1)])
    cur.execute("INSERT INTO collections VALUES (1, 'UAV-MARL', NULL)")
    cur.executemany("INSERT INTO collectionItems VALUES (?, ?)", [(1, 10), (1, 13)])
    conn.commit()
    conn.close()
    return tmp_path


def _create_zotero_notes_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "zotero.sqlite"
    (tmp_path / "storage").mkdir(exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE itemTypes (itemTypeID INT PRIMARY KEY, typeName TEXT);
        INSERT INTO itemTypes VALUES (1, 'journalArticle'), (2, 'note'), (3, 'attachment');
        CREATE TABLE items (itemID INT PRIMARY KEY, itemTypeID INT, key TEXT, dateModified TEXT);
        CREATE TABLE deletedItems (itemID INT PRIMARY KEY);
        CREATE TABLE fields (fieldID INT PRIMARY KEY, fieldName TEXT);
        INSERT INTO fields VALUES (1, 'title');
        CREATE TABLE itemDataValues (valueID INT PRIMARY KEY, value TEXT);
        CREATE TABLE itemData (itemID INT, fieldID INT, valueID INT);
        CREATE TABLE itemNotes (itemID INT PRIMARY KEY, parentItemID INT, note TEXT, title TEXT);
        CREATE TABLE tags (tagID INT PRIMARY KEY, name TEXT);
        CREATE TABLE itemTags (itemID INT, tagID INT);
        CREATE TABLE collections (collectionID INT PRIMARY KEY, collectionName TEXT, parentCollectionID INT);
        CREATE TABLE collectionItems (collectionID INT, itemID INT);
        CREATE TABLE itemAttachments (itemID INT PRIMARY KEY, parentItemID INT, contentType TEXT, path TEXT, storageHash TEXT, storageModTime INT);
        """
    )
    cur.executemany(
        "INSERT INTO items VALUES (?, ?, ?, ?)",
        [
            (10, 1, "PAP1", "2026-11-19 10:00:00"),
            (11, 2, "NOT1", "2026-11-19 10:05:00"),
            (12, 2, "DEL1", "2026-11-19 10:06:00"),
            (13, 2, "STN1", "2026-11-19 10:07:00"),
            (14, 2, "SCF1", "2026-11-19 10:08:00"),
        ],
    )
    cur.execute("INSERT INTO deletedItems VALUES (12)")
    cur.execute("INSERT INTO itemDataValues VALUES (100, 'Lyapunov Safe MARL')")
    cur.execute("INSERT INTO itemData VALUES (10, 1, 100)")
    cur.executemany(
        "INSERT INTO itemNotes VALUES (?, ?, ?, ?)",
        [
            (
                11,
                10,
                '<div class="zotero-note"><h1>Gap Idea</h1><p>Missing <b>depot queue</b> &amp; wind coupling.</p><ul><li>Bridge A</li></ul></div>',
                "Gap Idea",
            ),
            (12, 10, "<p>Deleted note should not appear</p>", "Deleted"),
            (13, None, "<p>Standalone supervisor note on target venues: IEEE TVT vs RA-L.</p>", "Supervisor Note"),
            (
                14,
                10,
                '<div class="scifi-audit-card" data-scifi-version="2.0"><h3>SciFi Scientific Audit Card</h3></div>',
                "SciFi Card",
            ),
        ],
    )
    cur.executemany("INSERT INTO tags VALUES (?, ?)", [(1, "#foundation"), (2, "uav-charging")])
    cur.executemany("INSERT INTO itemTags VALUES (?, ?)", [(10, 1), (11, 2), (13, 1)])
    cur.execute("INSERT INTO collections VALUES (1, 'UAV-MARL', NULL)")
    cur.executemany("INSERT INTO collectionItems VALUES (?, ?)", [(1, 10), (1, 13)])
    conn.commit()
    conn.close()
    return tmp_path


def test_strip_zotero_note_html_preserves_paragraph_and_list_boundaries():
    raw = "<div><h2>Title</h2><p>First para</p><p>Second &amp; para<br/>line two</p><ul><li>Item 1</li><li>Item 2</li></ul></div>"
    cleaned = strip_zotero_note_html(raw)
    assert "First para\n" in cleaned
    assert "Second & para\nline two" in cleaned
    assert "- Item 1" in cleaned
    assert "- Item 2" in cleaned
    assert "First paraSecond" not in cleaned


def test_read_item_and_collection_notes_and_filter_tags(tmp_path: Path):
    z_dir = _create_minimal_zotero_notes_db(tmp_path)
    reader = ZoteroLocalReader(data_dir=z_dir)

    item_notes = get_item_notes(reader, "PAP1")
    assert len(item_notes) == 1
    n = item_notes[0]
    assert isinstance(n, ZoteroNote)
    assert n.key == "NOT1"
    assert n.parent_item_key == "PAP1"
    assert "Missing depot queue & wind coupling." in n.text
    assert "- Bridge A" in n.text
    assert "Deleted note" not in n.text
    assert "uav-charging" in n.tags

    assert len(reader.get_item_notes("PAP1")) == 1

    col_notes = get_collection_notes(reader, "UAV-MARL")
    assert {cn.key for cn in col_notes} == {"NOT1", "STN1"}
    assert len(reader.get_collection_notes("UAV-MARL")) == 2

    filtered = filter_items_by_tags(col_notes, ["foundation"])
    assert [f.key for f in filtered] == ["STN1"]
    filtered_hash = filter_items_by_tags(col_notes, ["#UAV-CHARGING"])
    assert [f.key for f in filtered_hash] == ["NOT1"]


def test_strip_html_and_read_item_and_collection_notes(tmp_path: Path):
    z_dir = _create_zotero_notes_db(tmp_path)
    reader = ZoteroLocalReader(data_dir=z_dir)

    item_notes = get_item_notes(reader, "PAP1")
    assert len(item_notes) == 2
    user_notes = [n for n in item_notes if not n.is_scifi_card]
    scifi_notes = [n for n in item_notes if n.is_scifi_card]
    assert len(user_notes) == 1 and len(scifi_notes) == 1
    n = user_notes[0]
    assert isinstance(n, ZoteroNote)
    assert n.key == "NOT1"
    assert n.parent_item_key == "PAP1"
    assert "Missing depot queue & wind coupling." in n.text
    assert "- Bridge A" in n.text
    assert "uav-charging" in n.tags
    assert n.date_modified == "2026-11-19 10:05:00"

    col_notes = get_collection_notes(reader, "UAV-MARL")
    assert {cn.key for cn in col_notes} == {"NOT1", "STN1", "SCF1"}
    filtered = filter_items_by_tags(col_notes, ["foundation"])
    assert [f.key for f in filtered] == ["STN1"]


def test_audit_card_v2_html_and_lossless_offline_staging(tmp_path: Path, monkeypatch):
    stage_file = tmp_path / "queue.json"
    writer = ZoteroLocalWriter(stage_file=stage_file)
    monkeypatch.setattr(writer, "is_server_available", lambda: False)

    card = ZoteroAuditCard(
        item_key="PAP1",
        contribution="Joint Lyapunov + CBF controller",
        summary="2-sentence summary",
        pdf_source="OpenAlex Green OA",
        citation_verified=True,
        claims_checked=[{"claim": "Achieves O(1)", "verdict": "ENTAILED", "evidence": "Sec III"}],
        limitations=["Static wind model"],
        relevance_notes="Primary baseline",
        authors_info=[
            {
                "name": "Wei Xu",
                "orcid": "0000-0001-2345-6789",
                "email": "wxu@ieee.org",
                "institution": "MIT",
                "h_index": 28,
            }
        ],
        methods=["Lyapunov-MAPPO"],
        claims=["Bounded queue drift"],
        gaps=["No 3D wind turbulence"],
        contradictions=["Contradicts Smith2024 on latency"],
        kg_digested_at="2026-11-19T20:00:00Z",
    )
    html = writer.format_audit_card_html(card)
    assert 'data-scifi-version="2.0"' in html
    assert "wxu@ieee.org" in html and "0000-0001-2345-6789" in html
    assert "Lyapunov-MAPPO" in html and "Contradicts Smith2024 on latency" in html

    res = writer.push_audit_card_note("PAP1", card)
    assert res["status"] == "STAGED"
    queued = writer._load_staged_queue()
    restored = ZoteroAuditCard.from_dict(queued[0]["card"])
    assert restored.summary == "2-sentence summary"
    assert restored.claims_checked == card.claims_checked
    assert restored.authors_info == card.authors_info
    assert restored.methods == ["Lyapunov-MAPPO"]
    assert restored.contradictions == ["Contradicts Smith2024 on latency"]
