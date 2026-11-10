"""
In-repo project manifest serialization, re-hydration, and synchronization engine.
Serializes project papers, citations, evidence, research gaps, and benchmark evaluations
to `<repo>/.scifi/literature_manifest.json` and updates `<repo>/.scifi/references.bib`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from scifi.literature.models import (
    BenchmarkRecord,
    BenchmarkResultRecord,
    CitationRecord,
    EvaluationConditionRecord,
    EvaluationMetricRecord,
    EvidenceRecord,
    PaperGapRecord,
    PaperLocationRecord,
    PaperRecord,
    ProjectRecord,
    ReprintRequestRecord,
)
from scifi.literature.reporter import export_bibtex_entries
from scifi.literature.store import LiteratureStore

DEFAULT_MANIFEST_FILENAME = "literature_manifest.json"
DEFAULT_BIB_FILENAME = "references.bib"
MANIFEST_SCHEMA_URL = "https://scifi.dev/schema/literature-manifest.v1.json"


def export_manifest(
    store: LiteratureStore,
    project_id: str,
    output_path: str | Path,
) -> Path:
    """
    Export project papers, citations, gaps, benchmarks, and reprint states
    to a JSON manifest file.

    Parameters
    ----------
    store : LiteratureStore
        Active SQLite knowledge store instance.
    project_id : str
        Unique project identifier.
    output_path : str | Path
        Target destination file path (or directory) for the manifest.

    Returns
    -------
    Path
        Resolved absolute Path to the written manifest JSON file.
    """
    proj = store.get_project(project_id)
    if proj is None:
        raise ValueError(f"Project '{project_id}' not found.")

    out = Path(output_path).resolve()
    if out.is_dir() or out.suffix != ".json":
        out = out / DEFAULT_MANIFEST_FILENAME

    out.parent.mkdir(parents=True, exist_ok=True)

    papers = store.get_project_papers(project_id)

    # 1. Papers with convenience flags
    papers_serialized: list[dict[str, Any]] = []
    seen_paper_ids: set[str] = set()

    for p in papers:
        seen_paper_ids.add(p.id)
        p_dict = p.to_dict()

        # Compute convenience flags
        oa_status = "closed"
        if p.locations:
            non_closed = [loc.oa_status for loc in p.locations if loc.oa_status and loc.oa_status != "closed"]
            if non_closed:
                oa_status = non_closed[0]
            elif any(loc.is_oa for loc in p.locations):
                oa_status = "gold"

        has_local_pdf = any(bool(loc.local_pdf_path) for loc in p.locations)

        reprints = store.get_reprint_requests(project_id=project_id, paper_id=p.id)
        reprint_status = reprints[0].status if reprints else None

        p_dict["oa_status"] = oa_status
        p_dict["has_local_pdf"] = has_local_pdf
        p_dict["reprint_status"] = reprint_status
        papers_serialized.append(p_dict)

    # 2. Citations
    citations_serialized: list[dict[str, Any]] = []
    seen_citations: set[tuple[str, str]] = set()

    for p in papers:
        cits = store.get_paper_citations(p.id)
        for cit in cits:
            key = (cit.source_paper_id, cit.target_paper_id)
            if key not in seen_citations:
                seen_citations.add(key)
                citations_serialized.append(cit.to_dict())

    # 3. Evidence & Gaps
    evidence_serialized: list[dict[str, Any]] = []
    seen_evidence_ids: set[str] = set()
    gaps_serialized: list[dict[str, Any]] = []
    seen_gap_ids: set[str] = set()

    for p in papers:
        evs = store.get_paper_evidence(p.id)
        for ev in evs:
            if ev.id not in seen_evidence_ids:
                seen_evidence_ids.add(ev.id)
                evidence_serialized.append(ev.to_dict())

        gaps = store.get_paper_gaps(p.id)
        for gap in gaps:
            if gap.id not in seen_gap_ids:
                seen_gap_ids.add(gap.id)
                gaps_serialized.append(gap.to_dict())

    # 4. Benchmarks, Results, Metrics & Conditions
    benchmark_results_serialized: list[dict[str, Any]] = []
    seen_result_ids: set[str] = set()
    benchmark_ids: set[str] = set()
    metric_ids: set[str] = set()
    condition_ids: set[str] = set()

    for p in papers:
        results = store.get_paper_benchmark_results(p.id)
        for r in results:
            if r.id not in seen_result_ids:
                seen_result_ids.add(r.id)
                benchmark_results_serialized.append(r.to_dict())
                benchmark_ids.add(r.benchmark_id)
                metric_ids.add(r.metric_id)
                if r.condition_id:
                    condition_ids.add(r.condition_id)

    benchmarks_serialized: list[dict[str, Any]] = []
    metrics_serialized: list[dict[str, Any]] = []
    conditions_serialized: list[dict[str, Any]] = []

    with store._lock:
        cursor = store.conn.cursor()
        for b_id in sorted(benchmark_ids):
            cursor.execute(
                "SELECT id, name, domain, canonical_url, description FROM benchmarks WHERE id = ?",
                (b_id,),
            )
            row = cursor.fetchone()
            if row:
                benchmarks_serialized.append(LiteratureStore._row_to_benchmark(row).to_dict())

        for m_id in sorted(metric_ids):
            cursor.execute(
                "SELECT id, name, goal, unit, description FROM evaluation_metrics WHERE id = ?",
                (m_id,),
            )
            row = cursor.fetchone()
            if row:
                metrics_serialized.append(LiteratureStore._row_to_metric(row).to_dict())

        for c_id in sorted(condition_ids):
            cursor.execute(
                "SELECT id, name, dataset_split, hardware, notes FROM evaluation_conditions WHERE id = ?",
                (c_id,),
            )
            row = cursor.fetchone()
            if row:
                conditions_serialized.append(
                    EvaluationConditionRecord(
                        id=row[0],
                        name=row[1],
                        dataset_split=row[2],
                        hardware=row[3],
                        notes=row[4],
                    ).to_dict()
                )

    # 5. Reprint Requests
    reprint_reqs = store.get_reprint_requests(project_id=project_id)
    reprints_serialized = [r.to_dict() for r in reprint_reqs]

    manifest_data = {
        "$schema": MANIFEST_SCHEMA_URL,
        "project_id": proj.id,
        "project_name": proj.name,
        "workspace_path": proj.workspace_path,
        "description": proj.description,
        "synced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "papers_count": len(papers_serialized),
        "papers": papers_serialized,
        "citations": citations_serialized,
        "evidence": evidence_serialized,
        "gaps": gaps_serialized,
        "benchmarks": benchmarks_serialized,
        "benchmark_results": benchmark_results_serialized,
        "evaluation_metrics": metrics_serialized,
        "evaluation_conditions": conditions_serialized,
        "reprint_requests": reprints_serialized,
    }

    out.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def import_manifest(
    store: LiteratureStore,
    manifest_path: str | Path,
    workspace_path: Optional[str | Path] = None,
) -> ProjectRecord:
    """
    Rehydrate project papers, citations, gaps, benchmarks, and reprint requests
    from a JSON manifest into the knowledge store.

    Parameters
    ----------
    store : LiteratureStore
        Active SQLite knowledge store instance.
    manifest_path : str | Path
        Path to the manifest JSON file or repository directory containing `.scifi/literature_manifest.json`.
    workspace_path : Optional[str | Path]
        Optional explicit workspace path. If omitted, resolved from local directory structure or manifest metadata.

    Returns
    -------
    ProjectRecord
        The rehydrated or updated project record in the knowledge store.
    """
    m_path = Path(manifest_path).resolve()
    if m_path.is_dir():
        cand1 = m_path / ".scifi" / DEFAULT_MANIFEST_FILENAME
        cand2 = m_path / DEFAULT_MANIFEST_FILENAME
        if cand1.exists():
            m_path = cand1
        elif cand2.exists():
            m_path = cand2
        else:
            raise FileNotFoundError(f"No {DEFAULT_MANIFEST_FILENAME} found in {m_path}")

    if not m_path.exists():
        raise FileNotFoundError(f"Manifest file not found: {m_path}")

    data = json.loads(m_path.read_text(encoding="utf-8"))

    # Resolve workspace path
    if workspace_path is not None:
        ws_path = Path(workspace_path).resolve()
    elif m_path.parent.name == ".scifi":
        ws_path = m_path.parent.parent.resolve()
    elif "workspace_path" in data and data["workspace_path"]:
        ws_path = Path(data["workspace_path"]).resolve()
    else:
        ws_path = m_path.parent.resolve()

    proj_name = data.get("project_name") or ws_path.name
    proj_id = data.get("project_id")
    description = data.get("description")

    proj = store.register_project(
        name=proj_name,
        workspace_path=ws_path,
        description=description,
        project_id=proj_id,
    )

    # 1. Papers
    for p_data in data.get("papers", []):
        paper = PaperRecord.from_dict(p_data)
        # Synthesize fallback location if oa_status or local_pdf_path provided without explicit locations
        if not paper.locations and any(k in p_data for k in ("oa_status", "pdf_url", "local_pdf_path")):
            oa_status = p_data.get("oa_status", "closed")
            loc = PaperLocationRecord(
                id=f"loc-{paper.id}",
                paper_id=paper.id,
                location_type="manifest_import",
                is_oa=(oa_status != "closed"),
                oa_status=oa_status,
                landing_page_url=p_data.get("landing_page_url"),
                pdf_url=p_data.get("pdf_url"),
                local_pdf_path=p_data.get("local_pdf_path"),
            )
            paper.locations.append(loc)

        store.upsert_paper(paper)
        store.link_paper_to_project(proj.id, paper.id)

    # 2. Citations
    for c_data in data.get("citations", []):
        cit = CitationRecord.from_dict(c_data)
        store.save_citation(cit)

    # 3. Evidence
    for ev_data in data.get("evidence", []):
        ev = EvidenceRecord.from_dict(ev_data)
        store.save_evidence(ev)

    # 4. Gaps (ensure primary_evidence_id foreign key is satisfied)
    for gap_data in data.get("gaps", []):
        gap = PaperGapRecord.from_dict(gap_data)
        if gap.primary_evidence_id:
            with store.transaction():
                store.conn.execute(
                    """
                    INSERT OR IGNORE INTO evidence (id, paper_id, evidence_type, extracted_text, extraction_method)
                    VALUES (?, ?, 'limitation', '', 'manifest_import_stub')
                    """,
                    (gap.primary_evidence_id, gap.paper_id),
                )
        store.save_paper_gap(gap)

    # 5. Benchmarks, Metrics, Conditions, Results
    for bm_data in data.get("benchmarks", []):
        if "metric_value" in bm_data or "benchmark_id" in bm_data:
            store.save_benchmark_result(BenchmarkResultRecord.from_dict(bm_data))
        else:
            store.save_benchmark(BenchmarkRecord.from_dict(bm_data))

    for met_data in data.get("evaluation_metrics", []):
        store.save_evaluation_metric(EvaluationMetricRecord.from_dict(met_data))

    for cond_data in data.get("evaluation_conditions", []):
        store.save_evaluation_condition(EvaluationConditionRecord.from_dict(cond_data))

    for bmr_data in data.get("benchmark_results", []):
        store.save_benchmark_result(BenchmarkResultRecord.from_dict(bmr_data))

    # 6. Reprint Requests
    for rep_data in data.get("reprint_requests", []):
        rep_id = rep_data.get("id")
        existing = store.get_reprint_request(rep_id) if rep_id else None
        if existing is None:
            store.create_reprint_request(
                project_id=proj.id,
                paper_id=rep_data["paper_id"],
                author_name=rep_data.get("author_name", "Author"),
                author_email=rep_data.get("author_email"),
                author_affiliation=rep_data.get("author_affiliation"),
                subject=rep_data.get("subject", ""),
                body=rep_data.get("body", ""),
                mailto_url=rep_data.get("mailto_url"),
                status=rep_data.get("status", "DRAFT_READY"),
                request_id=rep_id,
            )
        else:
            store.update_reprint_request(
                request_id=rep_id,
                author_email=rep_data.get("author_email"),
                status=rep_data.get("status"),
                mailto_url=rep_data.get("mailto_url"),
                subject=rep_data.get("subject"),
                body=rep_data.get("body"),
            )

    return proj


def sync_workspace(
    store: LiteratureStore,
    workspace_path: str | Path,
) -> ProjectRecord:
    """
    Bidirectionally synchronize a project workspace with the central knowledge store.

    1. Ingests `<workspace>/.scifi/literature_manifest.json` if it exists.
    2. Registers the workspace as a project if not already present.
    3. Merges and updates `<workspace>/.scifi/literature_manifest.json` with all
       project papers currently in the central store.
    4. Regenerates `<workspace>/.scifi/references.bib` (and root `references.bib`
       if already present) with standardized BibTeX entries.

    Parameters
    ----------
    store : LiteratureStore
        Active SQLite knowledge store instance.
    workspace_path : str | Path
        Path to the project repository / workspace.

    Returns
    -------
    ProjectRecord
        The synchronized project record.
    """
    ws = Path(workspace_path).resolve()
    scifi_dir = ws / ".scifi"
    manifest_file = scifi_dir / DEFAULT_MANIFEST_FILENAME
    root_manifest_file = ws / DEFAULT_MANIFEST_FILENAME

    # Choose manifest source if existing
    target_source = manifest_file if manifest_file.exists() else (root_manifest_file if root_manifest_file.exists() else None)

    if target_source is not None:
        proj = import_manifest(store, target_source, workspace_path=ws)
    else:
        proj = store.get_project_by_workspace(ws)
        if proj is None:
            proj = store.register_project(name=ws.name, workspace_path=ws)

    # Export merged state back to .scifi/literature_manifest.json
    export_manifest(store, proj.id, manifest_file)

    # Regenerate references.bib
    papers = store.get_project_papers(proj.id)
    bib_content = export_bibtex_entries(papers)

    bib_file = scifi_dir / DEFAULT_BIB_FILENAME
    bib_file.write_text(bib_content, encoding="utf-8")

    root_bib = ws / DEFAULT_BIB_FILENAME
    if root_bib.exists():
        root_bib.write_text(bib_content, encoding="utf-8")

    return proj


__all__ = [
    "DEFAULT_BIB_FILENAME",
    "DEFAULT_MANIFEST_FILENAME",
    "MANIFEST_SCHEMA_URL",
    "export_manifest",
    "import_manifest",
    "sync_workspace",
]
