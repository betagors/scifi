"""
Graph-Scoped SQLite Knowledge Store for literature intelligence.
Implements WAL mode, busy timeout concurrency handling, transactional integrity
with BEGIN IMMEDIATE, multi-graph session isolation, and read-only authorizer guards.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from scifi.literature.models import (
    AuthorRecord,
    CitationRecord,
    GraphSessionRecord,
    PaperIdentifierRecord,
    PaperLocationRecord,
    PaperRecord,
    PaperVersionRecord,
)

SCHEMA_SQL = """
-- 1. Multi-Graph Session Scoping
CREATE TABLE IF NOT EXISTS graphs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    seed_paper_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Internal Canonical Paper Record
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    year INTEGER,
    publication_date TEXT,
    citation_count INTEGER DEFAULT 0,
    influential_citation_count INTEGER DEFAULT 0,
    recent_citation_growth REAL DEFAULT 0.0,
    is_retracted BOOLEAN DEFAULT 0,
    abstract TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. External Provider Identifiers
CREATE TABLE IF NOT EXISTS paper_identifiers (
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    is_canonical BOOLEAN DEFAULT 0,
    PRIMARY KEY (provider, external_id)
);

-- 4. Publication Versions
CREATE TABLE IF NOT EXISTS paper_versions (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    version_type TEXT NOT NULL,
    version_label TEXT,
    doi TEXT,
    release_date TEXT,
    reconciliation_confidence REAL DEFAULT 1.0
);

-- 5. Document Locations & Access Modeling
CREATE TABLE IF NOT EXISTS paper_locations (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    version_id TEXT REFERENCES paper_versions(id) ON DELETE SET NULL,
    location_type TEXT NOT NULL,
    is_oa BOOLEAN NOT NULL DEFAULT 0,
    oa_status TEXT NOT NULL,
    landing_page_url TEXT,
    pdf_url TEXT,
    is_accessible BOOLEAN DEFAULT 0,
    local_pdf_path TEXT
);

-- 6. Junction connecting papers to scoped graph sessions
CREATE TABLE IF NOT EXISTS graph_papers (
    graph_id TEXT NOT NULL REFERENCES graphs(id) ON DELETE CASCADE,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    node_role TEXT NOT NULL DEFAULT 'intermediate',
    topological_depth INTEGER DEFAULT 0,
    PRIMARY KEY (graph_id, paper_id)
);

-- 7. Authors & Temporal Institutional Affiliations
CREATE TABLE IF NOT EXISTS authors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    orcid TEXT,
    email TEXT,
    institution TEXT,
    homepage TEXT
);

CREATE TABLE IF NOT EXISTS paper_authors (
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    author_id TEXT NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    author_position INTEGER NOT NULL,
    is_corresponding BOOLEAN DEFAULT 0,
    PRIMARY KEY (paper_id, author_id)
);

CREATE TABLE IF NOT EXISTS paper_author_affiliations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    institution_name TEXT NOT NULL,
    ror_id TEXT,
    country_code TEXT,
    FOREIGN KEY (paper_id, author_id) REFERENCES paper_authors(paper_id, author_id) ON DELETE CASCADE
);

-- 8. Venues & Contextual Ranking Metadata
CREATE TABLE IF NOT EXISTS venues (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    venue_type TEXT NOT NULL,
    series_acronym TEXT,
    issn TEXT
);

CREATE TABLE IF NOT EXISTS venue_rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue_id TEXT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    ranking_authority TEXT NOT NULL,
    ranking_edition_or_year TEXT NOT NULL,
    rank_value TEXT NOT NULL,
    metric_definition TEXT NOT NULL,
    raw_score REAL,
    retrieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS paper_venues (
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    venue_id TEXT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    publication_year INTEGER,
    PRIMARY KEY (paper_id, venue_id)
);

-- 9. Directed Citation Network
CREATE TABLE IF NOT EXISTS citations (
    source_paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    target_paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    is_influential BOOLEAN DEFAULT 0,
    context TEXT,
    co_citation_count INTEGER DEFAULT 0,
    bibliographic_coupling_strength REAL DEFAULT 0.0,
    PRIMARY KEY (source_paper_id, target_paper_id)
);

-- 10. Granular Citation Contexts
CREATE TABLE IF NOT EXISTS citation_contexts (
    id TEXT PRIMARY KEY,
    source_paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    target_paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    context_text TEXT NOT NULL,
    section_name TEXT,
    intent TEXT,
    is_influential BOOLEAN DEFAULT 0
);

-- 11. Evidence & Provenance Registry
CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    reporting_paper_id TEXT REFERENCES papers(id) ON DELETE SET NULL,
    evidence_type TEXT NOT NULL,
    source_section TEXT,
    source_location TEXT,
    extracted_text TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    confidence REAL,
    retrieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 12. Candidate Research Gaps & Limitations
CREATE TABLE IF NOT EXISTS paper_gaps (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    gap_type TEXT NOT NULL,
    claim_summary TEXT NOT NULL,
    primary_evidence_id TEXT NOT NULL REFERENCES evidence(id) ON DELETE RESTRICT,
    verification_status TEXT NOT NULL DEFAULT 'candidate',
    corroborating_count INTEGER DEFAULT 0,
    contradicting_count INTEGER DEFAULT 0
);

-- 13. SOTA Benchmark Intelligence
CREATE TABLE IF NOT EXISTS benchmarks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    task_type TEXT NOT NULL,
    domain TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS benchmark_results (
    id TEXT PRIMARY KEY,
    benchmark_id TEXT NOT NULL REFERENCES benchmarks(id) ON DELETE CASCADE,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    version_id TEXT REFERENCES paper_versions(id) ON DELETE SET NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    is_higher_better BOOLEAN NOT NULL DEFAULT 1,
    evaluation_conditions TEXT,
    evidence_id TEXT REFERENCES evidence(id) ON DELETE RESTRICT,
    is_verified_sota BOOLEAN DEFAULT 0,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_graph_papers_paper_id ON graph_papers(paper_id);
CREATE INDEX IF NOT EXISTS idx_citations_target ON citations(target_paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_identifiers_paper ON paper_identifiers(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_authors_paper ON paper_authors(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_versions_paper ON paper_versions(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_locations_paper ON paper_locations(paper_id);
"""


class LiteratureStore:
    """
    Persistent SQLite knowledge store for multi-graph literature intelligence.
    Enforces WAL mode, busy timeout concurrency, transactions with BEGIN IMMEDIATE,
    and read-only authorizer guards.
    """

    def __init__(self, db_path: str | Path) -> None:
        if str(db_path) == ":memory:":
            self.db_path = ":memory:"
        else:
            self.db_path = Path(db_path).resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self.conn = sqlite3.connect(
            str(self.db_path),
            timeout=5.0,
            isolation_level=None,  # Autocommit mode to allow explicit BEGIN IMMEDIATE
            check_same_thread=False,
        )

        # Apply mandatory SQLite PRAGMAs
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.conn.execute("PRAGMA busy_timeout = 5000;")
        self.conn.execute("PRAGMA foreign_keys = ON;")

        # Initialize schema tables and indexes
        self._init_db()

    def _init_db(self) -> None:
        """Create tables, foreign keys, and indexes if not already existing."""
        with self._lock:
            self.conn.executescript(SCHEMA_SQL)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """
        Context-managed transaction using BEGIN IMMEDIATE.
        Ensures thread-safe and process-safe transactional writes with automatic rollback on error.
        """
        with self._lock:
            already_in_tx = self.conn.in_transaction
            if not already_in_tx:
                self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
                if not already_in_tx and self.conn.in_transaction:
                    self.conn.execute("COMMIT")
            except Exception:
                if not already_in_tx and self.conn.in_transaction:
                    self.conn.execute("ROLLBACK")
                raise

    def create_or_get_graph(
        self, graph_id: str, title: str, seed_paper_id: Optional[str] = None
    ) -> GraphSessionRecord:
        """
        Create a new graph session or return the existing session record.
        """
        with self.transaction():
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT id, title, seed_paper_id, created_at FROM graphs WHERE id = ?",
                (graph_id,),
            )
            row = cursor.fetchone()
            if row:
                return GraphSessionRecord(
                    id=row[0],
                    title=row[1],
                    seed_paper_id=row[2],
                    created_at=str(row[3]) if row[3] else None,
                )

            cursor.execute(
                "INSERT INTO graphs (id, title, seed_paper_id) VALUES (?, ?, ?)",
                (graph_id, title, seed_paper_id),
            )
            cursor.execute(
                "SELECT created_at FROM graphs WHERE id = ?",
                (graph_id,),
            )
            row = cursor.fetchone()
            created_at = str(row[0]) if row and row[0] else None
            return GraphSessionRecord(
                id=graph_id,
                title=title,
                seed_paper_id=seed_paper_id,
                created_at=created_at,
            )

    def list_graphs(self) -> list[GraphSessionRecord]:
        """List all registered graph sessions ordered by creation date."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT id, title, seed_paper_id, created_at FROM graphs ORDER BY created_at DESC"
            )
            rows = cursor.fetchall()
            return [
                GraphSessionRecord(
                    id=row[0],
                    title=row[1],
                    seed_paper_id=row[2],
                    created_at=str(row[3]) if row[3] else None,
                )
                for row in rows
            ]

    def save_paper(
        self,
        paper: PaperRecord,
        graph_id: str,
        node_role: str = "intermediate",
        topological_depth: int = 0,
    ) -> None:
        """
        Persist a canonical paper record and its sub-entities (authors, identifiers,
        versions, locations) scoped to a specific graph session.
        """
        with self.transaction():
            cursor = self.conn.cursor()

            # 1. Upsert into papers
            cursor.execute(
                """
                INSERT INTO papers (
                    id, title, year, publication_date, citation_count,
                    influential_citation_count, recent_citation_growth,
                    is_retracted, abstract
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    year = coalesce(excluded.year, papers.year),
                    publication_date = coalesce(excluded.publication_date, papers.publication_date),
                    citation_count = excluded.citation_count,
                    influential_citation_count = excluded.influential_citation_count,
                    recent_citation_growth = excluded.recent_citation_growth,
                    is_retracted = excluded.is_retracted,
                    abstract = coalesce(excluded.abstract, papers.abstract)
                """,
                (
                    paper.id,
                    paper.title,
                    paper.year,
                    paper.publication_date,
                    paper.citation_count,
                    paper.influential_citation_count,
                    paper.recent_citation_growth,
                    int(paper.is_retracted),
                    paper.abstract,
                ),
            )

            # 2. Ensure graph exists
            cursor.execute(
                "INSERT OR IGNORE INTO graphs (id, title) VALUES (?, ?)",
                (graph_id, graph_id),
            )

            # 3. Associate paper with graph session
            cursor.execute(
                """
                INSERT INTO graph_papers (graph_id, paper_id, node_role, topological_depth)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(graph_id, paper_id) DO UPDATE SET
                    node_role = excluded.node_role,
                    topological_depth = excluded.topological_depth
                """,
                (graph_id, paper.id, node_role, topological_depth),
            )

            # 4. Save authors and paper_authors junction
            for idx, author in enumerate(paper.authors, start=1):
                cursor.execute(
                    """
                    INSERT INTO authors (id, name, orcid, email, institution)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        orcid = coalesce(excluded.orcid, authors.orcid),
                        email = coalesce(excluded.email, authors.email),
                        institution = coalesce(excluded.institution, authors.institution)
                    """,
                    (author.id, author.name, author.orcid, author.email, author.institution),
                )
                cursor.execute(
                    """
                    INSERT INTO paper_authors (paper_id, author_id, author_position, is_corresponding)
                    VALUES (?, ?, ?, 0)
                    ON CONFLICT(paper_id, author_id) DO UPDATE SET
                        author_position = excluded.author_position
                    """,
                    (paper.id, author.id, idx),
                )

            # 5. Save external identifiers
            for ident in paper.identifiers:
                cursor.execute(
                    """
                    INSERT INTO paper_identifiers (paper_id, provider, external_id, is_canonical)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(provider, external_id) DO UPDATE SET
                        paper_id = excluded.paper_id,
                        is_canonical = excluded.is_canonical
                    """,
                    (paper.id, ident.provider, ident.external_id, int(ident.is_canonical)),
                )

            # 6. Save versions
            for ver in paper.versions:
                cursor.execute(
                    """
                    INSERT INTO paper_versions (id, paper_id, version_type, version_label, doi, release_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        paper_id = excluded.paper_id,
                        version_type = excluded.version_type,
                        version_label = excluded.version_label,
                        doi = excluded.doi,
                        release_date = excluded.release_date
                    """,
                    (ver.id, paper.id, ver.version_type, ver.version_label, ver.doi, ver.release_date),
                )

            # 7. Save document locations
            for loc in paper.locations:
                cursor.execute(
                    """
                    INSERT INTO paper_locations (
                        id, paper_id, location_type, is_oa, oa_status, landing_page_url, pdf_url, local_pdf_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        paper_id = excluded.paper_id,
                        location_type = excluded.location_type,
                        is_oa = excluded.is_oa,
                        oa_status = excluded.oa_status,
                        landing_page_url = excluded.landing_page_url,
                        pdf_url = excluded.pdf_url,
                        local_pdf_path = excluded.local_pdf_path
                    """,
                    (
                        loc.id,
                        paper.id,
                        loc.location_type,
                        int(loc.is_oa),
                        loc.oa_status,
                        loc.landing_page_url,
                        loc.pdf_url,
                        loc.local_pdf_path,
                    ),
                )

    def save_citation(self, citation: CitationRecord) -> None:
        """
        Persist a directed citation edge between two papers.
        Ensures foreign key requirements are satisfied.
        """
        with self.transaction():
            cursor = self.conn.cursor()
            # Ensure stub paper records exist to satisfy foreign key constraints
            cursor.execute(
                "INSERT OR IGNORE INTO papers (id, title) VALUES (?, ?)",
                (citation.source_paper_id, citation.source_paper_id),
            )
            cursor.execute(
                "INSERT OR IGNORE INTO papers (id, title) VALUES (?, ?)",
                (citation.target_paper_id, citation.target_paper_id),
            )
            cursor.execute(
                """
                INSERT INTO citations (source_paper_id, target_paper_id, is_influential, context)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_paper_id, target_paper_id) DO UPDATE SET
                    is_influential = excluded.is_influential,
                    context = coalesce(excluded.context, citations.context)
                """,
                (
                    citation.source_paper_id,
                    citation.target_paper_id,
                    int(citation.is_influential),
                    citation.context,
                ),
            )

    def get_graph_papers(self, graph_id: str) -> list[PaperRecord]:
        """
        Retrieve all papers belonging to a given graph session, rehydrating their
        authors, identifiers, versions, and locations.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT p.id, p.title, p.year, p.publication_date, p.citation_count,
                       p.influential_citation_count, p.recent_citation_growth,
                       p.is_retracted, p.abstract
                FROM papers p
                JOIN graph_papers gp ON p.id = gp.paper_id
                WHERE gp.graph_id = ?
                ORDER BY gp.topological_depth ASC, p.year ASC, p.id ASC
                """,
                (graph_id,),
            )
            rows = cursor.fetchall()
            return [self._rehydrate_paper(row, cursor) for row in rows]

    def get_paper(self, paper_id: str) -> Optional[PaperRecord]:
        """
        Retrieve a single canonical paper record by ID.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT id, title, year, publication_date, citation_count,
                       influential_citation_count, recent_citation_growth,
                       is_retracted, abstract
                FROM papers
                WHERE id = ?
                """,
                (paper_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._rehydrate_paper(row, cursor)

    def _rehydrate_paper(self, row: tuple[Any, ...], cursor: sqlite3.Cursor) -> PaperRecord:
        """Internal helper to construct a PaperRecord from database rows."""
        paper_id = row[0]

        # Authors
        cursor.execute(
            """
            SELECT a.id, a.name, a.orcid, a.email, a.institution
            FROM authors a
            JOIN paper_authors pa ON a.id = pa.author_id
            WHERE pa.paper_id = ?
            ORDER BY pa.author_position ASC
            """,
            (paper_id,),
        )
        authors = [
            AuthorRecord(id=r[0], name=r[1], orcid=r[2], email=r[3], institution=r[4])
            for r in cursor.fetchall()
        ]

        # Identifiers
        cursor.execute(
            """
            SELECT paper_id, provider, external_id, is_canonical
            FROM paper_identifiers
            WHERE paper_id = ?
            ORDER BY is_canonical DESC, provider ASC
            """,
            (paper_id,),
        )
        identifiers = [
            PaperIdentifierRecord(
                paper_id=r[0], provider=r[1], external_id=r[2], is_canonical=bool(r[3])
            )
            for r in cursor.fetchall()
        ]

        # Versions
        cursor.execute(
            """
            SELECT id, paper_id, version_type, version_label, doi, release_date
            FROM paper_versions
            WHERE paper_id = ?
            ORDER BY release_date ASC
            """,
            (paper_id,),
        )
        versions = [
            PaperVersionRecord(
                id=r[0],
                paper_id=r[1],
                version_type=r[2],
                version_label=r[3],
                doi=r[4],
                release_date=r[5],
            )
            for r in cursor.fetchall()
        ]

        # Locations
        cursor.execute(
            """
            SELECT id, paper_id, location_type, is_oa, oa_status, landing_page_url, pdf_url, local_pdf_path
            FROM paper_locations
            WHERE paper_id = ?
            """,
            (paper_id,),
        )
        locations = [
            PaperLocationRecord(
                id=r[0],
                paper_id=r[1],
                location_type=r[2],
                is_oa=bool(r[3]),
                oa_status=r[4],
                landing_page_url=r[5],
                pdf_url=r[6],
                local_pdf_path=r[7],
            )
            for r in cursor.fetchall()
        ]

        return PaperRecord(
            id=row[0],
            title=row[1],
            year=row[2],
            publication_date=row[3],
            citation_count=row[4] or 0,
            influential_citation_count=row[5] or 0,
            recent_citation_growth=row[6] or 0.0,
            is_retracted=bool(row[7]),
            abstract=row[8],
            authors=authors,
            identifiers=identifiers,
            versions=versions,
            locations=locations,
        )

    def get_graph_citations(self, graph_id: str) -> list[CitationRecord]:
        """
        Retrieve all citation links connecting papers within the given graph session.
        Maintains strict graph isolation by ensuring both endpoints belong to the session.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT c.source_paper_id, c.target_paper_id, c.is_influential, c.context
                FROM citations c
                JOIN graph_papers gp_src ON c.source_paper_id = gp_src.paper_id AND gp_src.graph_id = ?
                JOIN graph_papers gp_tgt ON c.target_paper_id = gp_tgt.paper_id AND gp_tgt.graph_id = ?
                ORDER BY c.source_paper_id, c.target_paper_id
                """,
                (graph_id, graph_id),
            )
            rows = cursor.fetchall()
            return [
                CitationRecord(
                    source_paper_id=row[0],
                    target_paper_id=row[1],
                    is_influential=bool(row[2]),
                    context=row[3],
                )
                for row in rows
            ]

    def execute_read_query(self, query_sql: str) -> list[dict[str, Any]]:
        """
        Execute a read-only SQL query against the knowledge store.
        Strictly permits only SELECT / READ operations using SQLite's authorizer callback.
        Raises PermissionError if any mutation (INSERT, UPDATE, DELETE, DROP, ALTER, etc.) is attempted.
        """
        with self._lock:
            def authorizer_callback(
                action: int,
                arg1: Optional[str],
                arg2: Optional[str],
                dbname: Optional[str],
                source: Optional[str],
            ) -> int:
                allowed = (
                    sqlite3.SQLITE_SELECT,
                    sqlite3.SQLITE_READ,
                    getattr(sqlite3, "SQLITE_FUNCTION", 31),
                )
                if action in allowed:
                    return sqlite3.SQLITE_OK
                return sqlite3.SQLITE_DENY

            self.conn.set_authorizer(authorizer_callback)
            try:
                cursor = self.conn.cursor()
                cursor.execute(query_sql)
                if not cursor.description:
                    return []
                cols = [desc[0] for desc in cursor.description]
                return [dict(zip(cols, row)) for row in cursor.fetchall()]
            except (sqlite3.DatabaseError, sqlite3.ProgrammingError) as e:
                err_str = str(e).lower()
                if "not authorized" in err_str or "one statement at a time" in err_str:
                    raise PermissionError(f"Query not permitted in read-only mode: {e}") from e
                raise
            finally:
                self.conn.set_authorizer(None)

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            self.conn.close()

    def __enter__(self) -> LiteratureStore:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


__all__ = ["LiteratureStore", "SCHEMA_SQL"]
