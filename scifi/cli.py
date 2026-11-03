"""
Unified Command-Line Interface for SciFi: Scientific Research & Academic Writing Toolkit.

Provides a single entry point for:
- verify: Single citation verification (DOI, URL, arXiv, PubMed)
- audit: BibTeX (.bib) file audit, retraction check & sanitization
- search: Academic registry search by paper title
- argus: Attribution audit, uncredited method detection & plagiarism prevention
- setup: REA-style setup installer configuring Antigravity, Claude Desktop, and Cursor
- server: FastMCP daemon execution
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from scifi import setup_cli
from scifi.argus import cli as argus_cli
from scifi.citation_verifier import cli as citation_cli

cmd_verify = citation_cli.cmd_verify
cmd_audit = citation_cli.cmd_audit
cmd_search = citation_cli.cmd_search
cmd_argus = argus_cli.cmd_audit
cmd_setup = setup_cli.cmd_setup


def cmd_server(args: argparse.Namespace) -> int:
    """Run the FastMCP server daemon."""
    from scifi.server import mcp

    transport = getattr(args, "transport", "stdio")
    mcp.run(transport=transport)
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    """Compile a LaTeX manuscript and report diagnostics."""
    from scifi.latex import compile_latex

    entrypoint = args.tex_file
    engine = getattr(args, "engine", "auto")
    clean = getattr(args, "clean", True)
    res = compile_latex(entrypoint=entrypoint, engine=engine, clean=clean)

    status = res.get("status")
    if status == "SUCCESS":
        print(f"[SUCCESS] Compiled {res.get('pdf_path')}")
        warnings = res.get("warnings", [])
        if warnings:
            print(f"Warnings ({len(warnings)}):")
            for w in warnings:
                print(f"  - {w}")
        return 0
    elif status == "ENGINE_MISSING":
        print(f"[ENGINE_MISSING] {res.get('message')}")
        hint = res.get("action_required", {}).get("install_command")
        if hint:
            print(f"Action required: {hint}")
        return 1
    else:
        print(f"[{status}] Compilation failed: {res.get('message')}")
        for err in res.get("errors", []):
            loc = f"{err.get('file', '')}:{err.get('line', '')}"
            print(f"  Error at {loc}: {err.get('message', '')}")
        return 1


def create_parser() -> argparse.ArgumentParser:
    """Build the unified top-level ArgumentParser."""
    parser = argparse.ArgumentParser(
        prog="scifi",
        description="SciFi: Scientific Research & Academic Writing Toolkit for literature verification, paper auditing, and proof structuring.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # verify
    p_verify = subparsers.add_parser("verify", aliases=["v", "check"], help="Verify a citation (DOI, arXiv link, PubMed URL, or publisher URL)")
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
    p_audit = subparsers.add_parser("audit", aliases=["a"], help="Audit an entire BibTeX (.bib) file for retracts, errata, and missing DOIs")
    p_audit.add_argument("bib_file", help="Path to .bib file")
    p_audit.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Report format")
    p_audit.add_argument("--output-report", help="File to write audit report to")
    p_audit.add_argument("--output-bib", help="File to write sanitized and verified .bib to")
    p_audit.add_argument("--no-search", action="store_true", help="Do not search registry for missing DOIs")

    # search
    p_search = subparsers.add_parser("search", aliases=["s", "find"], help="Search official registries by paper title")
    p_search.add_argument("title", help="Paper title to search")
    p_search.add_argument("--verify", action="store_true", help="Automatically verify after locating identifier")

    # argus
    p_argus = subparsers.add_parser("argus", aliases=["cite", "attribution"], help="Attribution sentinel, uncredited method detection, and plagiarism audit")
    p_argus.add_argument("file", nargs="?", default=None, help="Path to LaTeX (.tex) or markdown/text file to audit")
    p_argus.add_argument("--bib", help="Path to target references.bib file")
    p_argus.add_argument("--format", choices=["markdown", "json", "text"], default="markdown", help="Report format")
    p_argus.add_argument("--fix", action="store_true", help="Automatically insert \\cite and append BibTeX")
    p_argus.add_argument("--author-whitelist", nargs="*", help="Author names to whitelist against self-plagiarism flags")
    p_argus.add_argument("--preprint-doi", help="DOI of author's preprint")
    p_argus.add_argument("--no-search", action="store_true", help="Skip remote registry lookups")

    # setup
    p_setup = subparsers.add_parser("setup", aliases=["init", "i"], help="Configure SciFi FastMCP server in Antigravity, Claude Desktop, and Cursor")
    p_setup.add_argument("--auto", action="store_true", help="Non-interactive setup; install to all detected environments")
    p_setup.add_argument("--dry-run", action="store_true", help="Print planned configuration changes without modifying files")
    p_setup.add_argument("--target", type=str, help="Install to a specific configuration file path")
    p_setup.add_argument("--scifi-root", type=str, help="Custom root directory for scifi repository")

    # compile
    p_compile = subparsers.add_parser("compile", aliases=["c", "build"], help="Compile a LaTeX manuscript and diagnose build errors")
    p_compile.add_argument("tex_file", nargs="?", default="main.tex", help="Path to main LaTeX (.tex) file (default: main.tex)")
    p_compile.add_argument("--engine", choices=["auto", "latexmk", "pdflatex"], default="auto", help="LaTeX engine to use (default: auto)")
    p_compile.add_argument("--no-clean", dest="clean", action="store_false", default=True, help="Do not remove auxiliary files")

    # server
    p_server = subparsers.add_parser("server", aliases=["mcp", "serve"], help="Run the SciFi FastMCP server daemon")
    p_server.add_argument("--transport", choices=["stdio", "sse"], default="stdio", help="MCP transport mode (default: stdio)")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """
    Main CLI entrypoint for SciFi.

    Args:
        argv: Command-line arguments. Defaults to sys.argv[1:].

    Returns:
        Exit code: 0 on success, non-zero on error.
    """
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    actual_argv = list(sys.argv[1:] if argv is None else argv)

    # Support nested Argus subcommands: `scifi argus scan ...` or `scifi argus search ...` or `scifi argus audit ...`
    if len(actual_argv) > 1 and actual_argv[0] in ("argus", "cite", "attribution") and actual_argv[1] in ("audit", "scan", "search"):
        from scifi.argus.cli import main as argus_main

        return argus_main(actual_argv[1:])

    parser = create_parser()

    if not actual_argv:
        parser.print_help()
        return 0

    try:
        args = parser.parse_args(actual_argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 0

    if not args.command:
        parser.print_help()
        return 0

    if args.command in ("verify", "v", "check"):
        return citation_cli.cmd_verify(args)
    elif args.command in ("audit", "a"):
        return citation_cli.cmd_audit(args)
    elif args.command in ("search", "s", "find"):
        return citation_cli.cmd_search(args)
    elif args.command in ("argus", "cite", "attribution"):
        if not args.file:
            # Print argus-specific help if file is missing
            for action in parser._subparsers._actions:
                if isinstance(action, argparse._SubParsersAction):
                    p_arg = action.choices.get("argus")
                    if p_arg:
                        p_arg.print_help()
                        return 0
            parser.print_help()
            return 0
        return argus_cli.cmd_audit(args)
    elif args.command in ("compile", "c", "build"):
        return cmd_compile(args)
    elif args.command in ("setup", "init", "i"):
        return setup_cli.cmd_setup(args)
    elif args.command in ("server", "mcp", "serve"):
        return cmd_server(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
