"""
Embedded Semantic Knowledge Graph for SciFi using LadybugDB.

SQLite (`scifi/literature/store.py`) remains the single system of record for
paper metadata, raw evidence quotes, and canonical entity aliases.
LadybugDB (`~/.scifi/knowledge_graph.lbdb`) serves as the derived, rebuildable
property-graph reasoning layer supporting multi-hop Cypher queries across
papers, methods, assumptions, claims, gaps, and benchmark results.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scifi.literature.models import EntityRecord, SemanticEdgeRecord
from scifi.logging import get_logger

if TYPE_CHECKING:
    from scifi.literature.store import LiteratureStore

logger = get_logger(__name__)

DEFAULT_KG_PATH: Path = Path.home() / ".scifi" / "knowledge_graph.lbdb"

_FORBIDDEN_CYPHER_RE = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|DETACH|DROP|ALTER|COPY|CALL|LOAD|INSTALL|ATTACH|EXPORT|IMPORT|REMOVE)\b",
    re.IGNORECASE,
)

KG_SCHEMA_STATEMENTS: tuple[str, ...] = (
    # Node Tables
    "CREATE NODE TABLE IF NOT EXISTS Paper("
    "id STRING, doi STRING, title STRING, year INT64, is_retracted BOOLEAN, venue_tier STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS Method("
    "id STRING, canonical_name STRING, aliases STRING, category STRING, complexity STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS Assumption("
    "id STRING, statement STRING, formal_expr STRING, scope STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS Claim(id STRING, summary STRING, claim_type STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS Gap("
    "id STRING, gap_type STRING, summary STRING, verification_status STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS Dataset(id STRING, name STRING, domain STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS Metric(id STRING, name STRING, goal STRING, unit STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS Result("
    "id STRING, metric_value DOUBLE, is_sota BOOLEAN, table_or_figure STRING, provenance_source STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE IF NOT EXISTS Evidence("
    "id STRING, paper_id STRING, evidence_type STRING, source_section STRING, "
    "extracted_text STRING, extraction_method STRING, confidence DOUBLE, PRIMARY KEY(id))",
    # Relationship Tables
    "CREATE REL TABLE IF NOT EXISTS CITES(FROM Paper TO Paper, is_influential BOOLEAN, intent STRING)",
    "CREATE REL TABLE IF NOT EXISTS PROPOSES(FROM Paper TO Method, evidence_id STRING, confidence DOUBLE)",
    "CREATE REL TABLE IF NOT EXISTS USES(FROM Paper TO Method, evidence_id STRING, confidence DOUBLE)",
    "CREATE REL TABLE IF NOT EXISTS EXTENDS(FROM Method TO Method, delta_summary STRING, evidence_id STRING, confidence DOUBLE)",
    "CREATE REL TABLE IF NOT EXISTS ASSUMES("
    "FROM Method TO Assumption, FROM Claim TO Assumption, "
    "is_implicit BOOLEAN, evidence_id STRING, confidence DOUBLE)",
    "CREATE REL TABLE IF NOT EXISTS PROVES(FROM Paper TO Claim, evidence_id STRING, confidence DOUBLE)",
    "CREATE REL TABLE IF NOT EXISTS FALSIFIES("
    "FROM Paper TO Assumption, FROM Claim TO Assumption, FROM Paper TO Claim, "
    "regime STRING, evidence_id STRING, confidence DOUBLE)",
    "CREATE REL TABLE IF NOT EXISTS CONTRADICTS(FROM Claim TO Claim, evidence_id STRING, confidence DOUBLE)",
    "CREATE REL TABLE IF NOT EXISTS REPORTS_GAP(FROM Paper TO Gap, evidence_id STRING)",
    "CREATE REL TABLE IF NOT EXISTS ADDRESSES(FROM Method TO Gap, evidence_id STRING, confidence DOUBLE)",
    "CREATE REL TABLE IF NOT EXISTS RAN(FROM Paper TO Result, FROM Method TO Result)",
    "CREATE REL TABLE IF NOT EXISTS ON_DATASET(FROM Result TO Dataset)",
    "CREATE REL TABLE IF NOT EXISTS MEASURED_BY(FROM Result TO Metric)",
)

_NODE_LABELS = ("Paper", "Method", "Assumption", "Claim", "Gap", "Dataset", "Metric", "Result", "Evidence")
_REL_LABELS = (
    "CITES",
    "PROPOSES",
    "USES",
    "EXTENDS",
    "ASSUMES",
    "PROVES",
    "FALSIFIES",
    "CONTRADICTS",
    "REPORTS_GAP",
    "ADDRESSES",
    "RAN",
    "ON_DATASET",
    "MEASURED_BY",
)


def _import_ladybug() -> Any:
    try:
        import ladybug as lb  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "ladybug is required for the SciFi Knowledge Graph. Install it with: pip install ladybug"
        ) from exc
    return lb


def _strip_cypher_string_literals(query: str) -> str:
    """Remove single- and double-quoted string literals before keyword inspection."""
    return re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"", " '' ", query)


def validate_readonly_cypher(query: str) -> None:
    """
    Enforce read-only Cypher execution.
    Raises PermissionError if any mutating, schema-altering, or I/O command is detected.
    """
    if not query or not query.strip():
        raise ValueError("Cypher query cannot be empty.")
    stripped = _strip_cypher_string_literals(query)
    match = _FORBIDDEN_CYPHER_RE.search(stripped)
    if match:
        raise PermissionError(
            f"Mutating or administrative Cypher keyword '{match.group(1).upper()}' is forbidden in read-only mode."
        )


class KnowledgeGraphStore:
    """
    LadybugDB-backed property graph for cross-paper scientific reasoning.

    Uses short-lived connections with retry/backoff to prevent Windows file-lock
    contention between CLI and MCP server processes.
    """

    def __init__(self, kg_path: str | Path = DEFAULT_KG_PATH) -> None:
        self.kg_path = Path(kg_path).resolve()
        self.kg_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self, read_only: bool = False, retries: int = 5) -> Iterator[Any]:
        lb = _import_ladybug()
        last_err: Exception | None = None
        db = None
        conn = None
        for attempt in range(retries):
            try:
                db = lb.Database(str(self.kg_path), read_only=read_only)
                conn = lb.Connection(db)
                break
            except Exception as exc:
                last_err = exc
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
                if db is not None:
                    try:
                        db.close()
                    except Exception:
                        pass
                db = None
                conn = None
                if attempt < retries - 1:
                    time.sleep(0.08 * (attempt + 1))
        if conn is None or db is None:
            raise RuntimeError(f"Failed to open LadybugDB at {self.kg_path}: {last_err}") from last_err

        try:
            yield conn
        finally:
            try:
                conn.close()
            finally:
                db.close()

    def _init_schema(self) -> None:
        with self._connect(read_only=False) as conn:
            for stmt in KG_SCHEMA_STATEMENTS:
                conn.execute(stmt)

    @staticmethod
    def _rows_to_dicts(result: Any, max_rows: int | None = None) -> list[dict[str, Any]]:
        cols = list(result.get_column_names())
        rows: list[dict[str, Any]] = []
        for idx, row in enumerate(result):
            if max_rows is not None and max_rows > 0 and idx >= max_rows:
                break
            rows.append(dict(zip(cols, row)))
        return rows

    def execute_read_query(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        max_rows: int = 100,
    ) -> list[dict[str, Any]]:
        """Execute a validated read-only Cypher query against the Knowledge Graph."""
        validate_readonly_cypher(cypher)
        with self._connect(read_only=True) as conn:
            res = conn.execute(cypher, params or {})
            return self._rows_to_dicts(res, max_rows=max_rows)

    def stats(self) -> dict[str, Any]:
        """Return node and relationship counts across all tables in the KG."""
        node_counts: dict[str, int] = {}
        rel_counts: dict[str, int] = {}
        with self._connect(read_only=True) as conn:
            for label in _NODE_LABELS:
                rows = list(conn.execute(f"MATCH (n:{label}) RETURN COUNT(n)"))
                node_counts[label] = int(rows[0][0]) if rows else 0
            for rel in _REL_LABELS:
                rows = list(conn.execute(f"MATCH ()-[r:{rel}]->() RETURN COUNT(r)"))
                rel_counts[rel] = int(rows[0][0]) if rows else 0
        return {
            "kg_path": str(self.kg_path),
            "nodes": node_counts,
            "relationships": rel_counts,
            "total_nodes": sum(node_counts.values()),
            "total_relationships": sum(rel_counts.values()),
        }

    # ── Idempotent Upserts ──────────────────────────────────────────────────

    def upsert_paper(
        self,
        paper_id: str,
        title: str,
        doi: str | None = None,
        year: int | None = None,
        is_retracted: bool = False,
        venue_tier: str | None = None,
    ) -> None:
        with self._connect(read_only=False) as conn:
            conn.execute(
                """
                MERGE (p:Paper {id: $id})
                SET p.doi = $doi,
                    p.title = $title,
                    p.year = $year,
                    p.is_retracted = $is_retracted,
                    p.venue_tier = $venue_tier
                """,
                {
                    "id": paper_id,
                    "doi": doi or "",
                    "title": title,
                    "year": int(year) if year is not None else 0,
                    "is_retracted": bool(is_retracted),
                    "venue_tier": venue_tier or "",
                },
            )

    def upsert_entity(self, entity: EntityRecord) -> None:
        """Upsert a canonical Method, Assumption, Claim, Dataset, or Metric node."""
        etype = entity.entity_type
        with self._connect(read_only=False) as conn:
            if etype == "Method":
                conn.execute(
                    """
                    MERGE (m:Method {id: $id})
                    SET m.canonical_name = $name,
                        m.aliases = $aliases,
                        m.category = $category,
                        m.complexity = $complexity
                    """,
                    {
                        "id": entity.id,
                        "name": entity.canonical_name,
                        "aliases": json.dumps(entity.aliases or []),
                        "category": entity.category or "",
                        "complexity": entity.complexity or "",
                    },
                )
            elif etype == "Assumption":
                conn.execute(
                    """
                    MERGE (a:Assumption {id: $id})
                    SET a.statement = $statement,
                        a.formal_expr = $formal_expr,
                        a.scope = $scope
                    """,
                    {
                        "id": entity.id,
                        "statement": entity.statement or entity.canonical_name,
                        "formal_expr": entity.formal_expr or "",
                        "scope": entity.scope or "",
                    },
                )
            elif etype == "Claim":
                conn.execute(
                    """
                    MERGE (c:Claim {id: $id})
                    SET c.summary = $summary,
                        c.claim_type = $claim_type
                    """,
                    {
                        "id": entity.id,
                        "summary": entity.statement or entity.canonical_name,
                        "claim_type": entity.category or "empirical",
                    },
                )
            elif etype == "Dataset":
                conn.execute(
                    """
                    MERGE (d:Dataset {id: $id})
                    SET d.name = $name,
                        d.domain = $domain
                    """,
                    {
                        "id": entity.id,
                        "name": entity.canonical_name,
                        "domain": entity.category or "",
                    },
                )
            elif etype == "Metric":
                conn.execute(
                    """
                    MERGE (m:Metric {id: $id})
                    SET m.name = $name,
                        m.goal = $goal,
                        m.unit = $unit
                    """,
                    {
                        "id": entity.id,
                        "name": entity.canonical_name,
                        "goal": entity.category or "maximize",
                        "unit": entity.scope or "",
                    },
                )
            else:
                raise ValueError(f"Unsupported KG entity_type: {etype}")

    def upsert_semantic_edge(self, edge: SemanticEdgeRecord) -> None:
        """Upsert a provenance-backed semantic relationship into LadybugDB."""
        if not edge.evidence_id:
            raise ValueError("Semantic edge requires evidence_id for provenance.")
        rel = edge.relation_type
        src_lbl = edge.source_type
        dst_lbl = edge.target_type

        with self._connect(read_only=False) as conn:
            if rel in {"PROPOSES", "USES", "PROVES", "CONTRADICTS", "ADDRESSES"}:
                conn.execute(
                    f"MATCH (s:{src_lbl} {{id: $sid}}), (t:{dst_lbl} {{id: $tid}}) "
                    f"MERGE (s)-[r:{rel}]->(t) "
                    "SET r.evidence_id = $eid, r.confidence = $conf",
                    {
                        "sid": edge.source_id,
                        "tid": edge.target_id,
                        "eid": edge.evidence_id,
                        "conf": float(edge.confidence),
                    },
                )
            elif rel == "EXTENDS":
                conn.execute(
                    f"MATCH (s:{src_lbl} {{id: $sid}}), (t:{dst_lbl} {{id: $tid}}) "
                    "MERGE (s)-[r:EXTENDS]->(t) "
                    "SET r.delta_summary = $delta, r.evidence_id = $eid, r.confidence = $conf",
                    {
                        "sid": edge.source_id,
                        "tid": edge.target_id,
                        "delta": edge.delta_summary or "",
                        "eid": edge.evidence_id,
                        "conf": float(edge.confidence),
                    },
                )
            elif rel == "ASSUMES":
                conn.execute(
                    f"MATCH (s:{src_lbl} {{id: $sid}}), (t:{dst_lbl} {{id: $tid}}) "
                    "MERGE (s)-[r:ASSUMES]->(t) "
                    "SET r.is_implicit = $imp, r.evidence_id = $eid, r.confidence = $conf",
                    {
                        "sid": edge.source_id,
                        "tid": edge.target_id,
                        "imp": bool(edge.is_implicit),
                        "eid": edge.evidence_id,
                        "conf": float(edge.confidence),
                    },
                )
            elif rel == "FALSIFIES":
                conn.execute(
                    f"MATCH (s:{src_lbl} {{id: $sid}}), (t:{dst_lbl} {{id: $tid}}) "
                    "MERGE (s)-[r:FALSIFIES]->(t) "
                    "SET r.regime = $regime, r.evidence_id = $eid, r.confidence = $conf",
                    {
                        "sid": edge.source_id,
                        "tid": edge.target_id,
                        "regime": edge.regime or "",
                        "eid": edge.evidence_id,
                        "conf": float(edge.confidence),
                    },
                )
            else:
                raise ValueError(f"Unsupported semantic relation_type: {rel}")

    # ── Deterministic Rebuild from SQLite ───────────────────────────────────

    def rebuild_from_sqlite(self, store: LiteratureStore) -> dict[str, int]:
        """
        Deterministically rebuild the entire LadybugDB Knowledge Graph from SQLite.
        Removes any stale `.lbdb` state and re-projects all tables cleanly.
        """
        for candidate in (
            self.kg_path,
            Path(f"{self.kg_path}.wal"),
            Path(f"{self.kg_path}.lock"),
        ):
            if candidate.is_dir():
                shutil.rmtree(candidate, ignore_errors=True)
            elif candidate.exists():
                candidate.unlink()

        self._init_schema()
        counts: dict[str, int] = {
            "papers": 0,
            "citations": 0,
            "evidence": 0,
            "gaps": 0,
            "datasets": 0,
            "metrics": 0,
            "results": 0,
            "entities": 0,
            "semantic_edges": 0,
        }

        with store._lock, self._connect(read_only=False) as conn:
            cur = store.conn.cursor()

            # 1. Papers + DOIs
            cur.execute(
                """
                SELECT p.id, p.title, p.year, p.is_retracted, p.venue_tier,
                       (SELECT external_id FROM paper_identifiers pi
                        WHERE pi.paper_id = p.id AND pi.provider = 'doi' LIMIT 1) AS doi
                FROM papers p
                """
            )
            for pid, title, year, is_ret, vtier, doi in cur.fetchall():
                conn.execute(
                    "MERGE (p:Paper {id: $id}) "
                    "SET p.doi = $doi, p.title = $title, p.year = $year, "
                    "p.is_retracted = $ret, p.venue_tier = $tier",
                    {
                        "id": str(pid),
                        "doi": str(doi or ""),
                        "title": str(title or ""),
                        "year": int(year) if year is not None else 0,
                        "ret": bool(is_ret),
                        "tier": str(vtier or ""),
                    },
                )
                counts["papers"] += 1

            # 2. Citations
            cur.execute("SELECT source_paper_id, target_paper_id, is_influential, context FROM citations")
            for src, tgt, infl, ctx in cur.fetchall():
                conn.execute(
                    "MATCH (s:Paper {id: $s}), (t:Paper {id: $t}) "
                    "MERGE (s)-[r:CITES]->(t) "
                    "SET r.is_influential = $infl, r.intent = $intent",
                    {
                        "s": str(src),
                        "t": str(tgt),
                        "infl": bool(infl),
                        "intent": str(ctx or ""),
                    },
                )
                counts["citations"] += 1

            # 3. Evidence
            cur.execute(
                "SELECT id, paper_id, evidence_type, source_section, extracted_text, extraction_method, confidence "
                "FROM evidence"
            )
            for eid, pid, etype, sec, txt, meth, conf in cur.fetchall():
                conn.execute(
                    "MERGE (e:Evidence {id: $id}) "
                    "SET e.paper_id = $pid, e.evidence_type = $etype, e.source_section = $sec, "
                    "e.extracted_text = $txt, e.extraction_method = $meth, e.confidence = $conf",
                    {
                        "id": str(eid),
                        "pid": str(pid),
                        "etype": str(etype),
                        "sec": str(sec or ""),
                        "txt": str(txt),
                        "meth": str(meth),
                        "conf": float(conf) if conf is not None else 1.0,
                    },
                )
                counts["evidence"] += 1

            # 4. Gaps
            cur.execute(
                "SELECT id, paper_id, gap_type, claim_summary, primary_evidence_id, verification_status FROM paper_gaps"
            )
            for gid, pid, gtype, summary, ev_id, status in cur.fetchall():
                conn.execute(
                    "MERGE (g:Gap {id: $id}) "
                    "SET g.gap_type = $gtype, g.summary = $summary, g.verification_status = $status",
                    {
                        "id": str(gid),
                        "gtype": str(gtype),
                        "summary": str(summary),
                        "status": str(status),
                    },
                )
                conn.execute(
                    "MATCH (p:Paper {id: $pid}), (g:Gap {id: $gid}) "
                    "MERGE (p)-[r:REPORTS_GAP]->(g) SET r.evidence_id = $eid",
                    {"pid": str(pid), "gid": str(gid), "eid": str(ev_id)},
                )
                counts["gaps"] += 1

            # 5. Benchmarks (Datasets), Metrics, Results
            cur.execute("SELECT id, name, domain FROM benchmarks")
            for bid, bname, bdom in cur.fetchall():
                conn.execute(
                    "MERGE (d:Dataset {id: $id}) SET d.name = $name, d.domain = $dom",
                    {"id": str(bid), "name": str(bname), "dom": str(bdom or "")},
                )
                counts["datasets"] += 1

            cur.execute("SELECT id, name, goal, unit FROM evaluation_metrics")
            for mid, mname, mgoal, munit in cur.fetchall():
                conn.execute(
                    "MERGE (m:Metric {id: $id}) SET m.name = $name, m.goal = $goal, m.unit = $unit",
                    {"id": str(mid), "name": str(mname), "goal": str(mgoal), "unit": str(munit or "")},
                )
                counts["metrics"] += 1

            cur.execute(
                "SELECT id, paper_id, benchmark_id, metric_id, metric_value, is_sota, "
                "table_or_figure, provenance_source FROM benchmark_results"
            )
            for rid, pid, bid, mid, mval, is_sota, tof, prov in cur.fetchall():
                conn.execute(
                    "MERGE (r:Result {id: $id}) "
                    "SET r.metric_value = $val, r.is_sota = $sota, "
                    "r.table_or_figure = $tof, r.provenance_source = $prov",
                    {
                        "id": str(rid),
                        "val": float(mval),
                        "sota": bool(is_sota),
                        "tof": str(tof or ""),
                        "prov": str(prov or "author_reported"),
                    },
                )
                conn.execute(
                    "MATCH (p:Paper {id: $pid}), (r:Result {id: $rid}) MERGE (p)-[:RAN]->(r)",
                    {"pid": str(pid), "rid": str(rid)},
                )
                conn.execute(
                    "MATCH (r:Result {id: $rid}), (d:Dataset {id: $bid}) MERGE (r)-[:ON_DATASET]->(d)",
                    {"rid": str(rid), "bid": str(bid)},
                )
                conn.execute(
                    "MATCH (r:Result {id: $rid}), (m:Metric {id: $mid}) MERGE (r)-[:MEASURED_BY]->(m)",
                    {"rid": str(rid), "mid": str(mid)},
                )
                counts["results"] += 1

        # 6. Semantic Entities & Edges (via public helpers)
        for entity in store.list_entities():
            self.upsert_entity(entity)
            counts["entities"] += 1

        for edge in store.list_semantic_edges():
            self.upsert_semantic_edge(edge)
            counts["semantic_edges"] += 1

        store.set_kg_sync_state("last_rebuild_utc", datetime.now(UTC).isoformat())
        store.set_kg_sync_state("last_rebuild_counts", json.dumps(counts))
        return counts

    # ── Multi-Hop Scientific Reasoning Queries ──────────────────────────────

    def trace_assumptions(self, target: str, max_hops: int = 3) -> dict[str, Any]:
        """
        Trace direct and inherited assumptions for a Method (by ID or name) or Paper (by ID),
        and detect whether any upstream assumption has been falsified elsewhere in the KG.
        """
        hops = max(1, min(int(max_hops), 5))
        with self._connect(read_only=True) as conn:
            # Resolve target to Method IDs
            method_rows = self._rows_to_dicts(
                conn.execute(
                    """
                    MATCH (m:Method)
                    WHERE m.id = $target
                       OR lower(m.canonical_name) = lower($target)
                       OR lower(m.aliases) CONTAINS lower($target)
                    RETURN m.id AS method_id, m.canonical_name AS method_name
                    """,
                    {"target": target},
                )
            )
            if not method_rows:
                # Try resolving via Paper -> USES / PROPOSES -> Method
                method_rows = self._rows_to_dicts(
                    conn.execute(
                        """
                        MATCH (p:Paper {id: $target})-[:USES|PROPOSES]->(m:Method)
                        RETURN m.id AS method_id, m.canonical_name AS method_name
                        """,
                        {"target": target},
                    )
                )

            method_ids = [r["method_id"] for r in method_rows]
            assumptions: list[dict[str, Any]] = []
            falsifications: list[dict[str, Any]] = []

            for mid in method_ids:
                # Direct + inherited via EXTENDS*0..hops
                a_rows = self._rows_to_dicts(
                    conn.execute(
                        f"""
                        MATCH (m:Method {{id: $mid}})-[:EXTENDS*0..{hops}]->(anc:Method)-[r:ASSUMES]->(a:Assumption)
                        OPTIONAL MATCH (ev:Evidence {{id: r.evidence_id}})
                        RETURN m.canonical_name AS target_method,
                               anc.id AS source_method_id,
                               anc.canonical_name AS source_method,
                               a.id AS assumption_id,
                               a.statement AS statement,
                               a.scope AS scope,
                               r.is_implicit AS is_implicit,
                               r.confidence AS confidence,
                               r.evidence_id AS evidence_id,
                               ev.extracted_text AS evidence_quote
                        """,
                        {"mid": mid},
                    )
                )
                assumptions.extend(a_rows)

                f_rows = self._rows_to_dicts(
                    conn.execute(
                        f"""
                        MATCH (m:Method {{id: $mid}})-[:EXTENDS*0..{hops}]->(anc:Method)-[:ASSUMES]->(a:Assumption)
                              <-[f:FALSIFIES]-(src)
                        OPTIONAL MATCH (ev:Evidence {{id: f.evidence_id}})
                        RETURN a.id AS assumption_id,
                               a.statement AS assumption_statement,
                               anc.canonical_name AS inherited_from,
                               src.id AS falsifier_id,
                               f.regime AS regime,
                               f.confidence AS confidence,
                               f.evidence_id AS evidence_id,
                               ev.extracted_text AS evidence_quote
                        """,
                        {"mid": mid},
                    )
                )
                falsifications.extend(f_rows)

        return {
            "target": target,
            "resolved_methods": method_rows,
            "max_hops": hops,
            "assumptions": assumptions,
            "falsifications": falsifications,
            "has_falsified_assumptions": len(falsifications) > 0,
        }

    def delta_novelty(
        self,
        method_name_or_id: str,
        peer_method_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Compute structural delta-novelty of a Method relative to peer Methods:
        assumptions removed/added, gaps addressed, and extensions.
        """
        with self._connect(read_only=True) as conn:
            target_rows = self._rows_to_dicts(
                conn.execute(
                    """
                    MATCH (m:Method)
                    WHERE m.id = $t OR lower(m.canonical_name) = lower($t)
                    RETURN m.id AS id, m.canonical_name AS canonical_name,
                           m.category AS category, m.complexity AS complexity
                    LIMIT 1
                    """,
                    {"t": method_name_or_id},
                )
            )
            if not target_rows:
                return {"status": "NOT_FOUND", "target": method_name_or_id}

            target = target_rows[0]
            tid = target["id"]

            target_assumptions = self._rows_to_dicts(
                conn.execute(
                    "MATCH (:Method {id: $id})-[:ASSUMES]->(a:Assumption) RETURN a.id AS id, a.statement AS statement",
                    {"id": tid},
                )
            )
            target_gaps = self._rows_to_dicts(
                conn.execute(
                    "MATCH (:Method {id: $id})-[:ADDRESSES]->(g:Gap) "
                    "RETURN g.id AS id, g.gap_type AS gap_type, g.summary AS summary",
                    {"id": tid},
                )
            )
            extends_rows = self._rows_to_dicts(
                conn.execute(
                    "MATCH (:Method {id: $id})-[r:EXTENDS]->(base:Method) "
                    "RETURN base.id AS base_id, base.canonical_name AS base_name, r.delta_summary AS delta",
                    {"id": tid},
                )
            )

            if peer_method_ids:
                peers = self._rows_to_dicts(
                    conn.execute(
                        "MATCH (p:Method) WHERE p.id IN $pids RETURN p.id AS id, p.canonical_name AS canonical_name",
                        {"pids": peer_method_ids},
                    )
                )
            else:
                peers = self._rows_to_dicts(
                    conn.execute(
                        "MATCH (p:Method) WHERE p.id <> $id "
                        "RETURN p.id AS id, p.canonical_name AS canonical_name LIMIT 25",
                        {"id": tid},
                    )
                )

            target_a_ids = {a["id"] for a in target_assumptions}
            peer_comparisons: list[dict[str, Any]] = []
            for peer in peers:
                p_assumptions = self._rows_to_dicts(
                    conn.execute(
                        "MATCH (:Method {id: $id})-[:ASSUMES]->(a:Assumption) "
                        "RETURN a.id AS id, a.statement AS statement",
                        {"id": peer["id"]},
                    )
                )
                p_a_ids = {a["id"] for a in p_assumptions}
                removed = [a for a in p_assumptions if a["id"] not in target_a_ids]
                added = [a for a in target_assumptions if a["id"] not in p_a_ids]
                peer_comparisons.append(
                    {
                        "peer_id": peer["id"],
                        "peer_name": peer["canonical_name"],
                        "assumptions_removed_by_target": removed,
                        "assumptions_added_by_target": added,
                    }
                )

        return {
            "status": "OK",
            "target_method": target,
            "assumptions": target_assumptions,
            "gaps_addressed": target_gaps,
            "extends": extends_rows,
            "peer_comparisons": peer_comparisons,
        }

    def find_contradictions(self, paper_id: str | None = None) -> list[dict[str, Any]]:
        """Return all FALSIFIES and CONTRADICTS edges (optionally filtered by paper_id) with provenance."""
        with self._connect(read_only=True) as conn:
            results: list[dict[str, Any]] = []
            if paper_id:
                c_rows = self._rows_to_dicts(
                    conn.execute(
                        """
                        MATCH (p:Paper {id: $pid})-[:PROVES]->(c1:Claim)-[r:CONTRADICTS]-(c2:Claim)
                        OPTIONAL MATCH (ev:Evidence {id: r.evidence_id})
                        RETURN 'CONTRADICTS' AS kind, c1.id AS source_id, c1.summary AS source_summary,
                               c2.id AS target_id, c2.summary AS target_summary,
                               r.confidence AS confidence, r.evidence_id AS evidence_id,
                               ev.extracted_text AS evidence_quote
                        """,
                        {"pid": paper_id},
                    )
                )
                f_rows = self._rows_to_dicts(
                    conn.execute(
                        """
                        MATCH (p:Paper {id: $pid})-[r:FALSIFIES]->(t)
                        OPTIONAL MATCH (ev:Evidence {id: r.evidence_id})
                        RETURN 'FALSIFIES' AS kind, p.id AS source_id, p.title AS source_summary,
                               t.id AS target_id, r.regime AS regime,
                               r.confidence AS confidence, r.evidence_id AS evidence_id,
                               ev.extracted_text AS evidence_quote
                        """,
                        {"pid": paper_id},
                    )
                )
            else:
                c_rows = self._rows_to_dicts(
                    conn.execute(
                        """
                        MATCH (c1:Claim)-[r:CONTRADICTS]->(c2:Claim)
                        OPTIONAL MATCH (ev:Evidence {id: r.evidence_id})
                        RETURN 'CONTRADICTS' AS kind, c1.id AS source_id, c1.summary AS source_summary,
                               c2.id AS target_id, c2.summary AS target_summary,
                               r.confidence AS confidence, r.evidence_id AS evidence_id,
                               ev.extracted_text AS evidence_quote
                        """
                    )
                )
                f_rows = self._rows_to_dicts(
                    conn.execute(
                        """
                        MATCH (s)-[r:FALSIFIES]->(t)
                        OPTIONAL MATCH (ev:Evidence {id: r.evidence_id})
                        RETURN 'FALSIFIES' AS kind, s.id AS source_id, t.id AS target_id,
                               r.regime AS regime, r.confidence AS confidence,
                               r.evidence_id AS evidence_id, ev.extracted_text AS evidence_quote
                        """
                    )
                )
            results.extend(c_rows)
            results.extend(f_rows)
            return results

    def find_uncredited_method(self, name_or_alias: str) -> list[dict[str, Any]]:
        """Resolve a method name/alias to its proposing Papers and flag retractions."""
        with self._connect(read_only=True) as conn:
            return self._rows_to_dicts(
                conn.execute(
                    """
                    MATCH (p:Paper)-[r:PROPOSES]->(m:Method)
                    WHERE lower(m.canonical_name) = lower($q)
                       OR lower(m.aliases) CONTAINS lower($q)
                    RETURN m.id AS method_id, m.canonical_name AS canonical_name,
                           p.id AS paper_id, p.title AS paper_title,
                           p.doi AS doi, p.year AS year, p.is_retracted AS is_retracted,
                           r.evidence_id AS evidence_id
                    """,
                    {"q": name_or_alias},
                )
            )


__all__ = [
    "DEFAULT_KG_PATH",
    "KG_SCHEMA_STATEMENTS",
    "KnowledgeGraphStore",
    "validate_readonly_cypher",
]
