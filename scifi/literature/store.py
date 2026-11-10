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

import uuid

DEFAULT_CENTRAL_STORE_PATH: Path = Path.home() / ".scifi" / "literature_store.db"
from scifi.literature.models import (
    AuthorRecord,
    BenchmarkRecord,
    BenchmarkResultRecord,
    CitationContextRecord,
    CitationRecord,
    EvaluationConditionRecord,
    EvaluationMetricRecord,
    EvidenceRecord,
    GraphSessionRecord,
    PaperGapRecord,
    PaperIdentifierRecord,
    PaperLocationRecord,
    PaperRecord,
    PaperVersionRecord,
    ProjectRecord,
    ReprintRequestRecord,
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
    venue_name TEXT,
    venue_tier TEXT,
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
    domain TEXT,
    canonical_url TEXT,
    description TEXT,
    created_at TEXT DEFAULT (datetime('now', 'utc'))
);

CREATE TABLE IF NOT EXISTS evaluation_metrics (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    goal TEXT NOT NULL DEFAULT 'maximize',
    unit TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS evaluation_conditions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    dataset_split TEXT DEFAULT 'test',
    hardware TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS benchmark_results (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    benchmark_id TEXT NOT NULL REFERENCES benchmarks(id) ON DELETE CASCADE,
    metric_id TEXT NOT NULL REFERENCES evaluation_metrics(id) ON DELETE CASCADE,
    condition_id TEXT REFERENCES evaluation_conditions(id) ON DELETE SET NULL,
    metric_value REAL NOT NULL,
    is_sota INTEGER DEFAULT 0,
    rank INTEGER,
    evidence_id TEXT REFERENCES evidence(id) ON DELETE SET NULL,
    table_or_figure TEXT,
    result_date TEXT,
    provenance_source TEXT DEFAULT 'author_reported',
    created_at TEXT DEFAULT (datetime('now', 'utc'))
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_graph_papers_paper_id ON graph_papers(paper_id);
CREATE INDEX IF NOT EXISTS idx_citations_target ON citations(target_paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_identifiers_paper ON paper_identifiers(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_authors_paper ON paper_authors(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_versions_paper ON paper_versions(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_locations_paper ON paper_locations(paper_id);
CREATE INDEX IF NOT EXISTS idx_bench_results_paper ON benchmark_results(paper_id);
CREATE INDEX IF NOT EXISTS idx_bench_results_bench ON benchmark_results(benchmark_id);
CREATE INDEX IF NOT EXISTS idx_bench_results_sota ON benchmark_results(benchmark_id, metric_id, is_sota);

-- 14. Global Projects Registry
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    workspace_path TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 15. Project-Paper Scoping Junction
CREATE TABLE IF NOT EXISTS project_papers (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    graph_id TEXT REFERENCES graphs(id) ON DELETE SET NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    PRIMARY KEY (project_id, paper_id)
);

-- 16. Author Reprint Outreach Registry
CREATE TABLE IF NOT EXISTS reprint_requests (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    author_name TEXT NOT NULL,
    author_email TEXT,
    author_affiliation TEXT,
    status TEXT NOT NULL DEFAULT 'DRAFT_READY',
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    mailto_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reprint_status ON reprint_requests(status);
CREATE INDEX IF NOT EXISTS idx_reprint_project ON reprint_requests(project_id);
CREATE INDEX IF NOT EXISTS idx_reprint_paper ON reprint_requests(paper_id);
CREATE INDEX IF NOT EXISTS idx_project_papers_proj ON project_papers(project_id);
CREATE INDEX IF NOT EXISTS idx_project_papers_paper ON project_papers(paper_id);
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
        self.write_lock = self._lock
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
            # Upgrade legacy prototype benchmarks/benchmark_results tables if present
            cursor = self.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='benchmarks'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(benchmarks)")
                cols = {row[1] for row in cursor.fetchall()}
                if "canonical_url" not in cols:
                    self.conn.execute("DROP TABLE IF EXISTS benchmark_results")
                    self.conn.execute("DROP TABLE IF EXISTS benchmarks")
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='papers'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(papers)")
                pcols = {row[1] for row in cursor.fetchall()}
                if "venue_name" not in pcols:
                    self.conn.execute("ALTER TABLE papers ADD COLUMN venue_name TEXT")
                if "venue_tier" not in pcols:
                    self.conn.execute("ALTER TABLE papers ADD COLUMN venue_tier TEXT")
            self.conn.executescript(SCHEMA_SQL)

    _init_schema = _init_db

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

    def _upsert_paper_records(self, cursor: sqlite3.Cursor, paper: PaperRecord) -> None:
        """Internal helper to upsert paper and related sub-records."""
        cursor.execute(
            """
            INSERT INTO papers (
                id, title, year, publication_date, citation_count,
                influential_citation_count, recent_citation_growth,
                is_retracted, abstract, venue_name, venue_tier
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                year = coalesce(excluded.year, papers.year),
                publication_date = coalesce(excluded.publication_date, papers.publication_date),
                citation_count = excluded.citation_count,
                influential_citation_count = excluded.influential_citation_count,
                recent_citation_growth = excluded.recent_citation_growth,
                is_retracted = excluded.is_retracted,
                abstract = coalesce(excluded.abstract, papers.abstract),
                venue_name = coalesce(excluded.venue_name, papers.venue_name),
                venue_tier = coalesce(excluded.venue_tier, papers.venue_tier)
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
                paper.venue_name,
                paper.venue_tier,
            ),
        )

        # Save authors and paper_authors junction
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

        # Save external identifiers
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

        # Save versions
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

        # Save document locations
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

    def upsert_paper(self, paper: PaperRecord) -> None:
        """
        Persist or update a canonical paper record and its sub-entities (authors,
        identifiers, versions, locations) without requiring a graph session association.
        """
        with self.transaction():
            cursor = self.conn.cursor()
            self._upsert_paper_records(cursor, paper)

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
            self._upsert_paper_records(cursor, paper)

            # Ensure graph exists
            cursor.execute(
                "INSERT OR IGNORE INTO graphs (id, title) VALUES (?, ?)",
                (graph_id, graph_id),
            )

            # Associate paper with graph session
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

    def save_paper_location(self, location: PaperLocationRecord) -> None:
        """
        Persist or update a document location (e.g. local PDF path or OA URL).
        """
        with self.transaction():
            cursor = self.conn.cursor()
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
                    location.id,
                    location.paper_id,
                    location.location_type,
                    int(location.is_oa),
                    location.oa_status,
                    location.landing_page_url,
                    location.pdf_url,
                    location.local_pdf_path,
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
                       p.is_retracted, p.abstract, p.venue_name, p.venue_tier
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
                       is_retracted, abstract, venue_name, venue_tier
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
            venue_name=row[9] if len(row) > 9 else None,
            venue_tier=row[10] if len(row) > 10 else None,
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

    def save_citation_context(self, context: CitationContextRecord) -> None:
        """
        Persist an in-text citation context record between two papers.
        Ensures foreign key requirements are satisfied and uses upsert semantics.
        """
        with self.transaction():
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO papers (id, title) VALUES (?, ?)",
                (context.source_paper_id, context.source_paper_id),
            )
            cursor.execute(
                "INSERT OR IGNORE INTO papers (id, title) VALUES (?, ?)",
                (context.target_paper_id, context.target_paper_id),
            )
            cursor.execute(
                """
                INSERT INTO citation_contexts (
                    id, source_paper_id, target_paper_id, context_text,
                    section_name, intent, is_influential
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source_paper_id = excluded.source_paper_id,
                    target_paper_id = excluded.target_paper_id,
                    context_text = excluded.context_text,
                    section_name = excluded.section_name,
                    intent = excluded.intent,
                    is_influential = excluded.is_influential
                """,
                (
                    context.id,
                    context.source_paper_id,
                    context.target_paper_id,
                    context.context_text,
                    context.section_name,
                    context.intent,
                    int(context.is_influential),
                ),
            )

    def save_evidence(self, evidence: EvidenceRecord) -> None:
        """
        Persist an extracted evidence record into the evidence provenance registry.
        Ensures foreign key requirements are satisfied and uses upsert semantics.
        """
        with self.transaction():
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO papers (id, title) VALUES (?, ?)",
                (evidence.paper_id, evidence.paper_id),
            )
            if evidence.reporting_paper_id:
                cursor.execute(
                    "INSERT OR IGNORE INTO papers (id, title) VALUES (?, ?)",
                    (evidence.reporting_paper_id, evidence.reporting_paper_id),
                )
            if evidence.retrieved_at is not None:
                cursor.execute(
                    """
                    INSERT INTO evidence (
                        id, paper_id, reporting_paper_id, evidence_type,
                        source_section, source_location, extracted_text,
                        extraction_method, confidence, retrieved_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        paper_id = excluded.paper_id,
                        reporting_paper_id = excluded.reporting_paper_id,
                        evidence_type = excluded.evidence_type,
                        source_section = excluded.source_section,
                        source_location = excluded.source_location,
                        extracted_text = excluded.extracted_text,
                        extraction_method = excluded.extraction_method,
                        confidence = excluded.confidence,
                        retrieved_at = excluded.retrieved_at
                    """,
                    (
                        evidence.id,
                        evidence.paper_id,
                        evidence.reporting_paper_id,
                        evidence.evidence_type,
                        evidence.source_section,
                        evidence.source_location,
                        evidence.extracted_text,
                        evidence.extraction_method,
                        evidence.confidence,
                        evidence.retrieved_at,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO evidence (
                        id, paper_id, reporting_paper_id, evidence_type,
                        source_section, source_location, extracted_text,
                        extraction_method, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        paper_id = excluded.paper_id,
                        reporting_paper_id = excluded.reporting_paper_id,
                        evidence_type = excluded.evidence_type,
                        source_section = excluded.source_section,
                        source_location = excluded.source_location,
                        extracted_text = excluded.extracted_text,
                        extraction_method = excluded.extraction_method,
                        confidence = excluded.confidence
                    """,
                    (
                        evidence.id,
                        evidence.paper_id,
                        evidence.reporting_paper_id,
                        evidence.evidence_type,
                        evidence.source_section,
                        evidence.source_location,
                        evidence.extracted_text,
                        evidence.extraction_method,
                        evidence.confidence,
                    ),
                )

    def save_paper_gap(self, gap: PaperGapRecord) -> None:
        """
        Persist a candidate or corroborated research gap record.
        Ensures foreign key requirements are satisfied and uses upsert semantics.
        """
        with self.transaction():
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO papers (id, title) VALUES (?, ?)",
                (gap.paper_id, gap.paper_id),
            )
            cursor.execute(
                """
                INSERT INTO paper_gaps (
                    id, paper_id, gap_type, claim_summary,
                    primary_evidence_id, verification_status,
                    corroborating_count, contradicting_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    paper_id = excluded.paper_id,
                    gap_type = excluded.gap_type,
                    claim_summary = excluded.claim_summary,
                    primary_evidence_id = excluded.primary_evidence_id,
                    verification_status = excluded.verification_status,
                    corroborating_count = excluded.corroborating_count,
                    contradicting_count = excluded.contradicting_count
                """,
                (
                    gap.id,
                    gap.paper_id,
                    gap.gap_type,
                    gap.claim_summary,
                    gap.primary_evidence_id,
                    gap.verification_status,
                    gap.corroborating_count,
                    gap.contradicting_count,
                ),
            )

    def save_benchmark(self, benchmark: BenchmarkRecord) -> None:
        """
        Persist a benchmark dataset or suite record using upsert semantics.
        """
        with self.transaction():
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO benchmarks (id, name, domain, canonical_url, description)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    domain = coalesce(excluded.domain, benchmarks.domain),
                    canonical_url = coalesce(excluded.canonical_url, benchmarks.canonical_url),
                    description = coalesce(excluded.description, benchmarks.description)
                """,
                (
                    benchmark.id,
                    benchmark.name,
                    benchmark.domain,
                    benchmark.canonical_url,
                    benchmark.description,
                ),
            )

    def save_evaluation_metric(self, metric: EvaluationMetricRecord) -> None:
        """
        Persist an evaluation metric definition using upsert semantics.
        """
        with self.transaction():
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO evaluation_metrics (id, name, goal, unit, description)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    goal = excluded.goal,
                    unit = coalesce(excluded.unit, evaluation_metrics.unit),
                    description = coalesce(excluded.description, evaluation_metrics.description)
                """,
                (
                    metric.id,
                    metric.name,
                    metric.goal,
                    metric.unit,
                    metric.description,
                ),
            )

    def save_evaluation_condition(self, condition: EvaluationConditionRecord) -> None:
        """
        Persist an evaluation condition/protocol record using upsert semantics.
        """
        with self.transaction():
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO evaluation_conditions (id, name, dataset_split, hardware, notes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    dataset_split = coalesce(excluded.dataset_split, evaluation_conditions.dataset_split),
                    hardware = coalesce(excluded.hardware, evaluation_conditions.hardware),
                    notes = coalesce(excluded.notes, evaluation_conditions.notes)
                """,
                (
                    condition.id,
                    condition.name,
                    condition.dataset_split,
                    condition.hardware,
                    condition.notes,
                ),
            )

    def save_benchmark_result(self, result: BenchmarkResultRecord) -> None:
        """
        Persist an individual benchmark score/result with full provenance and upsert semantics.
        Ensures foreign key dependencies are satisfied.
        """
        with self.transaction():
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO papers (id, title) VALUES (?, ?)",
                (result.paper_id, result.paper_id),
            )
            cursor.execute(
                "INSERT OR IGNORE INTO benchmarks (id, name) VALUES (?, ?)",
                (result.benchmark_id, result.benchmark_id),
            )
            cursor.execute(
                "INSERT OR IGNORE INTO evaluation_metrics (id, name) VALUES (?, ?)",
                (result.metric_id, result.metric_id),
            )
            if result.condition_id:
                cursor.execute(
                    "INSERT OR IGNORE INTO evaluation_conditions (id, name) VALUES (?, ?)",
                    (result.condition_id, result.condition_id),
                )
            cursor.execute(
                """
                INSERT INTO benchmark_results (
                    id, paper_id, benchmark_id, metric_id, condition_id,
                    metric_value, is_sota, rank, evidence_id, table_or_figure,
                    result_date, provenance_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    paper_id = excluded.paper_id,
                    benchmark_id = excluded.benchmark_id,
                    metric_id = excluded.metric_id,
                    condition_id = excluded.condition_id,
                    metric_value = excluded.metric_value,
                    is_sota = excluded.is_sota,
                    rank = excluded.rank,
                    evidence_id = excluded.evidence_id,
                    table_or_figure = excluded.table_or_figure,
                    result_date = excluded.result_date,
                    provenance_source = excluded.provenance_source
                """,
                (
                    result.id,
                    result.paper_id,
                    result.benchmark_id,
                    result.metric_id,
                    result.condition_id,
                    result.metric_value,
                    int(result.is_sota),
                    result.rank,
                    result.evidence_id,
                    result.table_or_figure,
                    result.result_date,
                    result.provenance_source,
                ),
            )

    def get_paper_evidence(self, paper_id: str) -> list[EvidenceRecord]:
        """
        Retrieve all evidence records associated with a given paper ID.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT id, paper_id, reporting_paper_id, evidence_type,
                       source_section, source_location, extracted_text,
                       extraction_method, confidence, retrieved_at
                FROM evidence
                WHERE paper_id = ?
                ORDER BY retrieved_at ASC, id ASC
                """,
                (paper_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_evidence(r) for r in rows]

    def get_paper_gaps(self, paper_id: str) -> list[PaperGapRecord]:
        """
        Retrieve all candidate and corroborated research gaps for a given paper ID.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT id, paper_id, gap_type, claim_summary,
                       primary_evidence_id, verification_status,
                       corroborating_count, contradicting_count
                FROM paper_gaps
                WHERE paper_id = ?
                ORDER BY id ASC
                """,
                (paper_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_gap(r) for r in rows]

    def get_citation_contexts(
        self, source_id: str, target_id: str
    ) -> list[CitationContextRecord]:
        """
        Retrieve granular in-text citation contexts between source and target papers.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT id, source_paper_id, target_paper_id, context_text,
                   section_name, intent, is_influential
                FROM citation_contexts
                WHERE source_paper_id = ? AND target_paper_id = ?
                ORDER BY id ASC
                """,
                (source_id, target_id),
            )
            rows = cursor.fetchall()
            return [self._row_to_citation_context(r) for r in rows]

    def get_graph_gaps(self, graph_id: str) -> dict[str, list[PaperGapRecord]]:
        """
        Retrieve all research gaps whose paper_id belongs to the specified graph session,
        grouped by paper_id.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT pg.id, pg.paper_id, pg.gap_type, pg.claim_summary,
                       pg.primary_evidence_id, pg.verification_status,
                       pg.corroborating_count, pg.contradicting_count
                FROM paper_gaps pg
                JOIN graph_papers gp ON pg.paper_id = gp.paper_id
                WHERE gp.graph_id = ?
                ORDER BY pg.paper_id ASC, pg.id ASC
                """,
                (graph_id,),
            )
            rows = cursor.fetchall()
            gaps_by_paper: dict[str, list[PaperGapRecord]] = {}
            for r in rows:
                gap = self._row_to_gap(r)
                gaps_by_paper.setdefault(gap.paper_id, []).append(gap)
            return gaps_by_paper

    def get_graph_evidence(self, graph_id: str) -> dict[str, EvidenceRecord]:
        """
        Retrieve all evidence records referenced by gaps or papers in the given graph session
        as an {id: EvidenceRecord} dictionary.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT e.id, e.paper_id, e.reporting_paper_id, e.evidence_type,
                       e.source_section, e.source_location, e.extracted_text,
                       e.extraction_method, e.confidence, e.retrieved_at
                FROM evidence e
                WHERE e.paper_id IN (SELECT paper_id FROM graph_papers WHERE graph_id = ?)
                   OR e.reporting_paper_id IN (SELECT paper_id FROM graph_papers WHERE graph_id = ?)
                   OR e.id IN (
                       SELECT pg.primary_evidence_id
                       FROM paper_gaps pg
                       JOIN graph_papers gp ON pg.paper_id = gp.paper_id
                       WHERE gp.graph_id = ?
                   )
                ORDER BY e.retrieved_at ASC, e.id ASC
                """,
                (graph_id, graph_id, graph_id),
            )
            rows = cursor.fetchall()
            return {r[0]: self._row_to_evidence(r) for r in rows}

    @staticmethod
    def _row_to_evidence(row: tuple[Any, ...]) -> EvidenceRecord:
        return EvidenceRecord(
            id=row[0],
            paper_id=row[1],
            reporting_paper_id=row[2],
            evidence_type=row[3],
            source_section=row[4],
            source_location=row[5],
            extracted_text=row[6],
            extraction_method=row[7],
            confidence=float(row[8]) if row[8] is not None else None,
            retrieved_at=str(row[9]) if row[9] is not None else None,
        )

    @staticmethod
    def _row_to_gap(row: tuple[Any, ...]) -> PaperGapRecord:
        return PaperGapRecord(
            id=row[0],
            paper_id=row[1],
            gap_type=row[2],
            claim_summary=row[3],
            primary_evidence_id=row[4],
            verification_status=row[5],
            corroborating_count=row[6] or 0,
            contradicting_count=row[7] or 0,
        )

    @staticmethod
    def _row_to_citation_context(row: tuple[Any, ...]) -> CitationContextRecord:
        return CitationContextRecord(
            id=row[0],
            source_paper_id=row[1],
            target_paper_id=row[2],
            context_text=row[3],
            section_name=row[4],
            intent=row[5],
            is_influential=bool(row[6]),
        )

    def get_paper_benchmark_results(self, paper_id: str) -> list[BenchmarkResultRecord]:
        """
        Retrieve all benchmark results associated with a given paper ID,
        ordered by metric_value DESC.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT id, paper_id, benchmark_id, metric_id, condition_id,
                       metric_value, is_sota, rank, evidence_id, table_or_figure,
                       result_date, provenance_source
                FROM benchmark_results
                WHERE paper_id = ?
                ORDER BY metric_value DESC, id ASC
                """,
                (paper_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_benchmark_result(r) for r in rows]

    def get_graph_benchmark_results(
        self, graph_id: str
    ) -> dict[str, list[BenchmarkResultRecord]]:
        """
        Retrieve all benchmark results for papers belonging to the specified graph session,
        grouped by paper_id.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT br.id, br.paper_id, br.benchmark_id, br.metric_id, br.condition_id,
                       br.metric_value, br.is_sota, br.rank, br.evidence_id, br.table_or_figure,
                       br.result_date, br.provenance_source
                FROM benchmark_results br
                JOIN graph_papers gp ON br.paper_id = gp.paper_id
                WHERE gp.graph_id = ?
                ORDER BY br.paper_id ASC, br.metric_value DESC, br.id ASC
                """,
                (graph_id,),
            )
            rows = cursor.fetchall()
            results_by_paper: dict[str, list[BenchmarkResultRecord]] = {}
            for r in rows:
                result = self._row_to_benchmark_result(r)
                results_by_paper.setdefault(result.paper_id, []).append(result)
            return results_by_paper

    def get_graph_benchmarks(self, graph_id: str) -> dict[str, BenchmarkRecord]:
        """
        Retrieve all benchmarks referenced by results for papers in the given graph session
        as a {benchmark_id: BenchmarkRecord} mapping.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT b.id, b.name, b.domain, b.canonical_url, b.description
                FROM benchmarks b
                JOIN benchmark_results br ON b.id = br.benchmark_id
                JOIN graph_papers gp ON br.paper_id = gp.paper_id
                WHERE gp.graph_id = ?
                ORDER BY b.name ASC, b.id ASC
                """,
                (graph_id,),
            )
            rows = cursor.fetchall()
            return {r[0]: self._row_to_benchmark(r) for r in rows}

    def get_graph_metrics(self, graph_id: str) -> dict[str, EvaluationMetricRecord]:
        """
        Retrieve all evaluation metrics referenced by results for papers in the given graph session
        as a {metric_id: EvaluationMetricRecord} mapping.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT m.id, m.name, m.goal, m.unit, m.description
                FROM evaluation_metrics m
                JOIN benchmark_results br ON m.id = br.metric_id
                JOIN graph_papers gp ON br.paper_id = gp.paper_id
                WHERE gp.graph_id = ?
                ORDER BY m.name ASC, m.id ASC
                """,
                (graph_id,),
            )
            rows = cursor.fetchall()
            return {r[0]: self._row_to_metric(r) for r in rows}

    def get_graph_conditions(self, graph_id: str) -> dict[str, EvaluationConditionRecord]:
        """
        Retrieve all evaluation conditions referenced by results for papers in the given graph session
        as a {condition_id: EvaluationConditionRecord} mapping.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT c.id, c.name, c.dataset_split, c.hardware, c.notes
                FROM evaluation_conditions c
                JOIN benchmark_results br ON c.id = br.condition_id
                JOIN graph_papers gp ON br.paper_id = gp.paper_id
                WHERE gp.graph_id = ?
                ORDER BY c.name ASC, c.id ASC
                """,
                (graph_id,),
            )
            rows = cursor.fetchall()
            return {r[0]: self._row_to_condition(r) for r in rows}

    def get_sota_leaders(
        self, benchmark_id: str, metric_id: str
    ) -> list[BenchmarkResultRecord]:
        """
        Retrieve all benchmark results marked as is_sota = 1 for the specified benchmark and metric.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT br.id, br.paper_id, br.benchmark_id, br.metric_id, br.condition_id,
                       br.metric_value, br.is_sota, br.rank, br.evidence_id, br.table_or_figure,
                       br.result_date, br.provenance_source
                FROM benchmark_results br
                LEFT JOIN evaluation_metrics m ON br.metric_id = m.id
                WHERE br.benchmark_id = ? AND br.metric_id = ? AND br.is_sota = 1
                ORDER BY
                    CASE WHEN m.goal = 'minimize' THEN br.metric_value END ASC,
                    CASE WHEN m.goal != 'minimize' OR m.goal IS NULL THEN br.metric_value END DESC,
                    br.id ASC
                """,
                (benchmark_id, metric_id),
            )
            rows = cursor.fetchall()
            return [self._row_to_benchmark_result(r) for r in rows]

    @staticmethod
    def _row_to_benchmark(row: tuple[Any, ...]) -> BenchmarkRecord:
        return BenchmarkRecord(
            id=row[0],
            name=row[1],
            domain=row[2] if row[2] is not None else "",
            canonical_url=row[3],
            description=row[4],
        )

    @staticmethod
    def _row_to_metric(row: tuple[Any, ...]) -> EvaluationMetricRecord:
        return EvaluationMetricRecord(
            id=row[0],
            name=row[1],
            goal=row[2] or "maximize",
            unit=row[3],
            description=row[4],
        )

    @staticmethod
    def _row_to_condition(row: tuple[Any, ...]) -> EvaluationConditionRecord:
        return EvaluationConditionRecord(
            id=row[0],
            name=row[1],
            dataset_split=row[2] if row[2] is not None else "test",
            hardware=row[3],
            notes=row[4],
        )

    @staticmethod
    def _row_to_benchmark_result(row: tuple[Any, ...]) -> BenchmarkResultRecord:
        return BenchmarkResultRecord(
            id=row[0],
            paper_id=row[1],
            benchmark_id=row[2],
            metric_id=row[3],
            condition_id=row[4],
            metric_value=float(row[5]) if row[5] is not None else 0.0,
            is_sota=bool(row[6]),
            rank=int(row[7]) if row[7] is not None else None,
            evidence_id=row[8],
            table_or_figure=row[9],
            result_date=str(row[10]) if row[10] is not None else None,
            provenance_source=row[11] if row[11] is not None else "author_reported",
        )

    def add_citations(self, citations: list[CitationRecord]) -> None:
        """Batch persist multiple citation records."""
        with self.transaction():
            for cit in citations:
                self.save_citation(cit)

    def get_paper_citations(self, paper_id: str) -> list[CitationRecord]:
        """Retrieve all outgoing citation records originating from a given paper."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT source_paper_id, target_paper_id, is_influential, context
                FROM citations
                WHERE source_paper_id = ?
                """,
                (paper_id,),
            )
            rows = cursor.fetchall()
            return [
                CitationRecord(
                    source_paper_id=r[0],
                    target_paper_id=r[1],
                    is_influential=bool(r[2]),
                    context=r[3],
                )
                for r in rows
            ]

    def get_paper_locations(self, paper_id: str) -> list[PaperLocationRecord]:
        """Retrieve all recorded document locations for a given paper."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT id, paper_id, location_type, is_oa, oa_status, landing_page_url, pdf_url, local_pdf_path
                FROM paper_locations
                WHERE paper_id = ?
                """,
                (paper_id,),
            )
            rows = cursor.fetchall()
            return [
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
                for r in rows
            ]

    def register_project(
        self,
        name: str,
        workspace_path: str | Path,
        description: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> ProjectRecord:
        """
        Register a new project workspace or update an existing project record
        matched by canonical workspace path.
        """
        norm_path = str(Path(workspace_path).resolve())
        with self.transaction():
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT id, name, workspace_path, description, created_at, updated_at FROM projects WHERE workspace_path = ?",
                (norm_path,),
            )
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    """
                    UPDATE projects
                    SET name = ?, description = coalesce(?, description), updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (name, description, row[0]),
                )
                cursor.execute(
                    "SELECT id, name, workspace_path, description, created_at, updated_at FROM projects WHERE id = ?",
                    (row[0],),
                )
                return ProjectRecord.from_row(cursor.fetchone())

            pid = project_id or f"proj-{uuid.uuid4().hex[:12]}"
            cursor.execute(
                """
                INSERT INTO projects (id, name, workspace_path, description)
                VALUES (?, ?, ?, ?)
                """,
                (pid, name, norm_path, description),
            )
            cursor.execute(
                "SELECT id, name, workspace_path, description, created_at, updated_at FROM projects WHERE id = ?",
                (pid,),
            )
            return ProjectRecord.from_row(cursor.fetchone())

    def list_projects(self) -> list[ProjectRecord]:
        """List all registered projects ordered by creation date."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT id, name, workspace_path, description, created_at, updated_at FROM projects ORDER BY created_at DESC"
            )
            return [ProjectRecord.from_row(r) for r in cursor.fetchall()]

    def get_project(self, project_id: str) -> Optional[ProjectRecord]:
        """Retrieve a registered project by its identifier."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT id, name, workspace_path, description, created_at, updated_at FROM projects WHERE id = ?",
                (project_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return ProjectRecord.from_row(row)

    def get_project_by_workspace(self, workspace_path: str | Path) -> Optional[ProjectRecord]:
        """Retrieve a registered project by its workspace path."""
        norm_path = str(Path(workspace_path).resolve())
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT id, name, workspace_path, description, created_at, updated_at FROM projects WHERE workspace_path = ?",
                (norm_path,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return ProjectRecord.from_row(row)

    def link_paper_to_project(
        self,
        project_id: str,
        paper_id: str,
        graph_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> None:
        """Associate a paper with a registered project."""
        with self.transaction():
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO papers (id, title) VALUES (?, ?)",
                (paper_id, paper_id),
            )
            cursor.execute(
                """
                INSERT INTO project_papers (project_id, paper_id, graph_id, notes)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id, paper_id) DO UPDATE SET
                    graph_id = coalesce(excluded.graph_id, project_papers.graph_id),
                    notes = coalesce(excluded.notes, project_papers.notes)
                """,
                (project_id, paper_id, graph_id, notes),
            )

    def get_project_papers(self, project_id: str) -> list[PaperRecord]:
        """
        Retrieve all papers linked to a project, fully rehydrating sub-entities.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT p.id, p.title, p.year, p.publication_date, p.citation_count,
                       p.influential_citation_count, p.recent_citation_growth,
                       p.is_retracted, p.abstract, p.venue_name, p.venue_tier
                FROM papers p
                JOIN project_papers pp ON p.id = pp.paper_id
                WHERE pp.project_id = ?
                ORDER BY pp.added_at ASC, p.year ASC, p.id ASC
                """,
                (project_id,),
            )
            rows = cursor.fetchall()
            return [self._rehydrate_paper(row, cursor) for row in rows]

    def create_reprint_request(
        self,
        project_id: Optional[str],
        paper_id: str,
        author_name: str,
        author_email: Optional[str] = None,
        author_affiliation: Optional[str] = None,
        subject: str = "",
        body: str = "",
        mailto_url: Optional[str] = None,
        status: str = "DRAFT_READY",
        request_id: Optional[str] = None,
    ) -> ReprintRequestRecord:
        """Create and persist an author reprint request draft."""
        rid = request_id or f"rep-{uuid.uuid4().hex[:12]}"
        with self.transaction():
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO papers (id, title) VALUES (?, ?)",
                (paper_id, paper_id),
            )
            cursor.execute(
                """
                INSERT INTO reprint_requests (
                    id, project_id, paper_id, author_name, author_email,
                    author_affiliation, status, subject, body, mailto_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rid,
                    project_id,
                    paper_id,
                    author_name,
                    author_email,
                    author_affiliation,
                    status,
                    subject,
                    body,
                    mailto_url,
                ),
            )
            cursor.execute(
                """
                SELECT id, project_id, paper_id, author_name, author_email,
                       author_affiliation, status, subject, body, mailto_url,
                       created_at, updated_at
                FROM reprint_requests
                WHERE id = ?
                """,
                (rid,),
            )
            return ReprintRequestRecord.from_row(cursor.fetchone())

    def get_reprint_requests(
        self,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        paper_id: Optional[str] = None,
    ) -> list[ReprintRequestRecord]:
        """
        Query reprint requests with optional filtering by project, status, or paper.
        """
        with self._lock:
            cursor = self.conn.cursor()
            query = """
                SELECT id, project_id, paper_id, author_name, author_email,
                       author_affiliation, status, subject, body, mailto_url,
                       created_at, updated_at
                FROM reprint_requests
                WHERE 1=1
            """
            params: list[Any] = []
            if project_id is not None:
                query += " AND project_id = ?"
                params.append(project_id)
            if status is not None:
                query += " AND status = ?"
                params.append(status)
            if paper_id is not None:
                query += " AND paper_id = ?"
                params.append(paper_id)
            query += " ORDER BY created_at DESC"
            cursor.execute(query, tuple(params))
            return [ReprintRequestRecord.from_row(r) for r in cursor.fetchall()]

    def get_reprint_request(self, request_id: str) -> Optional[ReprintRequestRecord]:
        """Retrieve a specific reprint request by identifier."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT id, project_id, paper_id, author_name, author_email,
                       author_affiliation, status, subject, body, mailto_url,
                       created_at, updated_at
                FROM reprint_requests
                WHERE id = ?
                """,
                (request_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return ReprintRequestRecord.from_row(row)

    def update_reprint_request(
        self,
        request_id: str,
        author_email: Optional[str] = None,
        status: Optional[str] = None,
        mailto_url: Optional[str] = None,
        subject: Optional[str] = None,
        body: Optional[str] = None,
    ) -> Optional[ReprintRequestRecord]:
        """
        Update mutable fields of a reprint request (email, status, draft contents).
        """
        with self.transaction():
            cursor = self.conn.cursor()
            updates = []
            params = []
            if author_email is not None:
                updates.append("author_email = ?")
                params.append(author_email)
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if mailto_url is not None:
                updates.append("mailto_url = ?")
                params.append(mailto_url)
            if subject is not None:
                updates.append("subject = ?")
                params.append(subject)
            if body is not None:
                updates.append("body = ?")
                params.append(body)

            if updates:
                updates.append("updated_at = CURRENT_TIMESTAMP")
                sql = f"UPDATE reprint_requests SET {', '.join(updates)} WHERE id = ?"
                params.append(request_id)
                cursor.execute(sql, tuple(params))

            cursor.execute(
                """
                SELECT id, project_id, paper_id, author_name, author_email,
                       author_affiliation, status, subject, body, mailto_url,
                       created_at, updated_at
                FROM reprint_requests
                WHERE id = ?
                """,
                (request_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return ReprintRequestRecord.from_row(row)

    def update_reprint_status(self, request_id: str, status: str) -> Optional[ReprintRequestRecord]:
        """Convenience method to transition the status of a reprint request."""
        return self.update_reprint_request(request_id, status=status)

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
