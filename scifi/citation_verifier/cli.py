"""
Command-line interface for SciFi Citation Verifier.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import audit_bib_file, generate_sanitized_bib, verify_citation
from .bib_auditor import search_identifier_by_title
from .models import VerificationStatus


def cmd_verify(args: argparse.Namespace) -> int:
    query = args.query
    if not query:
        print("Error: query (DOI or URL) is required.", file=sys.stderr)
        return 1

    result = verify_citation(
        query=query,
        claimed_title=args.claimed_title,
        claimed_year=args.claimed_year,
        claimed_author=args.claimed_author,
        claimed_venue=args.claimed_venue,
        timeout=args.timeout,
    )

    fmt = args.format.lower()
    if fmt == "json":
        print(json.dumps(result.to_dict(), indent=2))
    elif fmt == "bibtex":
        print(result.to_bibtex())
    elif fmt == "apa":
        print(result.to_apa())
    elif fmt == "markdown":
        print(result.summary_markdown())
    else:  # plain text
        print(f"Status: {result.status.value}")
        print(f"Title: {result.title}")
        print(f"Authors: {', '.join([a.name for a in result.authors])}")
        print(f"Year: {result.year}")
        print(f"Venue: {result.venue}")
        print(f"DOI: {result.canonical_doi}")
        print(f"URL: {result.canonical_url}")
        print(f"Retracted: {result.is_retracted}")
        if result.discrepancies:
            print("Discrepancies:")
            for d in result.discrepancies:
                print(f"  - [{d.severity.value}] {d.field}: {d.message}")

    if result.status == VerificationStatus.RETRACTED:
        return 2
    if result.status == VerificationStatus.UNRESOLVED:
        return 1
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    bib_path = Path(args.bib_file)
    if not bib_path.exists():
        print(f"Error: BibTeX file '{bib_path}' not found.", file=sys.stderr)
        return 1

    report = audit_bib_file(bib_path, search_missing=not args.no_search)

    if args.format == "json":
        data = {
            "file": str(bib_path),
            "total_entries": report.total_entries,
            "verified_count": report.verified_count,
            "retracted_count": report.retracted_count,
            "errata_count": report.errata_count,
            "mismatch_count": report.mismatch_count,
            "unresolved_count": report.unresolved_count,
            "entries": [e.to_dict() for e in report.entries],
        }
        output_str = json.dumps(data, indent=2)
    else:
        output_str = report.summary_markdown()

    if args.output_report:
        Path(args.output_report).write_text(output_str, encoding="utf-8")
        print(f"Audit report saved to: {args.output_report}")
    else:
        print(output_str)

    if args.output_bib:
        sanitized_bib = generate_sanitized_bib(report)
        Path(args.output_bib).write_text(sanitized_bib, encoding="utf-8")
        print(f"Sanitized BibTeX written to: {args.output_bib}")

    return 2 if report.retracted_count > 0 else 0


def cmd_search(args: argparse.Namespace) -> int:
    title = args.title
    found = search_identifier_by_title(title)
    if found:
        id_type, id_val = found
        print(f"Found {id_type.upper()}: {id_val}")
        if args.verify:
            meta = verify_citation(id_val)
            print(meta.summary_markdown())
        return 0
    else:
        print("No matching DOI found for title.")
        return 1


def main(argv: list[str] | None = None) -> int:
    reconfig_out = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfig_out):
        try:
            reconfig_out(encoding="utf-8", errors="replace")
            reconfig_err = getattr(sys.stderr, "reconfigure", None)
            if callable(reconfig_err):
                reconfig_err(encoding="utf-8", errors="replace")
        except Exception:
            pass

    actual_argv = sys.argv[1:] if argv is None else argv
    if actual_argv and actual_argv[0] == "argus":
        from scifi.argus.cli import main as argus_main
        return argus_main(actual_argv[1:])

    parser = argparse.ArgumentParser(
        prog="scifi",
        description="SciFi Research & Writing Toolkit: Citation Verifier and Integrity Sentinel.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # verify
    p_verify = subparsers.add_parser("verify", help="Verify a single DOI or link")
    p_verify.add_argument("query", help="DOI, arXiv link, PubMed URL, or publisher URL")
    p_verify.add_argument(
        "--format",
        choices=["markdown", "text", "json", "bibtex", "apa"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    p_verify.add_argument("--claimed-title", help="Claimed paper title to compare against")
    p_verify.add_argument("--claimed-year", type=int, help="Claimed publication year to compare against")
    p_verify.add_argument("--claimed-author", help="Claimed first author to compare against")
    p_verify.add_argument("--claimed-venue", help="Claimed venue/journal to compare against")
    p_verify.add_argument("--timeout", type=int, default=10, help="HTTP request timeout in seconds")

    # audit
    p_audit = subparsers.add_parser("audit", help="Audit an entire .bib file")
    p_audit.add_argument("bib_file", help="Path to .bib file")
    p_audit.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Report format")
    p_audit.add_argument("--output-report", help="File to write audit report to")
    p_audit.add_argument("--output-bib", help="File to write sanitized and verified .bib to")
    p_audit.add_argument("--no-search", action="store_true", help="Do not search registry for missing DOIs")

    # search
    p_search = subparsers.add_parser("search", help="Search official registries by title")
    p_search.add_argument("title", help="Paper title to search")
    p_search.add_argument("--verify", action="store_true", help="Automatically verify after locating identifier")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    if args.command == "verify":
        return cmd_verify(args)
    elif args.command == "audit":
        return cmd_audit(args)
    elif args.command == "search":
        return cmd_search(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
