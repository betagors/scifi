"""
Zero-Copy Local SQLite Reader for Zotero.
Reads zotero.sqlite in immutable URI mode to prevent database locking,
and resolves PDF files directly from Zotero storage directories.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from scifi.env import auto_detect_zotero_dir
from scifi.literature.zotero.models import (
    ZoteroAnnotation,
    ZoteroCollection,
    ZoteroItem,
)


class ZoteroLocalReader:
    """
    Direct zero-copy reader for local Zotero SQLite databases.
    """

    def __init__(self, data_dir: Optional[Union[str, Path]] = None) -> None:
        if data_dir is not None:
            self.data_dir = Path(data_dir).resolve()
        else:
            detected = auto_detect_zotero_dir()
            if detected is None:
                raise FileNotFoundError("Local Zotero data directory could not be auto-detected.")
            self.data_dir = detected

        self.sqlite_path = self.data_dir / "zotero.sqlite"
        self.storage_dir = self.data_dir / "storage"

    def _get_connection(self) -> sqlite3.Connection:
        """
        Open a connection to zotero.sqlite in immutable mode.
        Immutable mode guarantees SQLite will never attempt to lock the database,
        making it safe to run concurrently with the active Zotero desktop app.
        """
        if not self.sqlite_path.is_file():
            raise FileNotFoundError(f"Zotero SQLite database not found at {self.sqlite_path}")

        # Construct URI path
        norm_path = self.sqlite_path.as_posix()
        uri = f"file:///{norm_path}?immutable=1"
        return sqlite3.connect(uri, uri=True, timeout=10.0)

    def get_collections(self) -> List[ZoteroCollection]:
        """Retrieve all collections in the local Zotero library."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            rows = cur.execute(
                "SELECT collectionID, collectionName, parentCollectionID FROM collections ORDER BY collectionName"
            ).fetchall()
            return [
                ZoteroCollection(
                    collection_id=r[0],
                    name=r[1],
                    parent_collection_id=r[2],
                )
                for r in rows
            ]
        finally:
            conn.close()

    def get_collection_by_name(self, name: str) -> Optional[ZoteroCollection]:
        """Find a collection by name (case-insensitive)."""
        clean_name = name.strip().lower()
        for col in self.get_collections():
            if col.name.strip().lower() == clean_name:
                return col
        return None

    def _extract_item_fields(self, cur: sqlite3.Cursor, item_id: int) -> Dict[str, str]:
        """Extract metadata key-value pairs for an item."""
        rows = cur.execute(
            """
            SELECT f.fieldName, v.value
            FROM itemData id
            JOIN fields f ON id.fieldID = f.fieldID
            JOIN itemDataValues v ON id.valueID = v.valueID
            WHERE id.itemID = ?
            """,
            (item_id,),
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def _extract_tags(self, cur: sqlite3.Cursor, item_id: int) -> List[str]:
        """Extract tag names for an item."""
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

    def _resolve_attachment_pdf(self, cur: sqlite3.Cursor, parent_item_id: int) -> Optional[Path]:
        """Find the local PDF path for an item in Zotero storage."""
        rows = cur.execute(
            """
            SELECT i.key, ia.path
            FROM itemAttachments ia
            JOIN items i ON ia.itemID = i.itemID
            WHERE ia.parentItemID = ? AND (ia.contentType = 'application/pdf' OR ia.path LIKE '%.pdf')
            """,
            (parent_item_id,),
        ).fetchall()

        for att_key, raw_path in rows:
            if not raw_path:
                continue
            if raw_path.startswith("storage:"):
                fname = raw_path[len("storage:"):]
                cand = self.storage_dir / att_key / fname
                if cand.is_file():
                    return cand
            else:
                p = Path(raw_path)
                if p.is_file():
                    return p
        return None

    def get_collection_items(self, collection_name_or_id: Union[str, int]) -> List[ZoteroItem]:
        """Retrieve all paper items belonging to a collection."""
        if isinstance(collection_name_or_id, int):
            col_id = collection_name_or_id
        else:
            col = self.get_collection_by_name(collection_name_or_id)
            if not col:
                return []
            col_id = col.collection_id

        conn = self._get_connection()
        items: List[ZoteroItem] = []
        try:
            cur = conn.cursor()
            item_rows = cur.execute(
                """
                SELECT i.itemID, i.key
                FROM collectionItems ci
                JOIN items i ON ci.itemID = i.itemID
                WHERE ci.collectionID = ?
                """,
                (col_id,),
            ).fetchall()

            for it_id, it_key in item_rows:
                fields = self._extract_item_fields(cur, it_id)
                title = fields.get("title", "Untitled")
                doi = fields.get("DOI")
                if doi:
                    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", doi, flags=re.IGNORECASE).strip()

                extra = fields.get("extra", "")
                arxiv_id = None
                arx_match = re.search(r"arxiv:\s*(\d{4}\.\d{4,5}(?:v\d+)?|[a-zA-Z\-]+/\d+)", extra, re.IGNORECASE)
                if arx_match:
                    arxiv_id = arx_match.group(1)

                date_str = fields.get("date", "")
                year = None
                year_match = re.search(r"\b(19\d{2}|20\d{2})\b", date_str)
                if year_match:
                    year = int(year_match.group(1))

                pdf_path = self._resolve_attachment_pdf(cur, it_id)
                tags = self._extract_tags(cur, it_id)

                items.append(
                    ZoteroItem(
                        item_id=it_id,
                        key=it_key,
                        title=title,
                        doi=doi,
                        arxiv_id=arxiv_id,
                        year=year,
                        abstract=fields.get("abstractNote"),
                        publication_title=fields.get("publicationTitle"),
                        pdf_path=pdf_path,
                        tags=tags,
                    )
                )
            return items
        finally:
            conn.close()

    def get_item_by_doi(self, doi: str) -> Optional[ZoteroItem]:
        """Find an item in Zotero by DOI."""
        clean_doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", doi.strip(), flags=re.IGNORECASE)
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT i.itemID, i.key
                FROM itemData id
                JOIN fields f ON id.fieldID = f.fieldID
                JOIN itemDataValues v ON id.valueID = v.valueID
                JOIN items i ON id.itemID = i.itemID
                WHERE f.fieldName = 'DOI' AND LOWER(v.value) LIKE ?
                """,
                (f"%{clean_doi.lower()}%",),
            )
            row = cur.fetchone()
            if not row:
                return None
            it_id, it_key = row
            fields = self._extract_item_fields(cur, it_id)
            pdf_path = self._resolve_attachment_pdf(cur, it_id)
            tags = self._extract_tags(cur, it_id)
            return ZoteroItem(
                item_id=it_id,
                key=it_key,
                title=fields.get("title", "Untitled"),
                doi=clean_doi,
                abstract=fields.get("abstractNote"),
                publication_title=fields.get("publicationTitle"),
                pdf_path=pdf_path,
                tags=tags,
            )
        finally:
            conn.close()

    def get_item_by_arxiv(self, arxiv_id: str) -> Optional[ZoteroItem]:
        """Find an item in Zotero by arXiv ID (in extra or url field)."""
        clean_arx = re.sub(r"^arxiv:\s*", "", arxiv_id.strip(), flags=re.IGNORECASE)
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT i.itemID, i.key
                FROM itemData id
                JOIN fields f ON id.fieldID = f.fieldID
                JOIN itemDataValues v ON id.valueID = v.valueID
                JOIN items i ON id.itemID = i.itemID
                WHERE (f.fieldName = 'extra' OR f.fieldName = 'url') AND v.value LIKE ?
                """,
                (f"%{clean_arx}%",),
            )
            row = cur.fetchone()
            if not row:
                return None
            it_id, it_key = row
            fields = self._extract_item_fields(cur, it_id)
            pdf_path = self._resolve_attachment_pdf(cur, it_id)
            tags = self._extract_tags(cur, it_id)
            return ZoteroItem(
                item_id=it_id,
                key=it_key,
                title=fields.get("title", "Untitled"),
                arxiv_id=clean_arx,
                abstract=fields.get("abstractNote"),
                publication_title=fields.get("publicationTitle"),
                pdf_path=pdf_path,
                tags=tags,
            )
        finally:
            conn.close()

    def get_pdf_path(self, item_key: str) -> Optional[Path]:
        """Retrieve the local PDF file path for a given item key."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            row = cur.execute("SELECT itemID FROM items WHERE key = ?", (item_key,)).fetchone()
            if not row:
                return None
            return self._resolve_attachment_pdf(cur, row[0])
        finally:
            conn.close()

    def get_user_annotations(self, item_key: str) -> List[ZoteroAnnotation]:
        """Retrieve user PDF annotations (highlights, notes) for a given item key."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            row = cur.execute("SELECT itemID FROM items WHERE key = ?", (item_key,)).fetchone()
            if not row:
                return []
            parent_id = row[0]

            rows = cur.execute(
                """
                SELECT an.itemID, an.type, an.text, an.comment, an.color, an.pageLabel
                FROM itemAnnotations an
                JOIN itemAttachments ia ON an.parentItemID = ia.itemID
                WHERE ia.parentItemID = ?
                """,
                (parent_id,),
            ).fetchall()

            return [
                ZoteroAnnotation(
                    id=r[0],
                    parent_item_key=item_key,
                    type=r[1],
                    text=r[2],
                    comment=r[3],
                    color=r[4],
                    page_label=r[5],
                )
                for r in rows
            ]
        finally:
            conn.close()
