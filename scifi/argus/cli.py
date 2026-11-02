"""
Command-line interface for the Argus Attribution & Plagiarism Audit Engine.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import ArgusEngine
from .models import SuggestedAction
from .patcher import append_bibtex_entry, generate_reformulate_prompt, insert_cite_into_latex


def cmd_audit(args: argparse.Namespace) -> int:
    target_path = Path(args.file)
    if not target_path.exists():
        print(f"Error: Target file '{target_path}' not found.", file=sys.stderr)
        return 1

    engine = ArgusEngine(
        author_whitelist=args.author_whitelist,
        preprint_doi=args.preprint_doi,
        enable_search=not args.no_search,
    )

    report = engine.audit_file(target_path)

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    elif args.format == "markdown":
        print(report.summary_markdown())
    else:
        print(f"Argus Audit: {report.source_file}")
        print(f"Total findings: {report.total_findings}")
        for f in report.findings:
            print(f"[{f.id}] Line {f.line_number}: {f.category.value} -> {f.suggested_action.value} ({f.matched_entity})")
            print(f"       Hint: {f.remediation_hint}")

    # Automated / interactive fix
    if args.fix:
        bib_path = Path(args.bib) if args.bib else target_path.parent / "references.bib"
        fixed_count = 0
        for f in report.findings:
            if f.suggested_action == SuggestedAction.CITE and f.cite_key and f.bibtex_entry:
                if f.line_number:
                    insert_cite_into_latex(
                        target_path,
                        line_number=f.line_number,
                        cite_key=f.cite_key,
                        target_entity=f.matched_entity,
                    )
                append_bibtex_entry(bib_path, f.bibtex_entry, f.cite_key)
                fixed_count += 1
                print(f"[FIXED] Inserted \\cite{{{f.cite_key}}} and updated {bib_path.name}")
            elif f.suggested_action == SuggestedAction.REFORMULATE:
                print(f"[PROMPT TO REFORMULATE] Generated instructions for 'human' skill:")
                print(generate_reformulate_prompt(f))

        print(f"\nCompleted: {fixed_count} citations injected and verified.")

    return 0 if report.total_findings == 0 else 2


def cmd_scan(args: argparse.Namespace) -> int:
    engine = ArgusEngine(
        author_whitelist=args.author_whitelist,
        preprint_doi=args.preprint_doi,
        enable_search=not args.no_search,
    )
    report = engine.audit_text(args.text, source_file="CLI_Input")

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.summary_markdown())

    return 0 if report.total_findings == 0 else 2


def cmd_search(args: argparse.Namespace) -> int:
    from .searcher import ArgusSearcher

    searcher = ArgusSearcher()
    res = searcher.search_canonical_work(args.query)
    if not res:
        print(f"No canonical academic work found for '{args.query}'.", file=sys.stderr)
        return 1

    metadata, confidence, _ = res
    cite_key = metadata.generate_cite_key()
    bibtex = metadata.to_bibtex(key=cite_key)

    if args.format == "json":
        print(json.dumps({
            "query": args.query,
            "confidence": confidence,
            "metadata": metadata.to_dict(),
            "cite_key": cite_key,
            "bibtex": bibtex,
        }, indent=2))
    elif args.format == "bibtex":
        print(bibtex)
    else:
        print(f"Found canonical work for: '{args.query}' (Confidence: {confidence:.0%})")
        print(f"Title:    {metadata.title}")
        print(f"Authors:  {', '.join([a.name for a in metadata.authors[:3]])}")
        print(f"Year:     {metadata.year}")
        print(f"DOI:      {metadata.canonical_doi}")
        print(f"Cite Key: \\cite{{{cite_key}}}")
        print("\nBibTeX:\n" + bibtex)

    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        prog="scifi-argus",
        description="Argus: Sentinel for Academic Attribution, Uncredited Methods, and Plagiarism Detection.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Argus subcommand to execute")

    # audit
    p_audit = subparsers.add_parser("audit", help="Audit a LaTeX (.tex) or text file for attribution gaps")
    p_audit.add_argument("file", help="Path to LaTeX (.tex) or markdown/text file")
    p_audit.add_argument("--bib", help="Path to target references.bib file")
    p_audit.add_argument("--format", choices=["markdown", "json", "text"], default="markdown")
    p_audit.add_argument("--fix", action="store_true", help="Automatically insert \\cite and append BibTeX")
    p_audit.add_argument("--author-whitelist", nargs="*", help="Author names to whitelist against self-plagiarism flags")
    p_audit.add_argument("--preprint-doi", help="DOI of author's preprint")
    p_audit.add_argument("--no-search", action="store_true", help="Skip remote registry lookups")

    # scan
    p_scan = subparsers.add_parser("scan", help="Scan raw text string for uncredited methods or informal tropes")
    p_scan.add_argument("text", help="Text passage to scan")
    p_scan.add_argument("--format", choices=["markdown", "json", "text"], default="markdown")
    p_scan.add_argument("--author-whitelist", nargs="*")
    p_scan.add_argument("--preprint-doi")
    p_scan.add_argument("--no-search", action="store_true")

    # search
    p_search = subparsers.add_parser("search", help="Look up canonical academic paper for a method or phrase")
    p_search.add_argument("query", help="Method, algorithm name, or phrase")
    p_search.add_argument("--format", choices=["markdown", "json", "bibtex"], default="markdown")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    if args.command == "audit":
        return cmd_audit(args)
    elif args.command == "scan":
        return cmd_scan(args)
    elif args.command == "search":
        return cmd_search(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
