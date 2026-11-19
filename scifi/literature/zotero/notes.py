"""
Zero-copy Zotero child and standalone note reader and tag filter utilities.
"""

from __future__ import annotations

import html
import re
import sqlite3
from collections.abc import Sequence
from typing import TYPE_CHECKING

from scifi.literature.zotero.models import ZoteroNote

if TYPE_CHECKING:
    from scifi.literature.zotero.reader import ZoteroLocalReader

_BLOCK_CLOSE_RE = re.compile(r"</(?:p|div|h[1-6]|blockquote|tr|ul|ol)>", re.IGNORECASE)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_LI_OPEN_RE = re.compile(r"<li(?:\s[^>]*)?>", re.IGNORECASE)
_LI_CLOSE_RE = re.compile(r"</li>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def strip_zotero_note_html(raw_html: str | None) -> str:
    """
    Convert Zotero note HTML into clean readable plain text while preserving
    paragraph breaks and list bullet boundaries.
    """
    if not raw_html:
        return ""
    text = str(raw_html)
    text = _BR_RE.sub("\n", text)
    text = _LI_OPEN_RE.sub("\n- ", text)
    text = _LI_CLOSE_RE.sub("\n", text)
    text = _BLOCK_CLOSE_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    lines = [line.strip() for line in text.splitlines()]
    cleaned_lines: list[str] = []
    blank_run = 0
    for line in lines:
        if not line:
            blank_run += 1
            if blank_run <= 1 and cleaned_lines:
                cleaned_lines.append("")
        else:
            blank_run = 0
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _extract_note_tags(cur: sqlite3.Cursor, item_id: int) -> list[str]:
    try:
        rows = cur.execute(
            """
            SELECT t.name
            FROM itemTags it
            JOIN tags t ON it.tagID = t.tagID
            WHERE it.itemID = ?
            """,
            (item_id,),
        ).fetchall()
        return [r[0] for r in rows if r[0]]
    except Exception:
        return []


def _deleted_clause(cur: sqlite3.Cursor, alias: str = "i") -> str:
    has_deleted = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='deletedItems'"
    ).fetchone()
    return f"AND {alias}.itemID NOT IN (SELECT itemID FROM deletedItems)" if has_deleted else ""


def _items_has_column(cur: sqlite3.Cursor, column_name: str, table_name: str = "items") -> bool:
    try:
        cols = {r[1] for r in cur.execute(f"PRAGMA table_info({table_name})").fetchall()}
        return column_name in cols
    except Exception:
        return False


def _extract_item_notes_with_cursor(
    cur: sqlite3.Cursor,
    parent_id: int,
    parent_key: str,
) -> list[ZoteroNote]:
    has_notes = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='itemNotes'"
    ).fetchone()
    if not has_notes:
        return []
    del_sql = _deleted_clause(cur, "i")
    date_col = "i.dateModified" if _items_has_column(cur, "dateModified") else "NULL AS dateModified"
    rows = cur.execute(
        f"""
        SELECT i.itemID, i.key, n.note, n.title, {date_col}
        FROM itemNotes n
        JOIN items i ON n.itemID = i.itemID
        WHERE n.parentItemID = ? {del_sql}
        ORDER BY i.itemID ASC
        """,
        (parent_id,),
    ).fetchall()

    notes: list[ZoteroNote] = []
    for note_id, note_key, raw_html, title, date_mod in rows:
        raw_s = raw_html or ""
        notes.append(
            ZoteroNote(
                note_id=int(note_id),
                key=str(note_key),
                parent_item_key=parent_key,
                title=title,
                text=strip_zotero_note_html(raw_s),
                raw_html=raw_s,
                tags=_extract_note_tags(cur, int(note_id)),
                is_scifi_card="scifi-audit-card" in raw_s,
                date_modified=str(date_mod) if date_mod is not None else None,
            )
        )
    return notes


def get_item_notes(reader: ZoteroLocalReader, item_key: str) -> list[ZoteroNote]:
    """
    Retrieve non-deleted child notes (`itemNotes`) attached to a specific Zotero item key.
    """
    conn = reader._get_connection()
    try:
        cur = conn.cursor()
        parent_row = cur.execute("SELECT itemID FROM items WHERE key = ?", (item_key,)).fetchone()
        if not parent_row:
            return []
        return _extract_item_notes_with_cursor(cur, int(parent_row[0]), item_key)
    finally:
        conn.close()


def get_collection_notes(reader: ZoteroLocalReader, collection_name_or_id: str | int) -> list[ZoteroNote]:
    """
    Retrieve both child notes of papers in a collection and standalone notes placed
    directly inside the collection.
    """
    if isinstance(collection_name_or_id, int):
        col_ids = [collection_name_or_id]
    else:
        cols = reader.get_collections_by_name(collection_name_or_id)
        if not cols:
            return []
        col_ids = [c.collection_id for c in cols]

    conn = reader._get_connection()
    try:
        cur = conn.cursor()
        has_notes = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='itemNotes'"
        ).fetchone()
        if not has_notes:
            return []

        del_sql = _deleted_clause(cur, "ni")
        date_col = "ni.dateModified" if _items_has_column(cur, "dateModified") else "NULL AS dateModified"
        placeholders = ",".join("?" for _ in col_ids)

        rows = cur.execute(
            f"""
            SELECT DISTINCT ni.itemID, ni.key, pi.key AS parentKey, n.note, n.title, {date_col}
            FROM itemNotes n
            JOIN items ni ON n.itemID = ni.itemID
            LEFT JOIN items pi ON n.parentItemID = pi.itemID
            WHERE (
                ni.itemID IN (SELECT itemID FROM collectionItems WHERE collectionID IN ({placeholders}))
                OR n.parentItemID IN (SELECT itemID FROM collectionItems WHERE collectionID IN ({placeholders}))
            )
            {del_sql}
            ORDER BY ni.itemID ASC
            """,
            tuple(col_ids) + tuple(col_ids),
        ).fetchall()

        notes: list[ZoteroNote] = []
        for note_id, note_key, parent_key, raw_html, title, date_mod in rows:
            raw_s = raw_html or ""
            notes.append(
                ZoteroNote(
                    note_id=int(note_id),
                    key=str(note_key),
                    parent_item_key=str(parent_key) if parent_key else None,
                    title=title,
                    text=strip_zotero_note_html(raw_s),
                    raw_html=raw_s,
                    tags=_extract_note_tags(cur, int(note_id)),
                    is_scifi_card="scifi-audit-card" in raw_s,
                    date_modified=str(date_mod) if date_mod is not None else None,
                )
            )
        return notes
    finally:
        conn.close()


def _normalize_tag(tag: str) -> str:
    return tag.strip().lstrip("#").lower()


def filter_items_by_tags[T](
    items: Sequence[T],
    tags: Sequence[str],
    *,
    require_all: bool = False,
) -> list[T]:
    """
    Filter ZoteroItem or ZoteroNote objects (or dicts with a 'tags' field) by tag names.
    Tag matching is case-insensitive and ignores leading '#'.
    """
    wanted = {_normalize_tag(t) for t in tags if t and _normalize_tag(t)}
    if not wanted:
        return list(items)

    matched: list[T] = []
    for item in items:
        raw_tags: Sequence[str] = (
            item.get("tags", [])
            if isinstance(item, dict)
            else getattr(item, "tags", [])
        ) or []
        item_norm = {_normalize_tag(str(t)) for t in raw_tags if t}
        if require_all:
            if wanted.issubset(item_norm):
                matched.append(item)
        else:
            if wanted & item_norm:
                matched.append(item)
    return matched
