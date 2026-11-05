"""
Unified Command-Line Interface for SciFi: Scientific Research & Academic Writing Toolkit.

Provides a single entry point (`scifi` / `sf`) for:
- doctor: End-to-end 6-stage peer-review readiness audit across single or multi-file LaTeX manuscripts
- verify: Single citation verification (DOI, URL, arXiv, PubMed)
- audit: BibTeX (.bib) file audit, retraction check & sanitization
- search: Academic registry search by paper title
- argus: Attribution audit, uncredited method detection & plagiarism prevention
- literature: Literature lineage discovery, interactive map, and reporting (alias: lit)
- math: Symbolic calculus, physical units, matrix shapes, limits, convexity & notation (Turing)
- stats: Curve verification against analytical formulas & sample statistics audit (Gauss)
- review: Adversarial claims & fragile assumptions audit (Popper)
- shannon: Title, 5-beat abstract, and academic SEO triage scorecard
- table: Publication-grade LaTeX `booktabs` table generator
- venue: Venue formatting & double-blind anonymization compliance checker
- config: Global (`~/.scifi/config.json`) & project (`scifi.toml`) configuration manager
- compile: LaTeX compilation and log diagnostics
- setup / sync: Automated multi-agent MCP & scientific rules installer
- server: FastMCP daemon execution
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from scifi import setup_cli
from scifi.argus import cli as argus_cli
from scifi.citation_verifier import cli as citation_cli
from scifi.literature.cli import cmd_literature, register_literature_subparsers

cmd_verify = citation_cli.cmd_verify
cmd_audit = citation_cli.cmd_audit
cmd_search = citation_cli.cmd_search
cmd_argus = argus_cli.cmd_audit
cmd_setup = setup_cli.cmd_setup
cmd_sync = setup_cli.cmd_sync


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


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run the 6-stage Manuscript Readiness Pipeline (`sf doctor`)."""
    from scifi.doctor import audit_manuscript

    res = audit_manuscript(
        tex_or_dir_path=args.target,
        bib_path=getattr(args, "bib", None),
        venue=getattr(args, "venue", None),
        double_blind=True if getattr(args, "double_blind", False) else None,
        compile_pdf=getattr(args, "compile", False),
        live=getattr(args, "live", False),
        output_report=getattr(args, "output", None),
    )
    if res.get("status") != "SUCCESS":
        print(f"[ERROR] {res.get('error_message', 'Manuscript audit failed.')}", file=sys.stderr)
        return 1

    if getattr(args, "format", "markdown") == "json":
        out = dict(res)
        out.pop("report_markdown", None)
        print(json.dumps(out, indent=2))
    else:
        print(res.get("report_markdown", ""))
    return 0 if res.get("readiness_score", 0) >= 65 else 1


def cmd_config(args: argparse.Namespace) -> int:
    """Manage global (~/.scifi/config.json) and workspace (scifi.toml) configuration."""
    from scifi.config import (
        generate_scifi_toml_template,
        get_global_config_path,
        resolve_config,
        set_global_config_value,
    )

    sub = getattr(args, "config_action", None) or "show"
    if sub == "show":
        cfg = resolve_config()
        print(json.dumps({"global_config_path": str(get_global_config_path()), "effective_config": cfg.to_dict()}, indent=2))
        return 0
    elif sub == "set":
        try:
            saved = set_global_config_value(args.key, args.value)
            print(f"[SUCCESS] Updated '{args.key}' in {saved}")
            return 0
        except ValueError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 1
    elif sub == "init":
        target = Path(getattr(args, "output", "scifi.toml"))
        if target.exists() and not getattr(args, "force", False):
            print(f"[ERROR] {target} already exists. Pass --force to overwrite.", file=sys.stderr)
            return 1
        template = generate_scifi_toml_template(
            main_tex=getattr(args, "main_tex", "main.tex"),
            bib_file=getattr(args, "bib_file", "references.bib"),
            target_venue=getattr(args, "venue", "ieee"),
            double_blind=getattr(args, "double_blind", True),
        )
        target.write_text(template, encoding="utf-8")
        print(f"[SUCCESS] Created project configuration in {target.resolve()}")
        return 0
    return 0


def cmd_math(args: argparse.Namespace) -> int:
    """Execute Turing mathematical verification subcommands (`sf math`)."""
    from scifi.math import (
        check_convexity,
        check_limits,
        check_matrix_shapes,
        check_notation,
        check_units,
        verify_derivation_step,
        verify_derivative,
    )

    sub = getattr(args, "math_command", None)
    if sub == "derivative":
        res = verify_derivative(args.expression, args.variable, args.claimed)
    elif sub == "step":
        res = verify_derivation_step(args.lhs, args.rhs, assumptions=args.assumptions)
    elif sub == "units":
        res = check_units(args.expression, mode=args.mode)
    elif sub == "shapes":
        try:
            shapes_dict = json.loads(args.shapes)
        except Exception as e:
            print(f"[ERROR] Invalid JSON for --shapes: {e}", file=sys.stderr)
            return 1
        res = check_matrix_shapes(args.expression, shapes_dict)
    elif sub == "limits":
        res = check_limits(args.expression, args.variable, args.tends_to, direction=args.direction, expected=args.expected)
    elif sub == "convexity":
        res = check_convexity(args.expression, args.variables)
    elif sub == "notation":
        res = check_notation(args.target)
    else:
        print("[ERROR] Specify a math subcommand: derivative, step, units, shapes, limits, convexity, notation", file=sys.stderr)
        return 1

    print(json.dumps(res, indent=2))
    return 0 if res.get("is_correct", res.get("status") in ("VALID", "SUCCESS")) else 1


def cmd_stats(args: argparse.Namespace) -> int:
    """Execute Gauss statistical & curve verification subcommands (`sf stats`)."""
    from scifi.stats import audit_statistics, verify_curve

    sub = getattr(args, "stats_command", None)
    if sub == "curve":
        res = verify_curve(args.formula, args.data_path, args.x_col, args.y_col, tolerance=args.tolerance)
    elif sub == "audit":
        raw = args.values
        try:
            if raw.strip().startswith("[") or raw.strip().startswith("{") or Path(raw).exists():
                parsed_input = json.loads(raw) if raw.strip().startswith(("[", "{")) else raw
            else:
                parsed_input = [float(x.strip()) for x in raw.split(",") if x.strip()]
        except Exception:
            parsed_input = raw
        res = audit_statistics(parsed_input, confidence=args.confidence)
    else:
        print("[ERROR] Specify a stats subcommand: curve, audit", file=sys.stderr)
        return 1

    print(json.dumps(res, indent=2))
    return 0 if res.get("status") in ("VALID", "SUCCESS") else 1


def cmd_review(args: argparse.Namespace) -> int:
    """Execute Popper adversarial claims scanner (`sf review`)."""
    from scifi.review import audit_claims

    res = audit_claims(args.target)
    if getattr(args, "format", "markdown") == "json":
        print(json.dumps(res, indent=2))
    else:
        if res.get("status") != "SUCCESS":
            print(f"[ERROR] {res.get('message', 'Audit failed')}", file=sys.stderr)
            return 1
        flags = res.get("flags", [])
        print(f"# Popper Adversarial Claims Audit ({len(flags)} flags)")
        for f in flags:
            loc = f"{f.get('file', '')}:{f.get('line', '')}".strip(":")
            print(f"- Line `{loc}`: **\"{f['matched_text']}\"** — {f['critique']}")
    return 0


def cmd_shannon(args: argparse.Namespace) -> int:
    """Execute Shannon Title, 5-Beat Abstract & SEO evaluator (`sf shannon`)."""
    from scifi.shannon import evaluate_manuscript_metadata

    res = evaluate_manuscript_metadata(
        title=getattr(args, "title", None),
        abstract=getattr(args, "abstract", None),
        keywords=getattr(args, "keywords", None),
        tex_path=getattr(args, "target", None),
        target_venue=getattr(args, "venue", None),
        live=getattr(args, "live", False),
    )
    if res.get("status") != "SUCCESS":
        print(f"[ERROR] {res.get('error_message', 'Shannon evaluation failed.')}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        out = dict(res)
        out.pop("report_text", None)
        print(json.dumps(out, indent=2))
    else:
        print(res.get("report_text", ""))
    return 0 if res.get("triage_score", {}).get("total_score", 0) >= 70 else 1


def cmd_table(args: argparse.Namespace) -> int:
    """Generate a publication-grade LaTeX `booktabs` table (`sf table`)."""
    from scifi.latex.tables import generate_latex_table

    lower_cols = [c.strip() for c in (args.lower_better or "").split(",") if c.strip()]
    res = generate_latex_table(
        data_input=args.data_file,
        caption=args.caption,
        label=args.label,
        lower_is_better=lower_cols,
        precision=args.precision,
        output_path=args.output,
    )
    if res.get("status") != "SUCCESS":
        print(f"[ERROR] {res.get('error_message', 'Table generation failed.')}", file=sys.stderr)
        return 1

    if getattr(args, "format", "latex") == "json":
        print(json.dumps(res, indent=2))
    else:
        print(res["latex"])
    return 0


def cmd_venue(args: argparse.Namespace) -> int:
    """Audit a single or multi-file LaTeX manuscript for venue compliance & double-blind leaks (`sf venue`)."""
    from scifi.latex.venue import check_venue_compliance

    authors = [a.strip() for a in (args.authors or "").split(",") if a.strip()]
    res = check_venue_compliance(
        tex_or_dir_path=args.target,
        venue=args.venue,
        double_blind=args.double_blind,
        author_names=authors,
    )
    if res.get("status") == "ERROR":
        print(f"[ERROR] {res.get('error_message')}", file=sys.stderr)
        return 1

    if getattr(args, "format", "markdown") == "json":
        print(json.dumps(res, indent=2))
    else:
        print(f"# Venue & Double-Blind Compliance Report [{res['status']}]")
        print(f"- **Entrypoint:** `{res['entrypoint']}` (Files scanned: {len(res['files_scanned'])})")
        print(f"- **Venue:** `{res['venue']}` | **Double-Blind:** `{res['double_blind']}`")
        print(f"- **Errors:** {res['errors_count']} | **Warnings:** {res['warnings_count']}")
        for iss in res.get("issues", []):
            print(f"  - **[{iss['severity']}]** `{iss['file']}:{iss['line']}` ({iss['category']}): {iss['message']}")
    return 0 if res.get("is_compliant", True) else 1


def create_parser() -> argparse.ArgumentParser:
    """Build the unified top-level ArgumentParser."""
    parser = argparse.ArgumentParser(
        prog="scifi",
        description="SciFi: Scientific Research & Academic Writing Toolkit for literature verification, paper auditing, and proof structuring.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # doctor (end-to-end manuscript audit)
    p_doctor = subparsers.add_parser(
        "doctor",
        aliases=["doc", "check-paper"],
        help="Run the 6-stage Manuscript Peer-Review Readiness Pipeline across single or multi-file LaTeX projects",
    )
    p_doctor.add_argument("target", nargs="?", default=".", help="Path to root .tex file (e.g. main.tex) or project directory (default: .)")
    p_doctor.add_argument("--bib", help="Optional explicit path to .bib file (auto-discovered if omitted)")
    p_doctor.add_argument("--venue", help="Target venue profile (e.g. ieee, neurips, icml, acm, nature)")
    p_doctor.add_argument("--double-blind", action="store_true", help="Enforce double-blind anonymization rules")
    p_doctor.add_argument("--compile", action="store_true", help="Also run latexmk/pdflatex compilation")
    p_doctor.add_argument("--live", action="store_true", help="Perform live Crossref/OpenAlex registry lookups")
    p_doctor.add_argument("--output", help="Write Markdown readiness report to file")
    p_doctor.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")

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
    p_argus.add_argument("file", nargs="?", default=None, help="Path to LaTeX (.tex), directory, or markdown/text file to audit")
    p_argus.add_argument("--bib", help="Path to target references.bib file")
    p_argus.add_argument("--format", choices=["markdown", "json", "text"], default="markdown", help="Report format")
    p_argus.add_argument("--fix", action="store_true", help="Automatically insert \\cite and append BibTeX")
    p_argus.add_argument("--author-whitelist", nargs="*", help="Author names to whitelist against self-plagiarism flags")
    p_argus.add_argument("--preprint-doi", help="DOI of author's preprint")
    p_argus.add_argument("--no-search", action="store_true", help="Skip remote registry lookups")

    # literature
    p_literature = subparsers.add_parser(
        "literature",
        aliases=["lit"],
        help="Academic literature lineage discovery, interactive map, and reporting",
    )
    register_literature_subparsers(p_literature)

    # math (Turing)
    p_math = subparsers.add_parser("math", aliases=["turing", "m"], help="Symbolic calculus, units, matrix shapes, limits, convexity & notation checks")
    math_sub = p_math.add_subparsers(dest="math_command", help="Mathematical verification tool")

    pm_deriv = math_sub.add_parser("derivative", help="Verify symbolic derivative d^n/dx^n f(x)")
    pm_deriv.add_argument("expression", help="Function f(x)")
    pm_deriv.add_argument("variable", help="Differentiation variable")
    pm_deriv.add_argument("claimed", help="Claimed derivative")
    pm_deriv.add_argument("--order", type=int, default=1, help="Derivative order (default: 1)")

    pm_step = math_sub.add_parser("step", help="Verify algebraic/calculus equivalence LHS == RHS")
    pm_step.add_argument("lhs", help="Left-hand side expression")
    pm_step.add_argument("rhs", help="Right-hand side expression")
    pm_step.add_argument("--assumptions", nargs="*", help="Optional assumptions (e.g. 'x > 0')")

    pm_units = math_sub.add_parser("units", help="Check physical dimensional homogeneity via Pint")
    pm_units.add_argument("expression", help="Equation or comma-separated terms with units")
    pm_units.add_argument("--mode", choices=["eq", "terms"], default="eq", help="Validation mode")

    pm_shapes = math_sub.add_parser("shapes", help="Verify matrix/tensor contraction shapes")
    pm_shapes.add_argument("expression", help="Matrix expression (e.g. 'A @ B + C')")
    pm_shapes.add_argument("--shapes", required=True, help="JSON mapping symbol names to dimension lists")

    pm_limits = math_sub.add_parser("limits", help="Evaluate symbolic boundary limit")
    pm_limits.add_argument("expression", help="Expression to evaluate")
    pm_limits.add_argument("variable", help="Limit variable")
    pm_limits.add_argument("tends_to", help="Target value (e.g. 0, oo, -oo)")
    pm_limits.add_argument("--direction", default="+-", help="Limit direction (+, -, +-)")
    pm_limits.add_argument("--expected", help="Optional expected limit result")

    pm_conv = math_sub.add_parser("convexity", help="Check symbolic Hessian definiteness and convexity")
    pm_conv.add_argument("expression", help="Scalar objective function")
    pm_conv.add_argument("variables", help="Comma-separated variable names (e.g. 'x,y')")

    pm_not = math_sub.add_parser("notation", help="Scan single or multi-file LaTeX project for notation consistency")
    pm_not.add_argument("target", help="Path to .tex file, project directory, or LaTeX string")

    # stats (Gauss)
    p_stats = subparsers.add_parser("stats", aliases=["gauss"], help="Empirical curve verification and statistical significance auditing")
    stats_sub = p_stats.add_subparsers(dest="stats_command", help="Statistical audit tool")

    ps_curve = stats_sub.add_parser("curve", help="Compare closed-form theoretical formula against empirical simulation data")
    ps_curve.add_argument("formula", help="Analytical formula")
    ps_curve.add_argument("data_path", help="Path to CSV/JSON data or inline JSON")
    ps_curve.add_argument("x_col", help="Independent variable column")
    ps_curve.add_argument("y_col", help="Dependent variable column")
    ps_curve.add_argument("--tolerance", type=float, default=0.05, help="Relative RMSE tolerance (default: 0.05)")

    ps_audit = stats_sub.add_parser("audit", help="Audit sample statistics, 95%% CI, and Central Limit Theorem (N >= 30)")
    ps_audit.add_argument("values", help="Comma-separated numbers, JSON array, or path to CSV/JSON file")
    ps_audit.add_argument("--confidence", type=float, default=0.95, help="Confidence level (default: 0.95)")

    # review (Popper)
    p_review = subparsers.add_parser("review", aliases=["popper", "claims"], help="Adversarial peer-review scanner for overclaims and fragile assumptions")
    p_review.add_argument("target", help="Path to .tex file, multi-file LaTeX directory, or raw text")
    p_review.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")

    # shannon
    p_shannon = subparsers.add_parser("shannon", aliases=["seo", "abstract"], help="Evaluate title, 5-beat abstract, and keywords on 100-point Reviewer Triage rubric")
    p_shannon.add_argument("target", nargs="?", default=None, help="Optional path to .tex file or multi-file LaTeX directory")
    p_shannon.add_argument("--title", help="Draft manuscript title")
    p_shannon.add_argument("--abstract", help="Draft manuscript abstract")
    p_shannon.add_argument("--keywords", help="Comma-separated candidate keywords")
    p_shannon.add_argument("--venue", help="Target publisher or venue")
    p_shannon.add_argument("--live", action="store_true", help="Perform live title collision check on OpenAlex/Crossref")
    p_shannon.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # table
    p_table = subparsers.add_parser("table", aliases=["tab", "booktabs"], help="Generate publication-grade LaTeX booktabs tables with bolded SOTA metrics")
    p_table.add_argument("data_file", help="Path to CSV/JSON file or inline JSON array")
    p_table.add_argument("--caption", default="Experimental comparison against state-of-the-art baselines.", help="LaTeX table caption")
    p_table.add_argument("--label", default="tab:results", help="LaTeX table label")
    p_table.add_argument("--lower-better", help="Comma-separated column names where lower is better (e.g. RMSE,Latency)")
    p_table.add_argument("--precision", type=int, default=2, help="Decimal places (default: 2)")
    p_table.add_argument("--output", help="Optional path to write generated .tex file")
    p_table.add_argument("--format", choices=["latex", "json"], default="latex", help="Output format")

    # venue
    p_venue = subparsers.add_parser("venue", aliases=["blind"], help="Audit single or multi-file LaTeX manuscript for venue compliance & double-blind leaks")
    p_venue.add_argument("target", nargs="?", default=".", help="Path to .tex file or project directory (default: .)")
    p_venue.add_argument("--venue", help="Venue profile (e.g. ieee, neurips, icml, cvpr, acm, nature)")
    p_venue.add_argument("--double-blind", action="store_true", help="Enforce double-blind anonymization checks")
    p_venue.add_argument("--authors", help="Comma-separated author names to scan for accidental leaks")
    p_venue.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")

    # config
    p_config = subparsers.add_parser("config", aliases=["cfg"], help="Manage global (~/.scifi/config.json) and project (scifi.toml) configuration")
    cfg_sub = p_config.add_subparsers(dest="config_action", help="Config action")
    cfg_sub.add_parser("show", help="Show resolved global and workspace configuration")
    pc_set = cfg_sub.add_parser("set", help="Set a global config value (email, s2_api_key, default_venue, author_whitelist)")
    pc_set.add_argument("key", help="Config key (email, s2_api_key, default_venue, author_whitelist)")
    pc_set.add_argument("value", help="Config value")
    pc_init = cfg_sub.add_parser("init", help="Create a template scifi.toml in the current workspace")
    pc_init.add_argument("--output", default="scifi.toml", help="Output path (default: scifi.toml)")
    pc_init.add_argument("--main-tex", default="main.tex", help="Main LaTeX file name")
    pc_init.add_argument("--bib-file", default="references.bib", help="BibTeX file name")
    pc_init.add_argument("--venue", default="ieee", help="Target venue name")
    pc_init.add_argument("--double-blind", action="store_true", default=False, help="Enable double-blind mode by default")
    pc_init.add_argument("--force", action="store_true", help="Overwrite existing scifi.toml")

    # setup
    p_setup = subparsers.add_parser("setup", aliases=["init", "i"], help="Configure SciFi FastMCP server in OpenCode, Claude Code, VS Code (Cline/Roo), Cursor, Windsurf, Antigravity, and Claude Desktop")
    p_setup.add_argument("--auto", action="store_true", help="Non-interactive setup; install to all detected environments")
    p_setup.add_argument("--dry-run", action="store_true", help="Print planned configuration changes without modifying files")
    p_setup.add_argument("--target", type=str, help="Install to a specific configuration file path")
    p_setup.add_argument("--scifi-root", type=str, help="Custom root directory for scifi repository")
    p_setup.add_argument("--list", action="store_true", help="List all supported and detected AI environments")
    p_setup.add_argument("--rules", action="store_true", help="Synchronize SciFi scientific rules to project instruction files")
    p_setup.add_argument("--workspace", action="store_true", help="Configure workspace MCP manifests (.cursor, .mcp.json, opencode.json) and sync rules")

    # sync
    p_sync = subparsers.add_parser("sync", help="Synchronize SciFi scientific rules to CLAUDE.md, .clinerules, .cursorrules, etc.")
    p_sync.add_argument("--dry-run", action="store_true", help="Print planned rule synchronization without modifying files")

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

    if args.command in ("doctor", "doc", "check-paper"):
        return cmd_doctor(args)
    elif args.command in ("verify", "v", "check"):
        return citation_cli.cmd_verify(args)
    elif args.command in ("audit", "a"):
        return citation_cli.cmd_audit(args)
    elif args.command in ("search", "s", "find"):
        return citation_cli.cmd_search(args)
    elif args.command in ("argus", "cite", "attribution"):
        if not args.file:
            for action in parser._subparsers._actions:
                if isinstance(action, argparse._SubParsersAction):
                    p_arg = action.choices.get("argus")
                    if p_arg:
                        p_arg.print_help()
                        return 0
            parser.print_help()
            return 0
        return argus_cli.cmd_audit(args)
    elif args.command in ("literature", "lit"):
        if not getattr(args, "lit_command", None):
            for action in parser._subparsers._actions:
                if isinstance(action, argparse._SubParsersAction):
                    p_lit = action.choices.get("literature")
                    if p_lit:
                        p_lit.print_help()
                        return 0
            parser.print_help()
            return 0
        return cmd_literature(args)
    elif args.command in ("math", "turing", "m"):
        return cmd_math(args)
    elif args.command in ("stats", "gauss"):
        return cmd_stats(args)
    elif args.command in ("review", "popper", "claims"):
        return cmd_review(args)
    elif args.command in ("shannon", "seo", "abstract"):
        return cmd_shannon(args)
    elif args.command in ("table", "tab", "booktabs"):
        return cmd_table(args)
    elif args.command in ("venue", "blind"):
        return cmd_venue(args)
    elif args.command in ("config", "cfg"):
        return cmd_config(args)
    elif args.command in ("compile", "c", "build"):
        return cmd_compile(args)
    elif args.command in ("setup", "init", "i"):
        return setup_cli.cmd_setup(args)
    elif args.command == "sync":
        return setup_cli.cmd_sync(args)
    elif args.command in ("server", "mcp", "serve"):
        return cmd_server(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
