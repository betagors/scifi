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
from scifi.literature.store import DEFAULT_CENTRAL_STORE_PATH, LiteratureStore
from scifi.web.server import SciFiWebServer

cmd_verify = citation_cli.cmd_verify
cmd_audit = citation_cli.cmd_audit
cmd_search = citation_cli.cmd_search
cmd_argus = argus_cli.cmd_audit
cmd_setup = setup_cli.cmd_setup
cmd_sync = setup_cli.cmd_sync


def cmd_ui(args: argparse.Namespace) -> int:
    """Launch the SciFi Web Cockpit local server and open browser."""
    import webbrowser

    db_path = getattr(args, "db", None) or str(DEFAULT_CENTRAL_STORE_PATH)
    store = LiteratureStore(db_path)
    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8080)
    no_browser = getattr(args, "no_browser", False)

    try:
        server = SciFiWebServer(store=store, host=host, port=port, auto_fallback=True)
    except Exception as e:
        print(f"[ERROR] Failed to start SciFi Web Cockpit: {e}", file=sys.stderr)
        return 1

    actual_url = f"http://{host}:{server.port}"
    print(f"[SUCCESS] SciFi Web Cockpit running at {actual_url}")
    print("Press Ctrl+C to stop.")

    if not no_browser:
        try:
            webbrowser.open(actual_url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down SciFi Web Cockpit...")
    finally:
        server.server_close()
    return 0


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
    """Run the 6-stage Manuscript Readiness Pipeline or Environment Diagnostics (`sf doctor`)."""
    if getattr(args, "env", False):
        from scifi.env import diagnose_environment
        diag = diagnose_environment(auto_fix=getattr(args, "fix", False))
        print("=== SciFi Environment Health Diagnostic ===")
        print(f"Python: {diag['python']['version']} ({diag['python']['executable']})")
        uv_status = "Available (" + diag['uv'].get('version', '') + ")" if diag['uv']['available'] else "Missing (fallback active)"
        print(f"uv: {uv_status}")
        z = diag['zotero']
        port_str = "OPEN" if z['port_23119_open'] else "CLOSED"
        print(f"Zotero: {z['status']} (data_dir: {z['data_dir']}, port 23119: {port_str})")
        lat = diag['latex']
        lat_status = "Available" if lat['available'] else "Missing"
        print(f"LaTeX Toolchain: {lat_status}")
        return 0

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


def cmd_human(args: argparse.Namespace) -> int:
    """Execute Humanizer & LaTeX Forensic Stylometry Auditor (`sf human`)."""
    from scifi.human import audit_human_prose

    res = audit_human_prose(
        tex_or_dir_path=args.target,
        output_report=getattr(args, "output", None),
    )
    if res.get("status") != "SUCCESS":
        print(f"[ERROR] {res.get('error_message', 'Humanizer audit failed.')}", file=sys.stderr)
        return 1

    if getattr(args, "format", "markdown") == "json" or getattr(args, "json", False):
        out = dict(res)
        out.pop("report_markdown", None)
        print(json.dumps(out, indent=2))
    else:
        print(res.get("report_markdown", ""))
    return 0 if res.get("human_score", 0) >= 55 else 1


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



def cmd_figures(args: argparse.Namespace) -> int:
    """Audit scientific figures & visual accessibility (`sf figures`)."""
    from scifi.figures import audit_latex_figures

    res = audit_latex_figures(
        tex_path=args.target,
        base_dir=getattr(args, "base_dir", None),
        min_dpi=getattr(args, "dpi", 300),
    )
    if getattr(args, "json", False):
        print(json.dumps(res.to_dict(), indent=2))
    else:
        print(f"# Figure & Visual Accessibility Audit ({len(res.issues)} issues, Score: {res.clean_score}/100)")
        for iss in res.issues:
            print(f"- [{iss.severity.value}] `{iss.figure_ref}`: {iss.message}")
            if iss.recommendation:
                print(f"  * Recommendation: {iss.recommendation}")
    return 0 if res.clean_score >= 70 else 1


def cmd_trim(args: argparse.Namespace) -> int:
    """Analyze page budget & micro-trimming opportunities (`sf trim`)."""
    from scifi.layout import audit_trim_budget

    res = audit_trim_budget(
        tex_path=args.target,
        bib_path=getattr(args, "bib", None),
    )
    if getattr(args, "json", False):
        print(json.dumps(res.to_dict(), indent=2))
    else:
        print(f"# Page Budget Trimming Audit (Potential savings: {res.total_potential_lines_saved} lines)")
        if res.bibtex_condensed_entries:
            print(f"- BibTeX Abbreviation: {res.bibtex_condensed_entries} verbose venues can be condensed.")
        for s in res.suggestions:
            print(f"- [{s.suggestion_type.value}] {s.target}: {s.description}")
    return 0


def cmd_proofs(args: argparse.Namespace) -> int:
    """Audit theorem-proof completeness and appendix pointers (`sf proofs`)."""
    from scifi.proofs import audit_latex_proofs

    res = audit_latex_proofs(tex_path=args.target)
    if getattr(args, "json", False):
        print(json.dumps(res.to_dict(), indent=2))
    else:
        print(f"# Theorem-Proof Completeness Audit ({res.total_theorems} theorems, {res.orphan_theorems} orphan(s))")
        for iss in res.issues:
            print(f"- [{iss.get('severity', 'WARNING')}] {iss.get('theorem')}: {iss.get('message')}")
    return 0 if res.orphan_theorems == 0 else 1


def cmd_repro(args: argparse.Namespace) -> int:
    """Audit conference reproducibility checklist (`sf repro`)."""
    from scifi.reproducibility import audit_reproducibility

    res = audit_reproducibility(
        tex_path=args.target,
        venue=getattr(args, "venue", "neurips"),
        double_blind=getattr(args, "double_blind", False),
    )
    if getattr(args, "json", False):
        print(json.dumps(res.to_dict(), indent=2))
    else:
        print(f"# Conference Reproducibility Audit [{res.venue.upper()}] (Score: {res.score}/100)")
        for k, v in res.checklist_items.items():
            status_icon = "PASS" if v else "FAIL"
            print(f"- [{status_icon}] {k}")
        for iss in res.issues:
            print(f"  * Warning: {iss.message}")
    return 0 if res.score >= 70 else 1


def cmd_rebuttal(args: argparse.Namespace) -> int:
    """Author rebuttal and manuscript diff suite (`sf rebuttal`)."""
    action = getattr(args, "rebuttal_action", None)
    if action == "format":
        from scifi.rebuttal import format_rebuttal_scaffold

        inp_path = getattr(args, "input", None)
        raw_text = Path(inp_path).read_text(encoding="utf-8") if inp_path and Path(inp_path).exists() else (getattr(args, "text", "") or "")
        scaffold = format_rebuttal_scaffold(reviews_text=raw_text, venue=getattr(args, "venue", "openreview"))
        out_p = getattr(args, "output", None)
        if out_p:
            Path(out_p).write_text(scaffold.markdown_template, encoding="utf-8")
            print(f"[OK] Rebuttal scaffold saved to {out_p}")
        else:
            print(scaffold.markdown_template)
        return 0
    elif action == "diff":
        from scifi.rebuttal import diff_manuscript

        res = diff_manuscript(
            old_tex_path=args.old_tex,
            new_tex_path=args.new_tex,
            generate_pdf=getattr(args, "pdf", False),
            output_tex=getattr(args, "output", None),
        )
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
        else:
            print(f"# Manuscript Revision Diff (+{res.added_lines} / -{res.deleted_lines} lines)")
            print(res.diff_ledger_markdown)
            if res.diff_pdf_path:
                print(f"[OK] Marked-up PDF generated: {res.diff_pdf_path}")
        return 0
    else:
        print("[ERROR] Specify a rebuttal action: format, diff", file=sys.stderr)
        return 1


def cmd_submission(args: argparse.Namespace) -> int:
    """Academic paper submission suite (`sf submission`)."""
    action = getattr(args, "submission_action", None)
    if action == "letter":
        from scifi.submission import generate_cover_letter

        res = generate_cover_letter(
            journal_name=getattr(args, "journal", "Target Journal") or "Target Journal",
            venue=getattr(args, "venue", "general") or "general",
            issn=getattr(args, "issn", None),
            editor_name=getattr(args, "editor", None),
            authors=getattr(args, "authors", None),
            figure_path=getattr(args, "figure", None),
            prior_doi=getattr(args, "prior_doi", None),
            manuscript_path=getattr(args, "target", None),
            output_path=getattr(args, "output", None),
        )
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
        else:
            print(res.markdown_text)
            if res.output_path:
                print(f"[OK] Cover letter saved to {res.output_path}")
        return 0

    elif action == "highlights":
        from scifi.submission import generate_highlights

        bullets_arg = getattr(args, "bullets", None)
        res = generate_highlights(
            bullets=bullets_arg,
            venue=getattr(args, "venue", "general") or "general",
            manuscript_path=getattr(args, "target", None),
            output_path=getattr(args, "output", None),
        )
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
        else:
            print(res.markdown_text)
            if not res.all_valid:
                for h in res.highlights:
                    if not h.is_valid:
                        print(f"  [WARNING] {h.issue}", file=sys.stderr)
            if getattr(args, "output", None):
                print(f"[OK] Highlights saved to {args.output}")
        return 0 if res.all_valid else 1

    elif action == "title-page":
        from scifi.submission import generate_title_page

        res = generate_title_page(
            venue=getattr(args, "venue", "general") or "general",
            authors=getattr(args, "authors", None),
            manuscript_path=getattr(args, "target", None),
            funding=getattr(args, "funding", None),
            conflicts=getattr(args, "conflicts", None),
            output_path=getattr(args, "output", None),
        )
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
        else:
            print(res.markdown_text)
            if res.output_path:
                print(f"[OK] Title page saved to {res.output_path}")
        return 0

    elif action == "pack-code":
        from scifi.submission import package_anonymous_code

        authors = [a.strip() for a in (getattr(args, "authors", "") or "").split(",") if a.strip()]
        res = package_anonymous_code(
            code_dir=getattr(args, "code_dir", "."),
            output_zip_path=getattr(args, "output", None),
            author_names=authors,
        )
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
        else:
            print(res.audit_report)
            if res.zip_path:
                print(f"[OK] Anonymous code archive created at: {res.zip_path}")
        return 0 if res.audit_passed else 1

    elif action == "bundle":
        from scifi.submission import prepare_submission_bundle

        res = prepare_submission_bundle(
            target_dir_or_tex=getattr(args, "target", "."),
            journal_name=getattr(args, "journal", None),
            venue=getattr(args, "venue", "general") or "general",
            issn=getattr(args, "issn", None),
            authors=getattr(args, "authors", None),
            code_dir=getattr(args, "code_dir", None),
            no_code=getattr(args, "no_code", False),
            figure_path=getattr(args, "figure", None),
            prior_doi=getattr(args, "prior_doi", None),
            funding=getattr(args, "funding", None),
            conflicts=getattr(args, "conflicts", None),
            editor_name=getattr(args, "editor", None),
            output_dir=getattr(args, "output", None),
        )
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
        else:
            print(f"# Submission Bundle Generated [{res.venue.upper()}]")
            print(f"- Output directory: `{res.output_dir}`")
            print(f"- Cover letter: `{res.cover_letter_path}`")
            print(f"- Highlights: `{res.highlights_path}`")
            print(f"- Title page: `{res.title_page_path}`")
            if res.code_zip_path:
                print(f"- Anonymous code zip: `{res.code_zip_path}`")
            print(f"- Manifest: `{res.manifest_path}`")
        return 0

    else:
        print("[ERROR] Specify a submission action: letter, highlights, title-page, pack-code, bundle", file=sys.stderr)
        return 1


def cmd_zotero(args: argparse.Namespace) -> int:
    """Manage local Zotero library, synchronization, and audit notes."""
    from scifi.env import auto_detect_zotero_dir, is_zotero_port_open
    from scifi.literature.zotero.reader import ZoteroLocalReader
    from scifi.literature.zotero.writer import ZoteroLocalWriter

    action = getattr(args, "zotero_action", None) or "status"

    if action == "status":
        z_dir = auto_detect_zotero_dir()
        port_open = is_zotero_port_open()
        print("=== SciFi Zotero Status ===")
        if not z_dir:
            print("Zotero Local Database: Not detected (checked standard paths)")
            print("Run 'sf doctor --env' for diagnostics.")
            return 0

        print(f"Zotero Data Directory: {z_dir}")
        print(f"Local Server (Port 23119): {'ONLINE' if port_open else 'OFFLINE (Desktop app closed)'}")
        try:
            reader = ZoteroLocalReader(data_dir=z_dir)
            cols = reader.get_collections()
            print(f"Collections Found: {len(cols)}")
            for c in cols[:5]:
                print(f"  - {c.name} (ID: {c.collection_id})")
            if len(cols) > 5:
                print(f"  ... and {len(cols) - 5} more")
        except Exception as e:
            print(f"Failed to read collections: {e}")
        return 0

    elif action == "sync":
        z_dir = auto_detect_zotero_dir()
        if not z_dir:
            print("[ERROR] Zotero data directory not found.", file=sys.stderr)
            return 1
        reader = ZoteroLocalReader(data_dir=z_dir)
        writer = ZoteroLocalWriter()
        col_name = getattr(args, "collection", None)
        if not col_name:
            cfg_path = Path(".scifi/config.toml")
            if cfg_path.is_file():
                for line in cfg_path.read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith("collection ="):
                        col_name = line.split("=")[1].strip().strip('"').strip("'")
                        break
        if not col_name:
            print("[ERROR] No collection specified. Pass --collection <name>.", file=sys.stderr)
            return 1

        items = reader.get_collection_items(col_name)
        print(f"[SUCCESS] Scanned collection '{col_name}': {len(items)} papers found.")

        flushed = writer.flush_staged_writes()
        if flushed:
            print(f"[SUCCESS] Flushed {len(flushed)} staged writes to Zotero.")
        return 0

    elif action == "flush":
        writer = ZoteroLocalWriter()
        flushed = writer.flush_staged_writes()
        print(f"Flushed {len(flushed)} staged mutations to Zotero.")
        return 0

    elif action == "annotations":
        key = getattr(args, "key", None)
        if not key:
            print("[ERROR] Item key required. Use --key <KEY>.", file=sys.stderr)
            return 1
        reader = ZoteroLocalReader()
        annos = reader.get_user_annotations(key)
        print(f"Annotations for item {key} ({len(annos)} found):")
        for a in annos:
            print(f"  - Page {a.page_label or '?'}: \"{a.text or ''}\" (Comment: {a.comment or 'None'})")
        return 0

    return 0


def cmd_scaffold(args: argparse.Namespace) -> int:
    """Scaffold a standard 2-pillar SciFi research project."""
    from scifi.scaffold import scaffold_project

    target = getattr(args, "target", ".")
    title = getattr(args, "title", "Research Manuscript")
    venue = getattr(args, "venue", "ieee")
    collection = getattr(args, "collection", None)

    res = scaffold_project(target_dir=target, title=title, venue=venue, collection=collection)
    print(f"[SUCCESS] Scaffolded 2-pillar project in '{res['root']}' for venue '{venue}'.")
    if res.get("collection"):
        print(f"Linked Zotero collection: {res['collection']}")
    return 0


def cmd_adapt(args: argparse.Namespace) -> int:
    """Migrate a legacy or flat codebase to standard SciFi structure."""
    from scifi.adapt import adapt_project

    target = getattr(args, "target", ".")
    venue = getattr(args, "venue", "ieee")
    collection = getattr(args, "collection", None)
    auto_match = getattr(args, "auto_match", False)
    dry_run = getattr(args, "dry_run", False)

    res = adapt_project(repo_dir=target, venue=venue, collection=collection, auto_match=auto_match, dry_run=dry_run)
    if res["status"] == "DRY_RUN":
        print(f"[DRY-RUN] Proposed moves for '{res['root']}':")
        print(f"  Publication moves: {len(res['publication_moves'])}")
        print(f"  Code moves: {len(res['code_moves'])}")
        print(f"  Data moves: {len(res['data_moves'])}")
        print(f"  Citations parsed: {res['citations_found']} ({res['zotero_matches']} matched in Zotero)")
        if res.get("collection"):
            print(f"  Target Zotero collection: {res['collection']}")
    else:
        print(f"[SUCCESS] Migrated project in '{res['root']}' to 2-pillar structure.")
        print(f"  Citations parsed: {res['citations_found']} ({res['zotero_matches']} matched in Zotero)")
        if res.get("collection"):
            if res.get("collection_staged"):
                print(f"  Linked Zotero collection: {res['collection']} (queued in .scifi/zotero_write_queue.json)")
                if res.get("collection_error"):
                    print(f"    ℹ️  {res['collection_error']}")
            else:
                print(f"  Linked Zotero collection: {res['collection']}")
                print(f"  Populated: {res.get('populated_linked', 0)} existing items linked, {res.get('populated_created', 0)} imported from .bib")
    return 0


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
    p_doctor.add_argument("--env", action="store_true", help="Diagnose environment health (Python, uv, LaTeX, Zotero)")
    p_doctor.add_argument("--fix", action="store_true", help="Attempt automatic remediation of environment issues")

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

    # human
    p_human = subparsers.add_parser(
        "human",
        aliases=["humanize", "deai", "stylometry"],
        help="Audit LaTeX source code and academic prose across 6 forensic stylometric and structural AI-detection dimensions",
    )
    p_human.add_argument("target", nargs="?", default=".", help="Path to .tex file, multi-file LaTeX directory, Markdown/text file, or inline text (default: .)")
    p_human.add_argument("--output", help="Optional path to save the Markdown forensic report")
    p_human.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_human.add_argument("--json", action="store_true", help="Output machine-readable JSON")

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

    # figures (da-vinci)
    p_figures = subparsers.add_parser("figures", aliases=["fig", "da-vinci"], help="Audit figures for DPI, vector formats, subfigure parity, and colorblind safety")
    p_figures.add_argument("target", nargs="?", default="main.tex", help="Path to .tex file or project root (default: main.tex)")
    p_figures.add_argument("--base-dir", help="Base directory containing figure assets")
    p_figures.add_argument("--dpi", type=int, default=300, help="Minimum acceptable DPI (default: 300)")
    p_figures.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # trim (layout)
    p_trim = subparsers.add_parser("trim", aliases=["budget", "layout"], help="Analyze page budget slack, paragraph widow lines, and BibTeX abbreviation savings")
    p_trim.add_argument("target", nargs="?", default="main.tex", help="Path to .tex file or project root (default: main.tex)")
    p_trim.add_argument("--bib", help="Path to BibTeX file (auto-discovered if omitted)")
    p_trim.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # proofs (euclid)
    p_proofs = subparsers.add_parser("proofs", aliases=["theorems", "euclid"], help="Audit theorem-proof completeness and verify appendix derivation pointers")
    p_proofs.add_argument("target", nargs="?", default="main.tex", help="Path to .tex file or project root (default: main.tex)")
    p_proofs.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # repro (bacon)
    p_repro = subparsers.add_parser("repro", aliases=["bacon", "reproducibility"], help="Audit conference reproducibility checklist (seeds, error bars, compute budget, anonymization)")
    p_repro.add_argument("target", nargs="?", default="main.tex", help="Path to .tex file or project root (default: main.tex)")
    p_repro.add_argument("--venue", default="neurips", help="Target venue checklist (default: neurips)")
    p_repro.add_argument("--double-blind", action="store_true", help="Enforce double-blind anonymization")
    p_repro.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # rebuttal (socrates)
    p_rebuttal = subparsers.add_parser("rebuttal", aliases=["socrates", "response"], help="Author rebuttal generator and LaTeX revision diff tracker")
    reb_sub = p_rebuttal.add_subparsers(dest="rebuttal_action", help="Rebuttal action")
    pr_format = reb_sub.add_parser("format", help="Generate 4-beat rebuttal scaffold from review text")
    pr_format.add_argument("--input", help="Path to raw reviews text file")
    pr_format.add_argument("--text", help="Raw reviews text inline")
    pr_format.add_argument("--venue", default="openreview", help="Target venue template (default: openreview)")
    pr_format.add_argument("--output", help="Output path for rebuttal markdown file")

    pr_diff = reb_sub.add_parser("diff", help="Generate diff ledger and marked-up PDF between old and new manuscripts")
    pr_diff.add_argument("old_tex", help="Path to original submission .tex file")
    pr_diff.add_argument("new_tex", help="Path to revised manuscript .tex file")
    pr_diff.add_argument("--pdf", action="store_true", help="Compile marked-up latexdiff PDF")
    pr_diff.add_argument("--output", help="Path to save marked-up diff .tex file")
    pr_diff.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # submission
    p_submission = subparsers.add_parser(
        "submission",
        aliases=["sub", "pack"],
        help="Academic paper submission suite: cover letter, highlights, title page, and anonymous code zip",
    )
    sub_sub = p_submission.add_subparsers(dest="submission_action", help="Submission action")

    ps_let = sub_sub.add_parser("letter", help="Generate publication-ready editorial cover letter")
    ps_let.add_argument("--target", help="Path to manuscript LaTeX file or directory")
    ps_let.add_argument("--journal", help="Target journal name")
    ps_let.add_argument("--venue", default="general", help="Target publisher profile (elsevier, ieee, springer, acm, general)")
    ps_let.add_argument("--issn", help="Journal ISSN")
    ps_let.add_argument("--editor", help="Editor-in-Chief name")
    ps_let.add_argument("--authors", help="Comma-separated author names")
    ps_let.add_argument("--figure", help="Path to teaser/graphical abstract figure")
    ps_let.add_argument("--prior-doi", help="DOI of prior publication extended by this submission")
    ps_let.add_argument("--output", help="Output file path (Markdown or LaTeX)")
    ps_let.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    ps_hl = sub_sub.add_parser("highlights", help="Generate and validate 3-5 research highlights against venue character limits")
    ps_hl.add_argument("--target", help="Path to manuscript LaTeX file to extract candidate highlights from")
    ps_hl.add_argument("--bullets", help="Explicit bullet points (semicolon or newline-separated)")
    ps_hl.add_argument("--venue", default="general", help="Target publisher profile (elsevier, ieee, springer, acm, general)")
    ps_hl.add_argument("--output", help="Output file path (Markdown or LaTeX)")
    ps_hl.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    ps_tp = sub_sub.add_parser("title-page", help="Generate unblinded standalone Title Page document for double-blind review fairness")
    ps_tp.add_argument("--target", help="Path to manuscript LaTeX file to extract metadata from")
    ps_tp.add_argument("--authors", help="Comma-separated author names or author definitions")
    ps_tp.add_argument("--venue", default="general", help="Target publisher profile (elsevier, ieee, springer, acm, general)")
    ps_tp.add_argument("--funding", help="Funding and grant acknowledgments")
    ps_tp.add_argument("--conflicts", help="Declaration of competing interests")
    ps_tp.add_argument("--output", help="Output file path (LaTeX or Markdown)")
    ps_tp.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    ps_pc = sub_sub.add_parser("pack-code", help="Package code repository into reproducible anonymous ZIP archive")
    ps_pc.add_argument("code_dir", nargs="?", default=".", help="Path to code directory to package (default: .)")
    ps_pc.add_argument("--authors", help="Comma-separated author names to audit against")
    ps_pc.add_argument("--output", help="Output zip file path (default: anonymous_code.zip)")
    ps_pc.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    ps_bun = sub_sub.add_parser("bundle", help="Generate all four submission artifacts and packaging manifest in one shot")
    ps_bun.add_argument("--target", default=".", help="Path to manuscript LaTeX file or directory (default: .)")
    ps_bun.add_argument("--journal", help="Target journal name")
    ps_bun.add_argument("--authors", help="Comma-separated author names or author definitions")
    ps_bun.add_argument("--venue", default="general", help="Target publisher profile (elsevier, ieee, springer, acm, general)")
    ps_bun.add_argument("--issn", help="Journal ISSN")
    ps_bun.add_argument("--code-dir", help="Explicit path to code directory")
    ps_bun.add_argument("--no-code", action="store_true", help="Skip code packaging (e.g. theoretical paper)")
    ps_bun.add_argument("--figure", help="Path to teaser/graphical abstract figure")
    ps_bun.add_argument("--prior-doi", help="DOI of prior publication extended by this submission")
    ps_bun.add_argument("--funding", help="Funding and grant acknowledgments")
    ps_bun.add_argument("--conflicts", help="Declaration of competing interests")
    ps_bun.add_argument("--editor", help="Editor-in-Chief name")
    ps_bun.add_argument("--output", help="Output directory path (default: dist/submission/)")
    ps_bun.add_argument("--json", action="store_true", help="Output machine-readable JSON")

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

    # zotero
    p_zotero = subparsers.add_parser("zotero", aliases=["zot"], help="Manage local Zotero library, synchronization, and audit notes")
    zot_sub = p_zotero.add_subparsers(dest="zotero_action", help="Zotero action")
    zot_sub.add_parser("status", help="Check local Zotero status, collections, and port 23119")
    pz_sync = zot_sub.add_parser("sync", help="Sync collection papers, references.bib, and flush staged writes")
    pz_sync.add_argument("--collection", help="Zotero collection name")
    zot_sub.add_parser("flush", help="Flush offline staged notes to Zotero")
    pz_ann = zot_sub.add_parser("annotations", help="View user PDF highlights and comments")
    pz_ann.add_argument("--key", required=True, help="Zotero item key")

    # scaffold
    p_scaffold = subparsers.add_parser("scaffold", aliases=["new", "bootstrap"], help="Scaffold a standard 2-pillar academic project (paper/ + code/ + .scifi/)")
    p_scaffold.add_argument("target", nargs="?", default=".", help="Target directory for project")
    p_scaffold.add_argument("--title", default="Research Manuscript", help="Manuscript title")
    p_scaffold.add_argument("--venue", default="ieee", help="Target venue profile (ieee, neurips, acm)")
    p_scaffold.add_argument("--collection", help="Link to Zotero collection")

    # adapt
    p_adapt = subparsers.add_parser("adapt", aliases=["migrate"], help="Migrate legacy codebase into standard 2-pillar SciFi structure")
    p_adapt.add_argument("target", nargs="?", default=".", help="Target legacy codebase directory")
    p_adapt.add_argument("--venue", default="ieee", help="Target venue profile")
    p_adapt.add_argument("--collection", help="Link to Zotero collection")
    p_adapt.add_argument("--match", "--auto-match", dest="auto_match", action="store_true", help="Auto-match best overlapping existing Zotero collection instead of project name")
    p_adapt.add_argument("--dry-run", action="store_true", help="Preview planned directory restructuring without moving files")

    # setup
    p_setup = subparsers.add_parser("setup", aliases=["init", "i"], help="Configure SciFi FastMCP server in OpenCode, Claude Code, VS Code (Cline/Roo), Cursor, Windsurf, Antigravity, and Claude Desktop")
    p_setup.add_argument("--auto", action="store_true", help="Non-interactive setup; install to all detected environments")
    p_setup.add_argument("--dry-run", action="store_true", help="Print planned configuration changes without modifying files")
    p_setup.add_argument("--target", type=str, help="Install to a specific configuration file path")
    p_setup.add_argument("--scifi-root", type=str, help="Custom root directory for scifi repository")
    p_setup.add_argument("--list", action="store_true", help="List all supported and detected AI environments")
    p_setup.add_argument("--rules", action="store_true", help="Synchronize SciFi scientific rules to project instruction files")
    p_setup.add_argument("--workspace", action="store_true", help="Configure workspace MCP manifests (.cursor, .mcp.json, opencode.json) and sync rules")
    p_setup.add_argument("--use-uvx", action="store_true", help="Configure MCP client to execute via zero-install 'uvx scifi server'")

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

    # ui (cockpit)
    p_ui = subparsers.add_parser("ui", aliases=["cockpit", "web"], help="Launch local SciFi Web Research Cockpit dashboard")
    p_ui.add_argument("--port", type=int, default=8080, help="Port to bind Web Cockpit server (default: 8080)")
    p_ui.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    p_ui.add_argument("--no-browser", action="store_true", help="Do not automatically open web browser")
    p_ui.add_argument(
        "--db",
        default=str(DEFAULT_CENTRAL_STORE_PATH),
        help=f"Path to SQLite central store (default: {DEFAULT_CENTRAL_STORE_PATH})",
    )

    # package (bundle)
    p_package = subparsers.add_parser("package", aliases=["bundle"], help="Build release packages (PyPI distributions and AI Agent Plugin bundle)")
    p_package.add_argument("--output-dir", "-o", default="dist", help="Output directory for generated packages (default: dist)")
    p_package.add_argument("--plugin-only", action="store_true", help="Build only the AI Agent Plugin zip bundle")
    p_package.add_argument("--python-only", action="store_true", help="Build only Python wheel and source distribution")

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
    elif args.command in ("human", "humanize", "deai", "stylometry"):
        return cmd_human(args)
    elif args.command in ("table", "tab", "booktabs"):
        return cmd_table(args)
    elif args.command in ("venue", "blind"):
        return cmd_venue(args)
    elif args.command in ("config", "cfg"):
        return cmd_config(args)
    elif args.command in ("figures", "fig", "da-vinci"):
        return cmd_figures(args)
    elif args.command in ("trim", "budget", "layout"):
        return cmd_trim(args)
    elif args.command in ("proofs", "theorems", "euclid"):
        return cmd_proofs(args)
    elif args.command in ("repro", "bacon", "reproducibility"):
        return cmd_repro(args)
    elif args.command in ("rebuttal", "socrates", "response"):
        return cmd_rebuttal(args)
    elif args.command in ("submission", "sub", "pack"):
        return cmd_submission(args)
    elif args.command in ("compile", "c", "build"):
        return cmd_compile(args)
    elif args.command in ("zotero", "zot"):
        return cmd_zotero(args)
    elif args.command in ("scaffold", "new", "bootstrap"):
        return cmd_scaffold(args)
    elif args.command in ("adapt", "migrate"):
        return cmd_adapt(args)
    elif args.command in ("setup", "init", "i"):
        return setup_cli.cmd_setup(args)
    elif args.command == "sync":
        return setup_cli.cmd_sync(args)
    elif args.command in ("server", "mcp", "serve"):
        return cmd_server(args)
    elif args.command in ("ui", "cockpit", "web"):
        return cmd_ui(args)
    elif args.command in ("package", "bundle"):
        from scifi.packaging import cmd_package

        return cmd_package(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
