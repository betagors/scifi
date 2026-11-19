"""
Zero-Copy Local SQLite Reader for Zotero.
Reads zotero.sqlite in immutable URI mode to prevent database locking,
and resolves PDF files directly from Zotero storage directories.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

from scifi.env import auto_detect_zotero_dir
from scifi.literature.zotero.models import (
    ZoteroAnnotation,
    ZoteroCollection,
    ZoteroItem,
    ZoteroNote,
)


class _TempSnapConnection(sqlite3.Connection):
    """SQLite connection that cleans up its temporary WAL snapshot directory on close."""

    _tmp_dir: str | None = None

    def close(self) -> None:
        try:
            super().close()
        finally:
            if self._tmp_dir:
                shutil.rmtree(self._tmp_dir, ignore_errors=True)
                self._tmp_dir = None


class ZoteroLocalReader:
    """
    Direct zero-copy reader for local Zotero SQLite databases.
    """

    def __init__(self, data_dir: str | Path | None = None) -> None:
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
        Open a read-only connection to zotero.sqlite without locking Zotero Desktop.
        When a non-empty WAL file exists, snapshot ``zotero.sqlite`` (+ ``-wal`` /
        ``-shm``) into a temporary directory so uncommitted Zotero Desktop edits
        (like newly attached PDFs) are visible; otherwise use immutable URI mode.
        """
        if not self.sqlite_path.is_file():
            raise FileNotFoundError(f"Zotero SQLite database not found at {self.sqlite_path}")

        wal_path = Path(f"{self.sqlite_path}-wal")
        if wal_path.is_file() and wal_path.stat().st_size > 0:
            tmp_dir = tempfile.mkdtemp(prefix="scifi_zotero_")
            try:
                for suffix in ("", "-wal", "-shm"):
                    src = Path(f"{self.sqlite_path}{suffix}")
                    if src.is_file():
                        shutil.copy2(src, Path(tmp_dir) / src.name)
                conn = sqlite3.connect(
                    Path(tmp_dir) / self.sqlite_path.name,
                    timeout=10.0,
                    factory=_TempSnapConnection,
                )
                conn._tmp_dir = tmp_dir
                return conn
            except Exception:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                raise

        # Construct RFC-compliant file URI in immutable mode
        uri = f"{self.sqlite_path.as_uri()}?immutable=1"
        return sqlite3.connect(uri, uri=True, timeout=10.0)

    def get_collections(self) -> list[ZoteroCollection]:
        """Retrieve all non-deleted collections in the local Zotero library."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            has_deleted = cur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='deletedCollections'"
            ).fetchone()
            deleted_clause = (
                "WHERE collectionID NOT IN (SELECT collectionID FROM deletedCollections)" if has_deleted else ""
            )
            rows = cur.execute(
                f"SELECT collectionID, collectionName, parentCollectionID FROM collections {deleted_clause} ORDER BY collectionName"
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

    def get_collection_by_name(self, name: str) -> ZoteroCollection | None:
        """Find a collection by name (case-insensitive)."""
        matches = self.get_collections_by_name(name)
        return matches[0] if matches else None

    def get_collections_by_name(self, name: str) -> list[ZoteroCollection]:
        """Find all collections matching a name (case-insensitive)."""
        clean_name = name.strip().lower()
        return [col for col in self.get_collections() if col.name.strip().lower() == clean_name]

    def find_best_matching_collection(self, citations: list[dict[str, str]]) -> tuple[str | None, int]:
        """
        Check which existing collection has the highest citation overlap with the given list of citations.
        Returns (best_collection_name, match_count).
        """
        if not citations:
            return None, 0

        collections = self.get_collections()
        if not collections:
            return None, 0

        # Build lookup set of clean DOIs and normalized titles
        cited_dois = {
            re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", c["doi"], flags=re.IGNORECASE).strip().lower()
            for c in citations
            if c.get("doi")
        }
        cited_titles = {
            re.sub(r"[^a-zA-Z0-9]", "", c["title"].lower())
            for c in citations
            if c.get("title") and len(c["title"]) >= 8
        }

        best_col: str | None = None
        best_count = 0

        for col in collections:
            items = self.get_collection_items(col.collection_id)
            count = 0
            for item in items:
                if item.doi and item.doi.lower() in cited_dois:
                    count += 1
                elif item.title:
                    clean_t = re.sub(r"[^a-zA-Z0-9]", "", item.title.lower())
                    if clean_t and clean_t in cited_titles:
                        count += 1
            if count > best_count:
                best_count = count
                best_col = col.name

        return best_col, best_count

    def _extract_item_fields(self, cur: sqlite3.Cursor, item_id: int) -> dict[str, str]:
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

    def _extract_tags(self, cur: sqlite3.Cursor, item_id: int) -> list[str]:
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

    def _extract_creators(self, cur: sqlite3.Cursor, item_id: int) -> list[str]:
        """Extract ordered author/creator names ('Last, First' or 'Name') for an item."""
        try:
            rows = cur.execute(
                """
                SELECT c.firstName, c.lastName, c.fieldMode
                FROM itemCreators ic
                JOIN creators c ON ic.creatorID = c.creatorID
                WHERE ic.itemID = ?
                ORDER BY ic.orderIndex ASC
                """,
                (item_id,),
            ).fetchall()
            creators: list[str] = []
            for first, last, field_mode in rows:
                first_s = (first or "").strip()
                last_s = (last or "").strip()
                if field_mode == 1 or not first_s:
                    if last_s:
                        creators.append(last_s)
                elif last_s:
                    creators.append(f"{last_s}, {first_s}")
                elif first_s:
                    creators.append(first_s)
            return creators
        except Exception:
            return []

    def _extract_item_type(self, cur: sqlite3.Cursor, item_id: int) -> str | None:
        """Extract Zotero itemType name (e.g., journalArticle, conferencePaper)."""
        try:
            row = cur.execute(
                """
                SELECT it.typeName
                FROM items i
                JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
                WHERE i.itemID = ?
                """,
                (item_id,),
            ).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def _extract_date_modified(self, cur: sqlite3.Cursor, item_id: int) -> str | None:
        """Extract dateModified for an item when column exists."""
        try:
            cols = {r[1] for r in cur.execute("PRAGMA table_info(items)").fetchall()}
            if "dateModified" not in cols:
                return None
            row = cur.execute("SELECT dateModified FROM items WHERE itemID = ?", (item_id,)).fetchone()
            return str(row[0]) if row and row[0] is not None else None
        except Exception:
            return None

    def _extract_attachment_hash(self, cur: sqlite3.Cursor, parent_item_id: int) -> str | None:
        """Extract storageHash or storageModTime for an item's PDF attachment when columns exist."""
        try:
            cols = {r[1] for r in cur.execute("PRAGMA table_info(itemAttachments)").fetchall()}
            has_hash = "storageHash" in cols
            has_mtime = "storageModTime" in cols
            if not has_hash and not has_mtime:
                return None
            h_col = "storageHash" if has_hash else "NULL"
            m_col = "storageModTime" if has_mtime else "NULL"
            rows = cur.execute(
                f"""
                SELECT {h_col}, {m_col}
                FROM itemAttachments
                WHERE parentItemID = ? AND (contentType = 'application/pdf' OR path LIKE '%.pdf')
                """,
                (parent_item_id,),
            ).fetchall()
            for s_hash, s_mtime in rows:
                if s_hash:
                    return str(s_hash)
                if s_mtime is not None:
                    return str(s_mtime)
            return None
        except Exception:
            return None

    def _resolve_attachment_pdf(self, cur: sqlite3.Cursor, parent_item_id: int) -> Path | None:
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
                fname = raw_path[len("storage:") :]
                cand = self.storage_dir / att_key / fname
                if cand.is_file():
                    return cand
            else:
                p = Path(raw_path)
                if p.is_file():
                    return p
        return None

    def _build_item(self, cur: sqlite3.Cursor, it_id: int, it_key: str) -> ZoteroItem:
        """Construct a ZoteroItem from an itemID and key."""
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
        authors = self._extract_creators(cur, it_id)
        item_type = self._extract_item_type(cur, it_id)
        pub_title = fields.get("publicationTitle") or fields.get("proceedingsTitle") or fields.get("bookTitle")
        date_modified = self._extract_date_modified(cur, it_id)
        attachment_hash = self._extract_attachment_hash(cur, it_id)
        from scifi.literature.zotero.notes import _extract_item_notes_with_cursor

        notes = _extract_item_notes_with_cursor(cur, it_id, it_key)

        return ZoteroItem(
            item_id=it_id,
            key=it_key,
            title=title,
            doi=doi,
            arxiv_id=arxiv_id,
            year=year,
            abstract=fields.get("abstractNote"),
            publication_title=pub_title,
            pdf_path=pdf_path,
            notes=notes,
            tags=tags,
            authors=authors,
            item_type=item_type,
            url=fields.get("url"),
            volume=fields.get("volume"),
            issue=fields.get("issue"),
            pages=fields.get("pages"),
            date_modified=date_modified,
            attachment_hash=attachment_hash,
        )

    def get_collection_items(self, collection_name_or_id: str | int) -> list[ZoteroItem]:
        """Retrieve all paper items belonging to a collection (aggregating if duplicate names exist)."""
        if isinstance(collection_name_or_id, int):
            col_ids = [collection_name_or_id]
        else:
            cols = self.get_collections_by_name(collection_name_or_id)
            if not cols:
                return []
            col_ids = [c.collection_id for c in cols]

        conn = self._get_connection()
        items: list[ZoteroItem] = []
        seen_ids: set[int] = set()
        try:
            cur = conn.cursor()
            has_deleted = cur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='deletedItems'"
            ).fetchone()
            deleted_clause = "AND i.itemID NOT IN (SELECT itemID FROM deletedItems)" if has_deleted else ""
            has_item_types = cur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='itemTypes'"
            ).fetchone()
            type_join = "LEFT JOIN itemTypes it ON i.itemTypeID = it.itemTypeID" if has_item_types else ""
            type_clause = (
                "AND (it.typeName IS NULL OR it.typeName NOT IN ('attachment', 'note', 'annotation'))"
                if has_item_types
                else ""
            )

            placeholders = ",".join("?" for _ in col_ids)
            item_rows = cur.execute(
                f"""
                SELECT i.itemID, i.key
                FROM collectionItems ci
                JOIN items i ON ci.itemID = i.itemID
                {type_join}
                WHERE ci.collectionID IN ({placeholders}) {type_clause} {deleted_clause}
                """,
                tuple(col_ids),
            ).fetchall()

            for it_id, it_key in item_rows:
                if it_id in seen_ids:
                    continue
                seen_ids.add(it_id)
                items.append(self._build_item(cur, it_id, it_key))
            return items
        finally:
            conn.close()

    def search_items(
        self,
        query: str = "",
        collection: str | None = None,
        has_pdf: bool | None = None,
        limit: int = 20,
    ) -> list[ZoteroItem]:
        """
        Search Zotero items across the entire library or within a specific collection.
        Matches case-insensitive query tokens against title, abstract, authors, venue, DOI, arXiv ID, and tags.
        """
        tokens = [t.strip().lower() for t in query.split() if t.strip()]

        if collection:
            candidates = self.get_collection_items(collection)
        else:
            conn = self._get_connection()
            candidates = []
            try:
                cur = conn.cursor()
                has_deleted = cur.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='deletedItems'"
                ).fetchone()
                deleted_clause = "AND i.itemID NOT IN (SELECT itemID FROM deletedItems)" if has_deleted else ""
                has_item_types = cur.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='itemTypes'"
                ).fetchone()
                type_join = "JOIN itemTypes it ON i.itemTypeID = it.itemTypeID" if has_item_types else ""
                type_clause = "AND it.typeName NOT IN ('attachment', 'note', 'annotation')" if has_item_types else ""
                rows = cur.execute(
                    f"""
                    SELECT i.itemID, i.key
                    FROM items i
                    {type_join}
                    WHERE 1=1 {type_clause} {deleted_clause}
                    """
                ).fetchall()
                for it_id, it_key in rows:
                    candidates.append(self._build_item(cur, it_id, it_key))
            finally:
                conn.close()

        results: list[ZoteroItem] = []
        for item in candidates:
            if has_pdf is True and item.pdf_path is None:
                continue
            if has_pdf is False and item.pdf_path is not None:
                continue
            if tokens:
                haystack = " ".join(
                    [
                        item.title or "",
                        item.abstract or "",
                        item.publication_title or "",
                        item.doi or "",
                        item.arxiv_id or "",
                        " ".join(item.authors),
                        " ".join(item.tags),
                    ]
                ).lower()
                if not all(tok in haystack for tok in tokens):
                    continue
            results.append(item)
            if limit > 0 and len(results) >= limit:
                break
        return results

    def get_item_by_title(self, title: str) -> ZoteroItem | None:
        """Find an item in Zotero by normalized title."""
        norm_target = re.sub(r"[^a-z0-9]", "", title.lower())
        if len(norm_target) < 6:
            return None
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            rows = cur.execute(
                """
                SELECT i.itemID, i.key, v.value
                FROM itemData id
                JOIN fields f ON id.fieldID = f.fieldID
                JOIN itemDataValues v ON id.valueID = v.valueID
                JOIN items i ON id.itemID = i.itemID
                WHERE f.fieldName = 'title'
                """
            ).fetchall()
            for it_id, it_key, raw_title in rows:
                if re.sub(r"[^a-z0-9]", "", (raw_title or "").lower()) == norm_target:
                    fields = self._extract_item_fields(cur, it_id)
                    return ZoteroItem(
                        item_id=it_id,
                        key=it_key,
                        title=fields.get("title", "Untitled"),
                        doi=fields.get("DOI"),
                        pdf_path=self._resolve_attachment_pdf(cur, it_id),
                    )
            return None
        finally:
            conn.close()

    def get_item_by_doi(self, doi: str) -> ZoteroItem | None:
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

    def get_item_by_arxiv(self, arxiv_id: str) -> ZoteroItem | None:
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

    def get_pdf_path(self, item_key: str) -> Path | None:
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

    def get_user_annotations(self, item_key: str) -> list[ZoteroAnnotation]:
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

    def get_item_notes(self, item_key: str) -> list[ZoteroNote]:
        """Retrieve child notes (`itemNotes`) attached to a given item key."""
        from scifi.literature.zotero.notes import get_item_notes

        return get_item_notes(self, item_key)

    def get_collection_notes(self, collection_name_or_id: str | int) -> list[ZoteroNote]:
        """Retrieve all child and standalone notes belonging to a collection."""
        from scifi.literature.zotero.notes import get_collection_notes

        return get_collection_notes(self, collection_name_or_id)
