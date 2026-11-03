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
from pathlib import Path
import sys
import webbrowser
from typing import Optional

from scifi.literature.lineage import LineageCrawler
from scifi.literature.reporter import save_bibtex_file, save_markdown_report
from scifi.literature.store import LiteratureStore
from scifi.literature.visualizer import save_interactive_html

DEFAULT_DB_PATH = Path(".scifi/literature_store.db")


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


def cmd_report(args: argparse.Namespace) -> int:
    """Execute lineage crawl and generate markdown report, HTML map, and BibTeX file."""
    db_path = getattr(args, "db", str(DEFAULT_DB_PATH))
    store = LiteratureStore(db_path)
    crawler = LineageCrawler(store=store)

    graph_id, papers, citations = crawler.crawl_lineage(
        query=args.query,
        depth=args.depth,
        max_papers=args.max_papers,
    )

    if not papers:
        print(f"[ERROR] Could not resolve seed paper or find literature for query: '{args.query}'", file=sys.stderr)
        return 1

    depths = crawler.compute_topological_depths(papers, citations)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    title = papers[0].title if papers else args.query
    seed_id = papers[0].id if papers else None

    md_path = save_markdown_report(out_dir / "literature_report.md", graph_title=title, papers=papers, citations=citations, depths=depths)
    html_path = save_interactive_html(out_dir / "literature_map.html", graph_title=title, papers=papers, citations=citations, depths=depths, seed_paper_id=seed_id)
    bib_path = save_bibtex_file(out_dir / "references.bib", papers=papers)

    print(f"[SUCCESS] Literature report generated in {out_dir}:")
    print(f"  Report:   {md_path}")
    print(f"  Map:      {html_path}")
    print(f"  BibTeX:   {bib_path}")
    print(f"  Summary:  {len(papers)} papers, {len(citations)} citations (Session: {graph_id})")

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
    )

    if not papers:
        print(f"[ERROR] Could not resolve seed paper or find literature for query: '{args.query}'", file=sys.stderr)
        return 1

    depths = crawler.compute_topological_depths(papers, citations)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    title = papers[0].title if papers else args.query
    seed_id = papers[0].id if papers else None

    html_path = save_interactive_html(
        out_dir / "literature_map.html",
        graph_title=title,
        papers=papers,
        citations=citations,
        depths=depths,
        seed_paper_id=seed_id,
    )

    print(f"[SUCCESS] Literature map generated: {html_path} ({len(papers)} papers, {len(citations)} citations, Session: {graph_id})")

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


def cmd_literature(args: argparse.Namespace, parser: Optional[argparse.ArgumentParser] = None) -> int:
    """Dispatch literature subcommands."""
    lit_cmd = getattr(args, "lit_command", None)
    if not lit_cmd:
        if parser:
            parser.print_help()
        else:
            print("usage: scifi literature [-h] {report,map,db} ...")
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

    return 0


__all__ = [
    "DEFAULT_DB_PATH",
    "cmd_db_export_bib",
    "cmd_db_list_graphs",
    "cmd_literature",
    "cmd_map",
    "cmd_report",
    "register_literature_subparsers",
]
