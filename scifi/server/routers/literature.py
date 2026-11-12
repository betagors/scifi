"""
FastMCP Router: Open-Access Literature, Lineage Discovery, and Central Hub Tools.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scifi.literature.benchmarks import CANONICAL_BENCHMARKS
from scifi.literature.models import (
    BenchmarkRecord,
    BenchmarkResultRecord,
    EvaluationConditionRecord,
    EvaluationMetricRecord,
    PaperRecord,
)
from scifi.literature.reporter import save_bibtex_file
from scifi.literature.reprint import (
    ingest_paper_copy,
    prepare_reprint_for_paper,
)
from scifi.literature.sota import SotaEvaluator
from scifi.logging import get_logger
from scifi.server.app import _resolve_project, mcp

logger = get_logger(__name__)


@mcp.tool()
def scifi_fetch_paper_pdf(
    identifier: str,
    output_dir: str = "workspace",
    email: str = "researcher@scifi.org",
) -> dict[str, Any]:
    """
    Fetch an open-access PDF for a paper by DOI or arXiv ID from arXiv, Unpaywall, or OpenAlex.

    Args:
        identifier: DOI (e.g. '10.1038/nature14539') or arXiv ID (e.g. '1706.03762').
        output_dir: Directory where the downloaded PDF should be stored.
        email: Contact email for polite OpenAlex/Unpaywall registry requests.

    Returns:
        Dictionary with status, identifier, file_path, source, and file size.
    """
    import scifi.server as srv

    return srv.fetch_paper_pdf(identifier=identifier, output_dir=output_dir, email=email)


@mcp.tool()
def scifi_extract_pdf_text(
    pdf_path: str,
    max_pages: int = 20,
    max_section_length: int | None = None,
) -> dict[str, Any]:
    """
    Extract structured text from a scientific paper PDF for synthesis, methodology audit, and delta-novelty matrix generation.

    Args:
        pdf_path: Path to the PDF file.
        max_pages: Maximum number of pages to extract text from (default: 20).
        max_section_length: Optional maximum characters per extracted section (default: 15000).

    Returns:
        Dictionary with status, page_count, extracted text, and detected paper sections.
    """
    import scifi.server as srv

    kwargs: dict[str, Any] = {"pdf_path": pdf_path, "max_pages": max_pages}
    if max_section_length is not None:
        kwargs["max_section_length"] = max_section_length
    return srv.extract_pdf_text(**kwargs)


@mcp.tool()
def scifi_map_literature(
    query: str,
    depth: int = 2,
    max_papers: int = 25,
    graph_id: str | None = None,
    output_dir: str | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    venue_tier: str | None = None,
    require_evidence: bool = False,
    extract_fulltext: bool = True,
    pdf_dir: str | None = None,
    auto_fetch_pdf: bool = False,
) -> dict[str, Any]:
    """
    Discover intellectual lineage and construct an interactive literature graph from a seed paper or query.
    Extracts foundational citations, frontier developments, persists to SQLite store, and optionally renders artifacts.

    Args:
        query: Seed paper title, DOI, arXiv ID, or OpenAlex ID.
        depth: Traversal hops backward (foundations) and forward (frontier) (default: 2).
        max_papers: Maximum number of papers to discover (default: 25).
        graph_id: Optional persistent graph session identifier.
        output_dir: Optional filesystem directory to save interactive HTML map, Markdown report, and references.bib.

    Returns:
        Dictionary with status ('SUCCESS' or 'ERROR'), graph_id, seed_paper_id, total_papers, total_citations,
        papers list, and generated file paths if output_dir specified.
    """
    import scifi.server as srv

    store = srv.get_literature_store()
    crawler = srv.LineageCrawler(store=store)

    assigned_graph_id, papers, citations = crawler.crawl_lineage(
        query=query,
        depth=depth,
        max_papers=max_papers,
        graph_id=graph_id,
        min_year=min_year,
        max_year=max_year,
        venue_tier=venue_tier,
        require_evidence=require_evidence,
        extract_fulltext_gaps=extract_fulltext,
        pdf_dir=pdf_dir,
        auto_fetch_pdf=auto_fetch_pdf,
    )

    if not papers:
        return {
            "status": "ERROR",
            "message": f"Could not resolve seed paper or find literature for query: '{query}'",
            "graph_id": assigned_graph_id,
            "seed_paper_id": None,
            "total_papers": 0,
            "total_citations": 0,
            "gaps_count": 0,
            "corroborated_gaps_count": 0,
            "gaps": [],
            "papers": [],
            "benchmark_results_count": 0,
            "sota_leaders": [],
            "benchmarks": [],
            "files": None,
        }

    depths = crawler.compute_topological_depths(papers, citations)
    files_dict: dict[str, str] | None = None

    paper_gaps = store.get_graph_gaps(assigned_graph_id)
    evidence_map = store.get_graph_evidence(assigned_graph_id)
    benchmark_results = store.get_graph_benchmark_results(assigned_graph_id)
    benchmarks_map = store.get_graph_benchmarks(assigned_graph_id)
    metrics_map = store.get_graph_metrics(assigned_graph_id)
    conditions_map = store.get_graph_conditions(assigned_graph_id)

    total_gaps = sum(len(glist) for glist in paper_gaps.values())
    corroborated_count = sum(
        1 for glist in paper_gaps.values() for g in glist if g.verification_status == "corroborated"
    )
    gaps_list = [gap.to_dict() for glist in paper_gaps.values() for gap in glist]

    total_results = sum(len(rlist) for rlist in benchmark_results.values())
    sota_leaders = [r for rlist in benchmark_results.values() for r in rlist if r.is_sota]

    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        title = papers[0].title if papers else query
        seed_id = papers[0].id if papers else None

        html_path = srv.save_interactive_html(
            out_path / "literature_map.html",
            graph_title=title,
            papers=papers,
            citations=citations,
            depths=depths,
            seed_paper_id=seed_id,
            paper_gaps=paper_gaps,
            evidence_map=evidence_map,
            benchmark_results=benchmark_results,
            benchmarks_map=benchmarks_map,
            metrics_map=metrics_map,
            conditions_map=conditions_map,
        )
        md_path = srv.save_markdown_report(
            out_path / "literature_report.md",
            graph_title=title,
            papers=papers,
            citations=citations,
            depths=depths,
            paper_gaps=paper_gaps,
            evidence_map=evidence_map,
            benchmark_results=benchmark_results,
            benchmarks_map=benchmarks_map,
            metrics_map=metrics_map,
            conditions_map=conditions_map,
        )
        bib_path = save_bibtex_file(
            out_path / "references.bib",
            papers=papers,
        )

        files_dict = {
            "html_map": str(html_path.resolve()),
            "report_markdown": str(md_path.resolve()),
            "bibtex": str(bib_path.resolve()),
        }

    return {
        "status": "SUCCESS",
        "graph_id": assigned_graph_id,
        "seed_paper_id": papers[0].id if papers else None,
        "total_papers": len(papers),
        "total_citations": len(citations),
        "gaps_count": total_gaps,
        "corroborated_gaps_count": corroborated_count,
        "gaps": gaps_list,
        "benchmark_results_count": total_results,
        "sota_leaders": [r.to_dict() for r in sota_leaders],
        "benchmarks": [b.to_dict() for b in benchmarks_map.values()],
        "papers": [p.to_dict() for p in papers],
        "files": files_dict,
    }


@mcp.tool()
def scifi_query_sota_benchmarks(
    query: str,
    benchmark_name: str | None = None,
) -> dict[str, Any]:
    """
    Query benchmarks, active evaluation metrics, reported results, and current SOTA leaders for a research topic or benchmark name.
    Inspects canonical benchmark suites, domain taxonomies, and persisted empirical results to identify true state-of-the-art leaders and performance deltas.

    Args:
        query: Research domain, topic, paper title, DOI, or benchmark alias (e.g., 'Code Generation', 'HumanEval', 'Attention Is All You Need').
        benchmark_name: Optional explicit canonical benchmark name or ID to filter by (e.g., 'HumanEval', 'MMLU').

    Returns:
        Dictionary containing matched benchmarks, metrics, reported benchmark results, SOTA leaders, and performance deltas.
    """
    import scifi.server as srv

    store = srv.get_literature_store()
    q_clean = (query or "").strip().lower()
    bm_clean = (benchmark_name or "").strip().lower()

    matched_benchmarks: dict[str, BenchmarkRecord] = {}

    # 1. Check canonical benchmark catalog
    for bm_id, bm in CANONICAL_BENCHMARKS.items():
        if bm_clean:
            if bm_clean in bm.name.lower() or bm_clean in bm.id.lower() or bm_clean in bm.domain.lower():
                matched_benchmarks[bm.id] = bm
        elif q_clean:
            if (
                q_clean in bm.name.lower()
                or q_clean in bm.id.lower()
                or q_clean in bm.domain.lower()
                or (bm.description and q_clean in bm.description.lower())
            ):
                matched_benchmarks[bm.id] = bm

    # 2. Check benchmarks table in SQLite store
    try:
        with store._lock:
            cur = store.conn.cursor()
            cur.execute("SELECT id, name, domain, canonical_url, description FROM benchmarks")
            for r in cur.fetchall():
                bm = store._row_to_benchmark(r)
                if bm_clean:
                    if bm_clean in bm.name.lower() or bm_clean in bm.id.lower() or bm_clean in bm.domain.lower():
                        matched_benchmarks[bm.id] = bm
                elif q_clean:
                    if (
                        q_clean in bm.name.lower()
                        or q_clean in bm.id.lower()
                        or q_clean in bm.domain.lower()
                        or (bm.description and q_clean in bm.description.lower())
                    ):
                        matched_benchmarks[bm.id] = bm
    except Exception as e:
        logger.debug("Failed querying benchmarks from SQLite store: %s", e)

    # 3. Check matching papers by ID or title
    matched_paper_ids: set[str] = set()
    if q_clean:
        try:
            with store._lock:
                cur = store.conn.cursor()
                cur.execute(
                    "SELECT id, title FROM papers WHERE lower(id) LIKE ? OR lower(title) LIKE ?",
                    (f"%{q_clean}%", f"%{q_clean}%"),
                )
                for pid, _ in cur.fetchall():
                    matched_paper_ids.add(pid)
        except Exception as e:
            logger.debug("Failed querying matching papers from SQLite store: %s", e)

    # 4. Query benchmark results for matched benchmarks and matched papers
    all_results: list[BenchmarkResultRecord] = []
    benchmark_ids = list(matched_benchmarks.keys())

    if benchmark_ids or matched_paper_ids:
        try:
            with store._lock:
                cur = store.conn.cursor()
                clauses: list[str] = []
                params: list[Any] = []
                if benchmark_ids:
                    ph = ",".join("?" for _ in benchmark_ids)
                    clauses.append(f"br.benchmark_id IN ({ph})")
                    params.extend(benchmark_ids)
                if matched_paper_ids:
                    ph = ",".join("?" for _ in matched_paper_ids)
                    clauses.append(f"br.paper_id IN ({ph})")
                    params.extend(list(matched_paper_ids))

                sql = f"""
                    SELECT br.id, br.paper_id, br.benchmark_id, br.metric_id, br.condition_id,
                           br.metric_value, br.is_sota, br.rank, br.evidence_id, br.table_or_figure,
                           br.result_date, br.provenance_source
                    FROM benchmark_results br
                    WHERE {" OR ".join(clauses)}
                    ORDER BY br.benchmark_id ASC, br.metric_value DESC, br.id ASC
                """
                cur.execute(sql, tuple(params))
                for r in cur.fetchall():
                    res = store._row_to_benchmark_result(r)
                    all_results.append(res)
                    if res.benchmark_id not in matched_benchmarks:
                        cur2 = store.conn.cursor()
                        cur2.execute(
                            "SELECT id, name, domain, canonical_url, description FROM benchmarks WHERE id = ?",
                            (res.benchmark_id,),
                        )
                        bm_row = cur2.fetchone()
                        if bm_row:
                            matched_benchmarks[res.benchmark_id] = store._row_to_benchmark(bm_row)
        except Exception as e:
            logger.debug("Failed querying benchmark results from SQLite store: %s", e)

    # 5. Fetch associated metrics, conditions, and paper records
    metrics_map: dict[str, EvaluationMetricRecord] = {}
    conditions_map: dict[str, EvaluationConditionRecord] = {}
    papers_map: dict[str, PaperRecord] = {}

    if all_results:
        metric_ids = list({r.metric_id for r in all_results if r.metric_id})
        condition_ids = list({r.condition_id for r in all_results if r.condition_id})
        paper_ids = list({r.paper_id for r in all_results if r.paper_id})

        try:
            with store._lock:
                cur = store.conn.cursor()
                if metric_ids:
                    ph = ",".join("?" for _ in metric_ids)
                    cur.execute(
                        f"SELECT id, name, goal, unit, description FROM evaluation_metrics WHERE id IN ({ph})",
                        tuple(metric_ids),
                    )
                    for mr in cur.fetchall():
                        metrics_map[mr[0]] = store._row_to_metric(mr)
                if condition_ids:
                    ph = ",".join("?" for _ in condition_ids)
                    cur.execute(
                        f"SELECT id, name, dataset_split, hardware, notes FROM evaluation_conditions WHERE id IN ({ph})",
                        tuple(condition_ids),
                    )
                    for cr in cur.fetchall():
                        conditions_map[cr[0]] = store._row_to_condition(cr)
                if paper_ids:
                    for pid in paper_ids:
                        p = store.get_paper(pid)
                        if p:
                            papers_map[pid] = p
        except Exception as e:
            logger.debug("Failed querying metrics/conditions from SQLite store: %s", e)

    # 6. Evaluate SOTA rankings and deltas if results exist
    deltas: list[dict[str, Any]] = []
    if all_results:
        try:
            evaluator = SotaEvaluator()
            papers_list = list(papers_map.values()) or [
                PaperRecord(id=r.paper_id, title=r.paper_id) for r in all_results
            ]
            sota_results = evaluator.evaluate_sota_frontier(
                papers=papers_list,
                benchmark_results=all_results,
                metrics=metrics_map,
                benchmarks=matched_benchmarks,
            )
            for rep in sota_results.values():
                for d in rep.deltas:
                    deltas.append(d.to_dict())
        except Exception as e:
            logger.debug("Failed evaluating SOTA frontier: %s", e)

    sota_leaders = [r for r in all_results if r.is_sota]

    return {
        "status": "SUCCESS",
        "query": query,
        "benchmark_name": benchmark_name,
        "total_benchmarks": len(matched_benchmarks),
        "benchmarks": [b.to_dict() for b in matched_benchmarks.values()],
        "metrics": [m.to_dict() for m in metrics_map.values()],
        "total_results": len(all_results),
        "results": [r.to_dict() for r in all_results],
        "sota_leaders": [r.to_dict() for r in sota_leaders],
        "deltas": deltas,
    }


@mcp.tool()
def scifi_query_store(
    query_sql: str,
) -> list[dict[str, Any]]:
    """
    Execute a read-only SQL SELECT query against the SciFi literature intelligence SQLite store.
    Strictly enforced via SQLite authorizer callbacks; rejecting any INSERT, UPDATE, DELETE, DROP, or ALTER.

    Args:
        query_sql: Read-only SQL SELECT statement.

    Returns:
        List of dictionaries representing rows returned by the query.

    Raises:
        PermissionError: If any non-read-only SQL statement is attempted.
    """
    import scifi.server as srv

    store = srv.get_literature_store()
    return store.execute_read_query(query_sql)


@mcp.tool()
def scifi_export_bibtex(
    graph_id: str,
    output_path: str,
) -> dict[str, Any]:
    """
    Export verified and standardized BibTeX entries for all papers in a specific literature graph session.

    Args:
        graph_id: Persistent literature graph session ID.
        output_path: Destination path for the generated .bib file.

    Returns:
        Dictionary with status ('SUCCESS' or 'ERROR'), graph_id, total_entries, and output_path.
    """
    import scifi.server as srv

    store = srv.get_literature_store()
    papers = store.get_graph_papers(graph_id)

    if not papers:
        return {
            "status": "ERROR",
            "message": f"No papers found for graph session '{graph_id}'",
            "graph_id": graph_id,
            "total_entries": 0,
            "output_path": None,
        }

    out_file = save_bibtex_file(output_path, papers)
    return {
        "status": "SUCCESS",
        "graph_id": graph_id,
        "total_entries": len(papers),
        "output_path": str(out_file.resolve()),
    }


@mcp.tool()
def scifi_list_projects() -> list[dict[str, Any]]:
    """
    List all registered research projects in the central literature knowledge store.

    Returns:
        List of project metadata dictionaries with ID, name, workspace_path,
        description, and timestamps.
    """
    import scifi.server as srv

    store = srv.get_literature_store()
    projects = store.list_projects()
    return [p.to_dict() for p in projects]


@mcp.tool()
def scifi_get_project_summary(
    project_name_or_path: str | None = None,
) -> dict[str, Any]:
    """
    Retrieve project statistics, paper counts, open-access distribution,
    and reprint requests for a registered project workspace.
    If project_name_or_path is omitted, auto-discovers from current working directory.

    Args:
        project_name_or_path: Optional project name, ID, or workspace path.

    Returns:
        Dictionary with status, project metadata, paper counts, open access counts,
        and pending reprint requests.
    """
    import scifi.server as srv

    store = srv.get_literature_store()
    proj = _resolve_project(store, project_name_or_path)
    if proj is None:
        return {
            "status": "NOT_FOUND",
            "message": f"Project '{project_name_or_path or Path.cwd()}' not found.",
            "available_projects": [p.name for p in store.list_projects()],
        }

    papers = store.get_project_papers(proj.id)
    reprints = store.get_reprint_requests(project_id=proj.id)

    oa_count = sum(1 for p in papers if any(loc.is_oa for loc in p.locations))
    paywalled_count = len(papers) - oa_count
    pending_reprints = [r for r in reprints if r.status in ("DRAFT_READY", "SENT")]
    received_reprints = [r for r in reprints if r.status == "RECEIVED"]

    return {
        "status": "SUCCESS",
        "project": proj.to_dict(),
        "total_papers": len(papers),
        "open_access_papers": oa_count,
        "paywalled_papers": paywalled_count,
        "total_reprint_requests": len(reprints),
        "pending_reprints_count": len(pending_reprints),
        "received_reprints_count": len(received_reprints),
        "pending_reprints": [r.to_dict() for r in pending_reprints],
    }


@mcp.tool()
def scifi_draft_reprint_request(
    identifier: str,
    project_name: str | None = None,
) -> dict[str, Any]:
    """
    Generate an academic-standard author reprint request letter and mailto URL
    for a paywalled paper. Queries public registries for author contact and saves
    the draft to the central literature store.

    Args:
        identifier: DOI or paper identifier (e.g. '10.1016/j.neucom.2023.12345').
        project_name: Optional project name, ID, or workspace path to link with.

    Returns:
        Dictionary containing status ('DRAFT_READY' or 'ERROR'), subject, body,
        mailto_url, author_name, and author_email.
    """
    import scifi.server as srv

    store = srv.get_literature_store()
    if project_name:
        if str(project_name).strip().lower() == "all":
            proj_id = None
        else:
            proj = _resolve_project(store, project_name)
            if proj is None:
                return {
                    "status": "ERROR",
                    "message": f"Project '{project_name}' not found.",
                    "identifier": identifier,
                }
            proj_id = proj.id
    else:
        proj = _resolve_project(store, None)
        proj_id = proj.id if proj else None

    try:
        req = prepare_reprint_for_paper(
            store=store,
            project_id=proj_id,
            paper_id=identifier,
        )
        return req.to_dict()
    except Exception as e:
        logger.error("Failed drafting reprint request for %s: %s", identifier, e)
        return {
            "status": "ERROR",
            "message": str(e),
            "identifier": identifier,
        }


@mcp.tool()
def scifi_list_pending_reprints(
    project_name: str | None = None,
) -> list[dict[str, Any]]:
    """
    List pending reprint requests awaiting author responses (status DRAFT_READY or SENT).

    Args:
        project_name: Optional project name, ID, or workspace path filter.

    Returns:
        List of reprint request dictionaries.
    """
    import scifi.server as srv

    store = srv.get_literature_store()
    if project_name:
        if str(project_name).strip().lower() == "all":
            proj_id = None
        else:
            proj = _resolve_project(store, project_name)
            if proj is None:
                return []
            proj_id = proj.id
    else:
        proj = _resolve_project(store, None)
        proj_id = proj.id if proj else None

    requests = store.get_reprint_requests(project_id=proj_id)
    return [r.to_dict() for r in requests if r.status in ("DRAFT_READY", "SENT")]


@mcp.tool()
def scifi_ingest_paper_pdf(
    identifier: str,
    pdf_path: str,
    project_name: str | None = None,
) -> dict[str, Any]:
    """
    Ingest an acquired paper PDF copy into the content-addressed central store.
    Marks the paper location as accessible OA and transitions associated reprint
    requests to RECEIVED.

    Args:
        identifier: DOI or paper identifier.
        pdf_path: Local filesystem path to the PDF file.
        project_name: Optional project name, ID, or workspace path to link paper to.

    Returns:
        Dictionary with status ('SUCCESS' or 'ERROR'), stored_path, sha256, and paper_id.
    """
    import scifi.server as srv

    store = srv.get_literature_store()
    if project_name:
        if str(project_name).strip().lower() == "all":
            proj_id = None
        else:
            proj = _resolve_project(store, project_name)
            if proj is None:
                return {
                    "status": "ERROR",
                    "message": f"Project '{project_name}' not found.",
                    "identifier": identifier,
                }
            proj_id = proj.id
    else:
        proj = _resolve_project(store, None)
        proj_id = proj.id if proj else None

    try:
        return ingest_paper_copy(
            store=store,
            project_id=proj_id,
            paper_id=identifier,
            pdf_path=pdf_path,
        )
    except Exception as e:
        logger.error("Failed ingesting paper PDF %s: %s", pdf_path, e)
        return {
            "status": "ERROR",
            "message": str(e),
            "identifier": identifier,
            "pdf_path": pdf_path,
        }
