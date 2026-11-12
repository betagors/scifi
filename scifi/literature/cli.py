"""
Command-Line Interface subcommands for SciFi Literature Discovery & Lineage Engine.

Provides unified CLI entrypoints for:
- report: Crawl lineage, generate publication-ready markdown report, interactive HTML map, and references.bib
- map: Crawl lineage, generate standalone Vis.js interactive HTML map
- db list-graphs: List registered literature graph sessions
- db export-bib: Export sanitized BibTeX references for a specific graph session
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from scifi.literature.lineage import LineageCrawler
from scifi.literature.reporter import save_bibtex_file, save_markdown_report
from scifi.literature.store import DEFAULT_CENTRAL_STORE_PATH, LiteratureStore
from scifi.literature.visualizer import save_interactive_html

DEFAULT_DB_PATH = Path(".scifi/literature_store.db")


def _resolve_project_id(
    store: LiteratureStore,
    project_name_or_path: str | Path | None = None,
) -> str | None:
    """
    Resolve a project ID from an ID, name, or workspace path.
    If project_name_or_path is omitted, auto-discovers from current working directory.
    """
    if project_name_or_path:
        target_str = str(project_name_or_path).strip()
        if target_str.lower() == "all":
            return None
        # 1. Exact ID match
        proj = store.get_project(target_str)
        if proj is not None:
            return proj.id
        # 2. Canonical workspace path match
        target_path = Path(target_str).resolve()
        proj = store.get_project_by_workspace(target_path)
        if proj is not None:
            return proj.id
        # 3. Match name or directory name
        for p in store.list_projects():
            if p.name.lower() == target_str.lower():
                return p.id
            if Path(p.workspace_path).name.lower() == target_str.lower():
                return p.id
            try:
                if Path(p.workspace_path).resolve() == target_path:
                    return p.id
            except Exception:
                pass
        return None

    # Auto-discover from Path.cwd()
    cwd = Path.cwd().resolve()
    proj = store.get_project_by_workspace(cwd)
    if proj is not None:
        return proj.id
    for p in store.list_projects():
        try:
            if Path(p.workspace_path).resolve() == cwd:
                return p.id
        except Exception:
            pass
    if (cwd / ".scifi").is_dir():
        proj = store.get_project_by_workspace(cwd)
        if proj is None:
            manifest_file = cwd / ".scifi" / "literature_manifest.json"
            if manifest_file.exists():
                try:
                    from scifi.literature.manifest import sync_workspace

                    proj = sync_workspace(store, cwd)
                except Exception:
                    proj = store.register_project(name=cwd.name, workspace_path=cwd)
            else:
                proj = store.register_project(name=cwd.name, workspace_path=cwd)
        if proj is not None:
            return proj.id

    # Walk up parent directories to find containing project
    for parent in cwd.parents:
        proj = store.get_project_by_workspace(parent)
        if proj is not None:
            return proj.id
        for p in store.list_projects():
            try:
                if Path(p.workspace_path).resolve() == parent:
                    return p.id
            except Exception:
                pass
        if (parent / ".scifi").is_dir():
            proj = store.get_project_by_workspace(parent)
            if proj is None:
                manifest_file = parent / ".scifi" / "literature_manifest.json"
                if manifest_file.exists():
                    try:
                        from scifi.literature.manifest import sync_workspace

                        proj = sync_workspace(store, parent)
                    except Exception:
                        proj = store.register_project(name=parent.name, workspace_path=parent)
                else:
                    proj = store.register_project(name=parent.name, workspace_path=parent)
            if proj is not None:
                return proj.id
    return None


def register_literature_subparsers(parser: argparse.ArgumentParser) -> None:
    """Register all literature subcommands on the provided parser or subparser."""
    lit_subparsers = parser.add_subparsers(dest="lit_command", help="Literature subcommand")

    # 1. report
    p_report = lit_subparsers.add_parser(
        "report",
        help="Crawl lineage and generate markdown report, interactive map, and references.bib",
    )
    p_report.add_argument("query", help="Seed query, paper title, DOI, or arXiv identifier")
    p_report.add_argument("--depth", type=int, default=2, help="Lineage crawl depth (default: 2)")
    p_report.add_argument("--max-papers", type=int, default=25, help="Maximum papers to discover (default: 25)")
    p_report.add_argument(
        "--output-dir",
        default="./literature_review",
        help="Output directory (default: ./literature_review)",
    )
    p_report.add_argument("--open", action="store_true", help="Open generated interactive map in default web browser")
    p_report.add_argument("--min-year", type=int, default=None, help="Minimum publication year filter (e.g. 2020)")
    p_report.add_argument("--max-year", type=int, default=None, help="Maximum publication year filter (e.g. 2026)")
    p_report.add_argument(
        "--venue-tier",
        choices=["all", "top"],
        default="all",
        help="Venue prestige tier filter (default: all)",
    )
    p_report.add_argument(
        "--require-evidence",
        action="store_true",
        help="Only retain papers with verifiable benchmarks or self-reported limitations",
    )
    p_report.add_argument(
        "--pdf-dir",
        default=None,
        help="Directory containing local PDF papers to ingest and match (e.g. workspace/papers)",
    )
    p_report.add_argument(
        "--auto-fetch-pdf",
        action="store_true",
        help="Automatically download open-access paper PDFs via arXiv and Unpaywall",
    )
    p_report.add_argument(
        "--no-fulltext",
        action="store_true",
        help="Disable full-text section extraction from PDFs",
    )
    p_report.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help=f"Path to SQLite knowledge store (default: {DEFAULT_DB_PATH})",
    )

    # 2. map
    p_map = lit_subparsers.add_parser(
        "map",
        help="Crawl lineage and generate interactive HTML visualization map",
    )
    p_map.add_argument("query", help="Seed query, paper title, DOI, or arXiv identifier")
    p_map.add_argument("--depth", type=int, default=2, help="Lineage crawl depth (default: 2)")
    p_map.add_argument("--max-papers", type=int, default=25, help="Maximum papers to discover (default: 25)")
    p_map.add_argument(
        "--output-dir",
        default="./literature_review",
        help="Output directory (default: ./literature_review)",
    )
    p_map.add_argument("--open", action="store_true", help="Open generated interactive map in default web browser")
    p_map.add_argument("--min-year", type=int, default=None, help="Minimum publication year filter (e.g. 2020)")
    p_map.add_argument("--max-year", type=int, default=None, help="Maximum publication year filter (e.g. 2026)")
    p_map.add_argument(
        "--venue-tier",
        choices=["all", "top"],
        default="all",
        help="Venue prestige tier filter (default: all)",
    )
    p_map.add_argument(
        "--require-evidence",
        action="store_true",
        help="Only retain papers with verifiable benchmarks or self-reported limitations",
    )
    p_map.add_argument(
        "--pdf-dir",
        default=None,
        help="Directory containing local PDF papers to ingest and match (e.g. workspace/papers)",
    )
    p_map.add_argument(
        "--auto-fetch-pdf",
        action="store_true",
        help="Automatically download open-access paper PDFs via arXiv and Unpaywall",
    )
    p_map.add_argument(
        "--no-fulltext",
        action="store_true",
        help="Disable full-text section extraction from PDFs",
    )
    p_map.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help=f"Path to SQLite knowledge store (default: {DEFAULT_DB_PATH})",
    )

    # 3. db
    p_db = lit_subparsers.add_parser(
        "db",
        help="Query and manage literature knowledge store sessions",
    )
    db_subparsers = p_db.add_subparsers(dest="db_command", help="Database operation")

    # db list-graphs
    p_list = db_subparsers.add_parser(
        "list-graphs",
        help="List all registered literature graph sessions",
    )
    p_list.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help=f"Path to SQLite knowledge store (default: {DEFAULT_DB_PATH})",
    )

    # db export-bib
    p_export = db_subparsers.add_parser(
        "export-bib",
        help="Export BibTeX entries for a specific graph session",
    )
    p_export.add_argument("--graph-id", required=True, help="Graph session ID to export")
    p_export.add_argument("-o", "--output", required=True, help="Destination .bib file path")
    p_export.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help=f"Path to SQLite knowledge store (default: {DEFAULT_DB_PATH})",
    )

    # 4. sync
    p_sync = lit_subparsers.add_parser(
        "sync",
        help="Synchronize workspace with central literature store",
    )
    p_sync.add_argument(
        "--workspace",
        default=None,
        help="Path to project workspace (default: current working directory)",
    )
    p_sync.add_argument(
        "--db",
        default=str(DEFAULT_CENTRAL_STORE_PATH),
        help=f"Path to SQLite knowledge store (default: {DEFAULT_CENTRAL_STORE_PATH})",
    )

    # 5. reprint
    p_reprint = lit_subparsers.add_parser(
        "reprint",
        help="Generate author reprint request draft and mailto URL for paywalled paper",
    )
    p_reprint.add_argument("identifier", help="DOI or paper identifier")
    p_reprint.add_argument(
        "--project",
        default=None,
        help="Project name, ID, or workspace path (default: current working directory)",
    )
    p_reprint.add_argument("--email", default=None, help="Explicit corresponding author email")
    p_reprint.add_argument("--name", default=None, help="Explicit corresponding author name")
    p_reprint.add_argument("--affiliation", default=None, help="Explicit corresponding author affiliation")
    p_reprint.add_argument(
        "--db",
        default=str(DEFAULT_CENTRAL_STORE_PATH),
        help=f"Path to SQLite knowledge store (default: {DEFAULT_CENTRAL_STORE_PATH})",
    )

    # 6. reprints
    p_reprints = lit_subparsers.add_parser(
        "reprints",
        help="List reprint requests with optional project or status filtering",
    )
    p_reprints.add_argument(
        "--project",
        default=None,
        help="Filter by project name, ID, or workspace path",
    )
    p_reprints.add_argument(
        "--status",
        default=None,
        help="Filter by status (DRAFT_READY, SENT, RECEIVED, DECLINED)",
    )
    p_reprints.add_argument(
        "--db",
        default=str(DEFAULT_CENTRAL_STORE_PATH),
        help=f"Path to SQLite knowledge store (default: {DEFAULT_CENTRAL_STORE_PATH})",
    )
    p_reprints.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON",
    )

    # 7. ingest-pdf
    p_ingest = lit_subparsers.add_parser(
        "ingest-pdf",
        help="Ingest a local PDF into the content-addressed central store",
    )
    p_ingest.add_argument("--doi", required=True, help="DOI or paper identifier")
    p_ingest.add_argument("--pdf", required=True, help="Path to local PDF file")
    p_ingest.add_argument(
        "--project",
        default=None,
        help="Project name, ID, or workspace path",
    )
    p_ingest.add_argument(
        "--db",
        default=str(DEFAULT_CENTRAL_STORE_PATH),
        help=f"Path to SQLite knowledge store (default: {DEFAULT_CENTRAL_STORE_PATH})",
    )


def cmd_report(args: argparse.Namespace) -> int:
    """Execute lineage crawl and generate markdown report, HTML map, and BibTeX file."""
    db_path = getattr(args, "db", str(DEFAULT_DB_PATH))
    store = LiteratureStore(db_path)
    crawler = LineageCrawler(store=store)

    graph_id, papers, citations = crawler.crawl_lineage(
        query=args.query,
        depth=args.depth,
        max_papers=args.max_papers,
        min_year=getattr(args, "min_year", None),
        max_year=getattr(args, "max_year", None),
        venue_tier=getattr(args, "venue_tier", None),
        require_evidence=bool(getattr(args, "require_evidence", False)),
        extract_fulltext_gaps=not getattr(args, "no_fulltext", False),
        pdf_dir=getattr(args, "pdf_dir", None),
        auto_fetch_pdf=bool(getattr(args, "auto_fetch_pdf", False)),
    )

    if not papers:
        print(f"[ERROR] Could not resolve seed paper or find literature for query: '{args.query}'", file=sys.stderr)
        return 1

    depths = crawler.compute_topological_depths(papers, citations)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    title = papers[0].title if papers else args.query
    seed_id = papers[0].id if papers else None

    paper_gaps = store.get_graph_gaps(graph_id)
    evidence_map = store.get_graph_evidence(graph_id)
    benchmark_results = store.get_graph_benchmark_results(graph_id)
    benchmarks_map = store.get_graph_benchmarks(graph_id)
    metrics_map = store.get_graph_metrics(graph_id)
    conditions_map = store.get_graph_conditions(graph_id)

    md_path = save_markdown_report(
        out_dir / "literature_report.md",
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
    html_path = save_interactive_html(
        out_dir / "literature_map.html",
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
    bib_path = save_bibtex_file(out_dir / "references.bib", papers=papers)

    total_gaps = sum(len(glist) for glist in paper_gaps.values())
    corroborated_gaps = sum(
        1 for glist in paper_gaps.values() for g in glist if g.verification_status == "corroborated"
    )
    total_results = sum(len(rlist) for rlist in benchmark_results.values())
    n_benchmarks = len(benchmarks_map)
    n_sota_leaders = sum(1 for rlist in benchmark_results.values() for r in rlist if r.is_sota)

    print(f"[SUCCESS] Literature report generated in {out_dir}:")
    print(f"  Report:   {md_path}")
    print(f"  Map:      {html_path}")
    print(f"  BibTeX:   {bib_path}")
    print(f"  Summary:  {len(papers)} papers, {len(citations)} citations (Session: {graph_id})")
    print(f"  Evidence: {total_gaps} extracted technical limitations ({corroborated_gaps} corroborated)")
    print(f"  Benchmarks: {total_results} results across {n_benchmarks} benchmarks ({n_sota_leaders} SOTA leaders)")

    if getattr(args, "open", False):
        webbrowser.open(html_path.resolve().as_uri())

    return 0


def cmd_map(args: argparse.Namespace) -> int:
    """Execute lineage crawl and generate standalone interactive HTML map."""
    db_path = getattr(args, "db", str(DEFAULT_DB_PATH))
    store = LiteratureStore(db_path)
    crawler = LineageCrawler(store=store)

    graph_id, papers, citations = crawler.crawl_lineage(
        query=args.query,
        depth=args.depth,
        max_papers=args.max_papers,
        min_year=getattr(args, "min_year", None),
        max_year=getattr(args, "max_year", None),
        venue_tier=getattr(args, "venue_tier", None),
        require_evidence=bool(getattr(args, "require_evidence", False)),
        extract_fulltext_gaps=not getattr(args, "no_fulltext", False),
        pdf_dir=getattr(args, "pdf_dir", None),
        auto_fetch_pdf=bool(getattr(args, "auto_fetch_pdf", False)),
    )

    if not papers:
        print(f"[ERROR] Could not resolve seed paper or find literature for query: '{args.query}'", file=sys.stderr)
        return 1

    depths = crawler.compute_topological_depths(papers, citations)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    title = papers[0].title if papers else args.query
    seed_id = papers[0].id if papers else None

    paper_gaps = store.get_graph_gaps(graph_id)
    evidence_map = store.get_graph_evidence(graph_id)
    benchmark_results = store.get_graph_benchmark_results(graph_id)
    benchmarks_map = store.get_graph_benchmarks(graph_id)
    metrics_map = store.get_graph_metrics(graph_id)
    conditions_map = store.get_graph_conditions(graph_id)

    html_path = save_interactive_html(
        out_dir / "literature_map.html",
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

    total_gaps = sum(len(glist) for glist in paper_gaps.values())
    corroborated_gaps = sum(
        1 for glist in paper_gaps.values() for g in glist if g.verification_status == "corroborated"
    )
    total_results = sum(len(rlist) for rlist in benchmark_results.values())
    n_benchmarks = len(benchmarks_map)
    n_sota_leaders = sum(1 for rlist in benchmark_results.values() for r in rlist if r.is_sota)

    print(
        f"[SUCCESS] Literature map generated: {html_path} ({len(papers)} papers, {len(citations)} citations, Session: {graph_id})"
    )
    print(f"  Evidence: {total_gaps} extracted technical limitations ({corroborated_gaps} corroborated)")
    print(f"  Benchmarks: {total_results} results across {n_benchmarks} benchmarks ({n_sota_leaders} SOTA leaders)")

    if getattr(args, "open", False):
        webbrowser.open(html_path.resolve().as_uri())

    return 0


def cmd_db_list_graphs(args: argparse.Namespace) -> int:
    """List all registered literature graph sessions."""
    db_path = getattr(args, "db", str(DEFAULT_DB_PATH))
    store = LiteratureStore(db_path)
    graphs = store.list_graphs()

    if not graphs:
        print("No literature graphs found in database.")
        return 0

    print(f"{'Graph ID':<24} | {'Created At':<19} | {'Seed Paper ID':<15} | Title")
    print("-" * 80)
    for g in graphs:
        seed = g.seed_paper_id or "N/A"
        created = g.created_at[:19] if g.created_at else "N/A"
        print(f"{g.id:<24} | {created:<19} | {seed:<15} | {g.title}")
    return 0


def cmd_db_export_bib(args: argparse.Namespace) -> int:
    """Export BibTeX entries for a specific graph session."""
    db_path = getattr(args, "db", str(DEFAULT_DB_PATH))
    store = LiteratureStore(db_path)
    papers = store.get_graph_papers(args.graph_id)

    if not papers:
        print(f"[ERROR] No papers found for graph session '{args.graph_id}'", file=sys.stderr)
        return 1

    out_path = save_bibtex_file(args.output, papers)
    print(f"[SUCCESS] Exported {len(papers)} BibTeX entries to {out_path}")
    return 0


def cmd_literature_sync(args: argparse.Namespace) -> int:
    """Synchronize a project workspace with the central knowledge store."""
    from scifi.literature.manifest import sync_workspace

    ws_arg = getattr(args, "workspace", None)
    ws = Path(ws_arg).resolve() if ws_arg else Path.cwd().resolve()
    db_path = getattr(args, "db", None) or str(DEFAULT_CENTRAL_STORE_PATH)
    store = LiteratureStore(db_path)

    try:
        proj = sync_workspace(store, ws)
        print(f"[SUCCESS] Synchronized workspace '{proj.name}' (Project ID: {proj.id})")
        print(f"  Workspace: {proj.workspace_path}")
        print(f"  Manifest:  {ws / '.scifi' / 'literature_manifest.json'}")
        print(f"  BibTeX:    {ws / '.scifi' / 'references.bib'}")
        return 0
    except Exception as e:
        print(f"[ERROR] Sync failed: {e}", file=sys.stderr)
        return 1


def cmd_literature_reprint(args: argparse.Namespace) -> int:
    """Draft an author reprint request letter and mailto URL."""
    from scifi.literature.reprint import prepare_reprint_for_paper

    db_path = getattr(args, "db", None) or str(DEFAULT_CENTRAL_STORE_PATH)
    store = LiteratureStore(db_path)
    proj_arg = getattr(args, "project", None)
    proj_id = _resolve_project_id(store, proj_arg)

    try:
        record = prepare_reprint_for_paper(
            store=store,
            project_id=proj_id,
            paper_id=args.identifier,
            author_name=getattr(args, "name", None),
            author_email=getattr(args, "email", None),
            author_affiliation=getattr(args, "affiliation", None),
        )
        print(f"[SUCCESS] Reprint draft ready for '{args.identifier}':")
        print(f"  Author:   {record.author_name} <{record.author_email or 'unlisted'}>")
        print(f"  Status:   {record.status}")
        print(f"  Subject:  {record.subject}")
        if record.mailto_url:
            print(f"  Mailto:   {record.mailto_url}")
        print("\n--- Message Body ---")
        print(record.body)
        return 0
    except Exception as e:
        print(f"[ERROR] Failed to draft reprint request: {e}", file=sys.stderr)
        return 1


def cmd_literature_reprints(args: argparse.Namespace) -> int:
    """List reprint requests from the central store."""
    db_path = getattr(args, "db", None) or str(DEFAULT_CENTRAL_STORE_PATH)
    store = LiteratureStore(db_path)
    proj_arg = getattr(args, "project", None)
    if proj_arg:
        if str(proj_arg).strip().lower() == "all":
            proj_id = None
        else:
            proj_id = _resolve_project_id(store, proj_arg)
            if not proj_id:
                print(f"[WARNING] Project '{proj_arg}' not found.", file=sys.stderr)
                return 0
    else:
        proj_id = None

    status_filter = getattr(args, "status", None)
    if status_filter:
        status_filter = status_filter.upper()

    reprints = store.get_reprint_requests(project_id=proj_id, status=status_filter)

    if getattr(args, "json", False):
        print(json.dumps([r.to_dict() for r in reprints], indent=2))
        return 0

    if not reprints:
        print("No reprint requests found.")
        return 0

    print(f"{'ID':<16} | {'Status':<11} | {'Paper ID':<30} | {'Author':<20} | {'Email'}")
    print("-" * 100)
    for r in reprints:
        email = r.author_email or "N/A"
        raw_author = r.author_name or "Unknown"
        author = (raw_author[:18] + "..") if len(raw_author) > 20 else raw_author
        paper = (r.paper_id[:28] + "..") if len(r.paper_id) > 30 else r.paper_id
        print(f"{r.id:<16} | {r.status:<11} | {paper:<30} | {author:<20} | {email}")
    return 0


def cmd_literature_ingest_pdf(args: argparse.Namespace) -> int:
    """Ingest a local PDF into the content-addressed central store."""
    from scifi.literature.reprint import ingest_paper_copy

    db_path = getattr(args, "db", None) or str(DEFAULT_CENTRAL_STORE_PATH)
    store = LiteratureStore(db_path)
    proj_arg = getattr(args, "project", None)
    proj_id = _resolve_project_id(store, proj_arg)

    try:
        res = ingest_paper_copy(
            store=store,
            project_id=proj_id,
            paper_id=args.doi,
            pdf_path=args.pdf,
        )
        print(f"[SUCCESS] Ingested PDF for {args.doi}:")
        print(f"  Stored: {res['stored_path']}")
        print(f"  SHA256: {res['sha256']}")
        return 0
    except Exception as e:
        print(f"[ERROR] Failed to ingest PDF: {e}", file=sys.stderr)
        return 1


def cmd_literature(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Dispatch literature subcommands."""
    lit_cmd = getattr(args, "lit_command", None)
    if not lit_cmd:
        if parser:
            parser.print_help()
        else:
            print("usage: scifi literature [-h] {report,map,db,sync,reprint,reprints,ingest-pdf} ...")
        return 0

    if lit_cmd == "report":
        return cmd_report(args)
    elif lit_cmd == "map":
        return cmd_map(args)
    elif lit_cmd == "db":
        db_cmd = getattr(args, "db_command", None)
        if not db_cmd:
            print("usage: scifi literature db [-h] {list-graphs,export-bib} ...")
            return 0
        if db_cmd == "list-graphs":
            return cmd_db_list_graphs(args)
        elif db_cmd == "export-bib":
            return cmd_db_export_bib(args)
    elif lit_cmd == "sync":
        return cmd_literature_sync(args)
    elif lit_cmd == "reprint":
        return cmd_literature_reprint(args)
    elif lit_cmd == "reprints":
        return cmd_literature_reprints(args)
    elif lit_cmd == "ingest-pdf":
        return cmd_literature_ingest_pdf(args)

    return 0


__all__ = [
    "DEFAULT_CENTRAL_STORE_PATH",
    "DEFAULT_DB_PATH",
    "cmd_db_export_bib",
    "cmd_db_list_graphs",
    "cmd_literature",
    "cmd_literature_ingest_pdf",
    "cmd_literature_reprint",
    "cmd_literature_reprints",
    "cmd_literature_sync",
    "cmd_map",
    "cmd_report",
    "register_literature_subparsers",
]
