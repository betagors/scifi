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
import sys
from collections.abc import Sequence
from pathlib import Path

from scifi import setup_cli
from scifi.argus import cli as argus_cli
from scifi.citation_verifier import cli as citation_cli
from scifi.commands import (
    cmd_datasets,
    cmd_doctor,
    cmd_kaggle,
    cmd_math,
    cmd_stats,
    cmd_submission,
    cmd_zenodo,
    cmd_zotero,
)
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
    from typing import Literal

    from scifi.server import mcp

    raw_transport = getattr(args, "transport", "stdio")
    transport: Literal["stdio", "sse", "streamable-http"]
    if raw_transport == "sse":
        transport = "sse"
    elif raw_transport == "streamable-http":
        transport = "streamable-http"
    else:
        transport = "stdio"
    mcp.run(transport=transport)
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    """Compile a LaTeX manuscript and report diagnostics."""
    from scifi.latex import compile_latex

    entrypoint = args.tex_file
    engine = getattr(args, "engine", "auto")
    clean = getattr(args, "clean", True)
    render_pages = getattr(args, "render", False)
    res = compile_latex(entrypoint=entrypoint, engine=engine, clean=clean, render_pages=render_pages)

    if getattr(args, "json", False):
        print(json.dumps(res, indent=2))
        return 0 if res.get("status") == "SUCCESS" else 1

    status = res.get("status")
    dist = res.get("distribution") or "TeX"
    eng = res.get("engine") or engine
    eng_path = res.get("engine_path") or ""
    dur = res.get("duration_seconds")
    dur_str = f" | {dur}s" if dur is not None else ""

    if status == "SUCCESS":
        pages_str = f" | {res['page_count']} pages" if res.get("page_count") else ""
        print(f"[SUCCESS] Compiled {res.get('pdf_path')}")
        print(f"[COMPILER] {dist} | {eng} ({eng_path}){dur_str}{pages_str}")
        undef_refs = res.get("undefined_references") or []
        undef_cites = res.get("undefined_citations") or []
        if undef_refs:
            print(f"[WARN] Undefined references ({len(undef_refs)}): {', '.join(undef_refs)}")
        if undef_cites:
            print(f"[WARN] Undefined citations ({len(undef_cites)}): {', '.join(undef_cites)}")
        warnings_count = res.get("warnings_count", 0)
        layout = res.get("layout_warnings") or {}
        overfull = layout.get("overfull_hbox", 0)
        if warnings_count or overfull:
            print(f"[DIAGNOSTICS] warnings={warnings_count}, overfull_hbox={overfull}")
        if res.get("rendered_pages"):
            print(f"[EYES] Rendered {len(res['rendered_pages'])} PNG preview(s) via {res.get('render_backend')}:")
            for rp in res["rendered_pages"]:
                print(f"  - Page {rp['page']}: {rp['image_path']} ({rp['width']}x{rp['height']})")
        return 0
    elif status in ("COMPILER_NOT_FOUND", "ENGINE_MISSING"):
        print(f"[{status}] {res.get('hint') or res.get('message') or 'No LaTeX compiler found.'}")
        return 1
    else:
        print(
            f"[{status}] Compilation failed ({dist} | {eng}{dur_str}): {res.get('error_message') or res.get('error') or ''}"
        )
        for err in res.get("errors", []):
            loc = f"{err.get('file') or ''}:{err.get('line') or ''}"
            print(f"  Error at {loc}: {err.get('message', '')}")
        return 1


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
        print(
            json.dumps(
                {"global_config_path": str(get_global_config_path()), "effective_config": cfg.to_dict()}, indent=2
            )
        )
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
            print(f'- Line `{loc}`: **"{f["matched_text"]}"** — {f["critique"]}')
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


def cmd_orwell(args: argparse.Namespace) -> int:
    """Execute Orwell Academic Prose & LaTeX Stylometric Auditor (`sf orwell`)."""
    from scifi.orwell import audit_orwell_prose, calibrate_orwell_voice, verify_edit_invariants

    positionals: list[str] = list(getattr(args, "target", []) or [])
    as_json = getattr(args, "format", "markdown") == "json" or getattr(args, "json", False)

    if positionals and positionals[0] == "calibrate":
        corpus_dir = positionals[1] if len(positionals) > 1 else None
        res = calibrate_orwell_voice(
            corpus_dir=corpus_dir,
            preset=getattr(args, "preset", None),
            exemplar_dir=getattr(args, "exemplar", None),
            notation_only=getattr(args, "notation_only", False),
            blend_preset=getattr(args, "blend_preset", None),
            output_toml=getattr(args, "toml", None),
            write_toml=not getattr(args, "no_write", False),
        )
        if res.get("status") != "SUCCESS":
            print(f"[ERROR] {res.get('error_message', 'Orwell calibration failed.')}", file=sys.stderr)
            return 1
        if as_json:
            print(json.dumps(res, indent=2))
        else:
            p = res["profile"]
            print(f"[ORWELL CALIBRATE] source={p.get('source')} preset={p.get('preset')}")
            print(
                f"  sentence_length_mean={p.get('sentence_length_mean')}w, "
                f"cv_target={p.get('sentence_length_cv_target')} (min={p.get('sentence_length_cv_min')}), "
                f"passive_ratio={p.get('passive_ratio_target')}"
            )
            print(f"  transitions={p.get('preferred_transitions')}")
            print(f"  macros_extracted={len(p.get('macro_conventions', {}))}")
            for w in res.get("warnings", []):
                print(f"  [WARN] {w}")
            if res.get("toml_path"):
                print(f"  Saved to: {res['toml_path']}")
        return 0

    if positionals and positionals[0] == "verify-edit":
        if len(positionals) < 3:
            print("[ERROR] Usage: sf orwell verify-edit <before> <after>", file=sys.stderr)
            return 1
        res = verify_edit_invariants(positionals[1], positionals[2])
        if as_json:
            print(json.dumps(res, indent=2))
        else:
            status_tag = "PASS" if res["passed"] else "FAIL"
            print(f"[ORWELL INVARIANT CHECK: {status_tag}] violations={res['violation_count']}")
            for v in res.get("violations", []):
                print(f"  - [{v['category']}] {v['change']}: {v['token']} (x{v['count']})")
        return 0 if res.get("passed") else 1

    target = positionals[0] if positionals else "."
    res = audit_orwell_prose(
        tex_or_dir_path=target,
        output_report=getattr(args, "output", None),
    )
    if res.get("status") != "SUCCESS":
        print(f"[ERROR] {res.get('error_message', 'Orwell audit failed.')}", file=sys.stderr)
        return 1

    if as_json:
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
        render_previews=not getattr(args, "no_render", False),
        pdf_path=getattr(args, "pdf", None),
        render_dpi=getattr(args, "render_dpi", 150),
        vlm_check=getattr(args, "vlm", False),
        vlm_provider=getattr(args, "vlm_provider", None),
        vlm_model=getattr(args, "vlm_model", None),
    )
    if getattr(args, "json", False):
        print(json.dumps(res.to_dict(), indent=2))
    else:
        print(f"# Figure & Visual Accessibility Audit ({len(res.issues)} issues, Score: {res.clean_score}/100)")
        for iss in res.issues:
            print(f"- [{iss.severity.value}] `{iss.figure_ref}`: {iss.message}")
            if iss.recommendation:
                print(f"  * Recommendation: {iss.recommendation}")
        if res.rendered_previews:
            print(f"\n## Visual Previews ({len(res.rendered_previews)})")
            for rp in res.rendered_previews:
                label = rp.get("figure_ref") or f"Page {rp.get('page')}"
                print(f"- [{rp.get('kind')}] {label}: {rp.get('image_path')}")
        if res.vlm_inspection and res.vlm_inspection.get("status") != "DISABLED":
            vlm_status = res.vlm_inspection.get("status")
            print(f"\n## VLM Visual Inspection: {vlm_status}")
            if res.vlm_inspection.get("provider"):
                print(f"- Provider: `{res.vlm_inspection.get('provider')}` (`{res.vlm_inspection.get('model')}`)")
            if res.vlm_inspection.get("hint"):
                print(f"- Note: {res.vlm_inspection.get('hint')}")
            if res.vlm_inspection.get("error_message"):
                print(f"- Error: {res.vlm_inspection.get('error_message')}")
    return 0 if res.clean_score >= 70 else 1


def cmd_trim(args: argparse.Namespace) -> int:
    """Analyze page budget & micro-trimming opportunities (`sf trim`)."""
    from scifi.layout import audit_trim_budget

    res = audit_trim_budget(
        tex_path=args.target,
        bib_path=getattr(args, "bib", None),
        render_previews=not getattr(args, "no_render", False),
        pdf_path=getattr(args, "pdf", None),
        render_dpi=getattr(args, "render_dpi", 150),
        pages=getattr(args, "pages", None),
        vlm_check=getattr(args, "vlm", False),
        vlm_provider=getattr(args, "vlm_provider", None),
        vlm_model=getattr(args, "vlm_model", None),
    )
    if getattr(args, "json", False):
        print(json.dumps(res.to_dict(), indent=2))
    else:
        print(f"# Page Budget Trimming Audit (Potential savings: {res.total_potential_lines_saved} lines)")
        if res.bibtex_condensed_entries:
            print(f"- BibTeX Abbreviation: {res.bibtex_condensed_entries} verbose venues can be condensed.")
        for s in res.suggestions:
            print(f"- [{s.suggestion_type.value}] {s.target}: {s.description}")
        if res.rendered_pages:
            print(f"\n## Rendered PDF Pages ({len(res.rendered_pages)})")
            for rp in res.rendered_pages:
                print(f"- Page {rp.get('page')}: {rp.get('image_path')}")
        if res.vlm_inspection and res.vlm_inspection.get("status") != "DISABLED":
            vlm_status = res.vlm_inspection.get("status")
            print(f"\n## VLM Layout Inspection: {vlm_status}")
            if res.vlm_inspection.get("provider"):
                print(f"- Provider: `{res.vlm_inspection.get('provider')}` (`{res.vlm_inspection.get('model')}`)")
            if res.vlm_inspection.get("hint"):
                print(f"- Note: {res.vlm_inspection.get('hint')}")
            if res.vlm_inspection.get("error_message"):
                print(f"- Error: {res.vlm_inspection.get('error_message')}")
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
    """Audit conference reproducibility or domain reporting checklist (`sf repro`)."""
    from scifi.reproducibility import audit_reproducibility

    res = audit_reproducibility(
        tex_path=args.target,
        venue=getattr(args, "venue", "neurips"),
        double_blind=getattr(args, "double_blind", False),
        standard=getattr(args, "standard", None),
        check_pitfalls=not getattr(args, "no_pitfalls", False),
    )
    if getattr(args, "json", False):
        print(json.dumps(res.to_dict(), indent=2))
    else:
        print(
            f"# Reproducibility & Reporting Audit [{res.venue.upper()} | {res.standard.upper()}] "
            f"(Score: {res.score}/100)"
        )
        for k, v in res.checklist_items.items():
            status_icon = "PASS" if v else "FAIL"
            print(f"- [{status_icon}] {k}")
        for iss in res.issues:
            print(f"  * [{iss.severity}] {iss.message}")
    return 0 if res.score >= 70 else 1


def cmd_rebuttal(args: argparse.Namespace) -> int:
    """Author rebuttal and manuscript diff suite (`sf rebuttal`)."""
    action = getattr(args, "rebuttal_action", None)
    if action == "format":
        from scifi.rebuttal import format_rebuttal_scaffold

        inp_path = getattr(args, "input", None)
        raw_text = (
            Path(inp_path).read_text(encoding="utf-8")
            if inp_path and Path(inp_path).exists()
            else (getattr(args, "text", "") or "")
        )
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
                print(
                    f"  Populated: {res.get('populated_linked', 0)} existing items linked, {res.get('populated_created', 0)} imported from .bib"
                )
    return 0


def create_parser() -> argparse.ArgumentParser:
    """Build the unified top-level ArgumentParser."""
    parser = argparse.ArgumentParser(
        prog="scifi",
        description="SciFi: Scientific Research & Academic Writing Toolkit for literature verification, paper auditing, and proof structuring.",
    )
    import scifi

    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"scifi {scifi.__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # doctor (end-to-end manuscript audit)
    p_doctor = subparsers.add_parser(
        "doctor",
        aliases=["doc", "check-paper"],
        help="Run the 6-stage Manuscript Peer-Review Readiness Pipeline across single or multi-file LaTeX projects",
    )
    p_doctor.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Path to root .tex file (e.g. main.tex) or project directory (default: .)",
    )
    p_doctor.add_argument("--bib", help="Optional explicit path to .bib file (auto-discovered if omitted)")
    p_doctor.add_argument("--venue", help="Target venue profile (e.g. ieee, neurips, icml, acm, nature)")
    p_doctor.add_argument("--double-blind", action="store_true", help="Enforce double-blind anonymization rules")
    p_doctor.add_argument("--compile", action="store_true", help="Also run latexmk/pdflatex compilation")
    p_doctor.add_argument("--live", action="store_true", help="Perform live Crossref/OpenAlex registry lookups")
    p_doctor.add_argument("--output", help="Write Markdown readiness report to file")
    p_doctor.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_doctor.add_argument("--env", action="store_true", help="Diagnose environment health (Python, uv, LaTeX, Zotero)")
    p_doctor.add_argument("--fix", action="store_true", help="Attempt automatic remediation of environment issues")
    p_doctor.add_argument(
        "--history",
        action="store_true",
        help="Show Readiness Score ledger across drafts from .scifi/audit_history.json",
    )

    # verify
    p_verify = subparsers.add_parser(
        "verify", aliases=["v", "check"], help="Verify a citation (DOI, arXiv link, PubMed URL, or publisher URL)"
    )
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
    p_verify.add_argument(
        "--strict-consensus",
        action="store_true",
        help="Require >=2 independent registries to confirm the reference",
    )

    # audit
    p_audit = subparsers.add_parser(
        "audit", aliases=["a"], help="Audit an entire BibTeX (.bib) file for retracts, errata, and missing DOIs"
    )
    p_audit.add_argument("bib_file", help="Path to .bib file")
    p_audit.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Report format")
    p_audit.add_argument("--output-report", help="File to write audit report to")
    p_audit.add_argument("--output-bib", help="File to write sanitized and verified .bib to")
    p_audit.add_argument("--no-search", action="store_true", help="Do not search registry for missing DOIs")
    p_audit.add_argument(
        "--strict-consensus",
        action="store_true",
        help="Require >=2 independent registries to confirm each reference",
    )

    # search
    p_search = subparsers.add_parser("search", aliases=["s", "find"], help="Search official registries by paper title")
    p_search.add_argument("title", help="Paper title to search")
    p_search.add_argument("--verify", action="store_true", help="Automatically verify after locating identifier")

    # argus
    p_argus = subparsers.add_parser(
        "argus",
        aliases=["cite", "attribution"],
        help="Attribution sentinel, uncredited method detection, and plagiarism audit",
    )
    p_argus.add_argument(
        "file", nargs="?", default=None, help="Path to LaTeX (.tex), directory, or markdown/text file to audit"
    )
    p_argus.add_argument("--bib", help="Path to target references.bib file")
    p_argus.add_argument("--format", choices=["markdown", "json", "text"], default="markdown", help="Report format")
    p_argus.add_argument("--fix", action="store_true", help="Automatically insert \\cite and append BibTeX")
    p_argus.add_argument(
        "--author-whitelist", nargs="*", help="Author names to whitelist against self-plagiarism flags"
    )
    p_argus.add_argument("--preprint-doi", help="DOI of author's preprint")
    p_argus.add_argument("--no-search", action="store_true", help="Skip remote registry lookups")
    p_argus.add_argument(
        "--entailment",
        action="store_true",
        help="Run Hypatia claim-to-citation entailment audit on \\cite{} references",
    )
    p_argus.add_argument(
        "--no-pdf",
        action="store_true",
        help="Do not download Unpaywall/arXiv PDFs during entailment audit (use OpenAlex abstract only)",
    )

    # literature
    p_literature = subparsers.add_parser(
        "literature",
        aliases=["lit"],
        help="Academic literature lineage discovery, interactive map, and reporting",
    )
    register_literature_subparsers(p_literature)

    # math (Turing)
    p_math = subparsers.add_parser(
        "math",
        aliases=["turing", "m"],
        help="Symbolic calculus, units, matrix shapes, limits, convexity & notation checks",
    )
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
    pm_not.add_argument("--manifest", action="store_true", help="Include full cross-section symbol_manifest")

    # stats (Gauss)
    p_stats = subparsers.add_parser(
        "stats", aliases=["gauss"], help="Empirical curve verification and statistical significance auditing"
    )
    stats_sub = p_stats.add_subparsers(dest="stats_command", help="Statistical audit tool")

    ps_curve = stats_sub.add_parser(
        "curve", help="Compare closed-form theoretical formula against empirical simulation data"
    )
    ps_curve.add_argument("formula", help="Analytical formula")
    ps_curve.add_argument("data_path", help="Path to CSV/JSON data or inline JSON")
    ps_curve.add_argument("x_col", help="Independent variable column")
    ps_curve.add_argument("y_col", help="Dependent variable column")
    ps_curve.add_argument("--tolerance", type=float, default=0.05, help="Relative RMSE tolerance (default: 0.05)")

    ps_audit = stats_sub.add_parser(
        "audit", help="Audit sample statistics, 95%% CI, and Central Limit Theorem (N >= 30)"
    )
    ps_audit.add_argument("values", help="Comma-separated numbers, JSON array, or path to CSV/JSON file")
    ps_audit.add_argument("--confidence", type=float, default=0.95, help="Confidence level (default: 0.95)")

    # review (Popper)
    p_review = subparsers.add_parser(
        "review",
        aliases=["popper", "claims"],
        help="Adversarial peer-review scanner for overclaims and fragile assumptions",
    )
    p_review.add_argument("target", help="Path to .tex file, multi-file LaTeX directory, or raw text")
    p_review.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")

    # shannon
    p_shannon = subparsers.add_parser(
        "shannon",
        aliases=["seo", "abstract"],
        help="Evaluate title, 5-beat abstract, and keywords on 100-point Reviewer Triage rubric",
    )
    p_shannon.add_argument(
        "target", nargs="?", default=None, help="Optional path to .tex file or multi-file LaTeX directory"
    )
    p_shannon.add_argument("--title", help="Draft manuscript title")
    p_shannon.add_argument("--abstract", help="Draft manuscript abstract")
    p_shannon.add_argument("--keywords", help="Comma-separated candidate keywords")
    p_shannon.add_argument("--venue", help="Target publisher or venue")
    p_shannon.add_argument(
        "--live", action="store_true", help="Perform live title collision check on OpenAlex/Crossref"
    )
    p_shannon.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # orwell
    p_orwell = subparsers.add_parser(
        "orwell",
        aliases=["stylometry", "prose"],
        help="Audit LaTeX/prose stylometry, calibrate personal/exemplar voice, and verify edit invariants",
    )
    p_orwell.add_argument(
        "target",
        nargs="*",
        help="Target .tex/dir/text, or 'calibrate [<dir>]', or 'verify-edit <before> <after>'",
    )
    p_orwell.add_argument("--output", help="Optional path to save the Markdown forensic report")
    p_orwell.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_orwell.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_orwell.add_argument(
        "--preset",
        choices=["terse-systems", "formal-theory", "narrative-science", "balanced"],
        help="Calibrate from a built-in scholarly voice preset",
    )
    p_orwell.add_argument("--exemplar", help="Calibrate from an exemplar papers directory (.tex/.pdf)")
    p_orwell.add_argument(
        "--notation-only",
        action="store_true",
        help="Extract only macro/notation conventions from corpus_dir while using preset/exemplar prose cadence",
    )
    p_orwell.add_argument(
        "--blend-preset",
        choices=["terse-systems", "formal-theory", "narrative-science", "balanced"],
        help="Preset to blend with --notation-only",
    )
    p_orwell.add_argument("--toml", help="Path to scifi.toml to update (default: ./scifi.toml)")
    p_orwell.add_argument("--no-write", action="store_true", help="Preview calibration without writing scifi.toml")

    # table
    p_table = subparsers.add_parser(
        "table",
        aliases=["tab", "booktabs"],
        help="Generate publication-grade LaTeX booktabs tables with bolded SOTA metrics",
    )
    p_table.add_argument("data_file", help="Path to CSV/JSON file or inline JSON array")
    p_table.add_argument(
        "--caption", default="Experimental comparison against state-of-the-art baselines.", help="LaTeX table caption"
    )
    p_table.add_argument("--label", default="tab:results", help="LaTeX table label")
    p_table.add_argument(
        "--lower-better", help="Comma-separated column names where lower is better (e.g. RMSE,Latency)"
    )
    p_table.add_argument("--precision", type=int, default=2, help="Decimal places (default: 2)")
    p_table.add_argument("--output", help="Optional path to write generated .tex file")
    p_table.add_argument("--format", choices=["latex", "json"], default="latex", help="Output format")

    # venue
    p_venue = subparsers.add_parser(
        "venue",
        aliases=["blind"],
        help="Audit single or multi-file LaTeX manuscript for venue compliance & double-blind leaks",
    )
    p_venue.add_argument("target", nargs="?", default=".", help="Path to .tex file or project directory (default: .)")
    p_venue.add_argument("--venue", help="Venue profile (e.g. ieee, neurips, icml, cvpr, acm, nature)")
    p_venue.add_argument("--double-blind", action="store_true", help="Enforce double-blind anonymization checks")
    p_venue.add_argument("--authors", help="Comma-separated author names to scan for accidental leaks")
    p_venue.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")

    # figures (da-vinci)
    p_figures = subparsers.add_parser(
        "figures",
        aliases=["fig", "da-vinci"],
        help="Audit figures for DPI, vector formats, subfigure parity, colorblind safety, and VLM visual defects",
    )
    p_figures.add_argument(
        "target", nargs="?", default="main.tex", help="Path to .tex file or project root (default: main.tex)"
    )
    p_figures.add_argument("--base-dir", help="Base directory containing figure assets")
    p_figures.add_argument("--dpi", type=int, default=300, help="Minimum acceptable DPI (default: 300)")
    p_figures.add_argument("--pdf", help="Optional compiled PDF path for page rendering")
    p_figures.add_argument("--render-dpi", type=int, default=150, help="PNG preview render DPI (default: 150)")
    p_figures.add_argument("--no-render", action="store_true", help="Skip rendering figure/PDF PNG previews")
    p_figures.add_argument("--vlm", action="store_true", help="Run VLM visual defect check on rendered PNGs")
    p_figures.add_argument(
        "--vlm-provider",
        choices=["gemini", "openai", "anthropic", "openai_compatible"],
        help="VLM provider override",
    )
    p_figures.add_argument("--vlm-model", help="VLM model identifier override")
    p_figures.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # trim (layout)
    p_trim = subparsers.add_parser(
        "trim",
        aliases=["budget", "layout"],
        help="Analyze page budget slack, paragraph widow lines, BibTeX abbreviations, and VLM layout defects",
    )
    p_trim.add_argument(
        "target", nargs="?", default="main.tex", help="Path to .tex file or project root (default: main.tex)"
    )
    p_trim.add_argument("--bib", help="Path to BibTeX file (auto-discovered if omitted)")
    p_trim.add_argument("--pdf", help="Optional compiled PDF path for page rendering")
    p_trim.add_argument("--pages", help="Page numbers or ranges to render (e.g. '1-4,8')")
    p_trim.add_argument("--render-dpi", type=int, default=150, help="PNG preview render DPI (default: 150)")
    p_trim.add_argument("--no-render", action="store_true", help="Skip rendering compiled PDF pages to PNG")
    p_trim.add_argument("--vlm", action="store_true", help="Run VLM visual layout check on rendered PDF pages")
    p_trim.add_argument(
        "--vlm-provider",
        choices=["gemini", "openai", "anthropic", "openai_compatible"],
        help="VLM provider override",
    )
    p_trim.add_argument("--vlm-model", help="VLM model identifier override")
    p_trim.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # proofs (euclid)
    p_proofs = subparsers.add_parser(
        "proofs",
        aliases=["theorems", "euclid"],
        help="Audit theorem-proof completeness and verify appendix derivation pointers",
    )
    p_proofs.add_argument(
        "target", nargs="?", default="main.tex", help="Path to .tex file or project root (default: main.tex)"
    )
    p_proofs.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # repro (bacon)
    p_repro = subparsers.add_parser(
        "repro",
        aliases=["bacon", "reproducibility"],
        help="Audit ML and ML-systems reproducibility checklists and statistical pitfalls",
    )
    p_repro.add_argument(
        "target", nargs="?", default="main.tex", help="Path to .tex file or project root (default: main.tex)"
    )
    p_repro.add_argument("--venue", default="neurips", help="Target venue checklist (default: neurips)")
    p_repro.add_argument(
        "--standard",
        choices=["ml", "ml-systems"],
        default=None,
        help="Reproducibility checklist profile (default: inferred from --venue, or ml)",
    )
    p_repro.add_argument("--no-pitfalls", action="store_true", help="Skip statistical-pitfall scans")
    p_repro.add_argument("--double-blind", action="store_true", help="Enforce double-blind anonymization")
    p_repro.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # rebuttal (socrates)
    p_rebuttal = subparsers.add_parser(
        "rebuttal", aliases=["socrates", "response"], help="Author rebuttal generator and LaTeX revision diff tracker"
    )
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
    ps_let.add_argument(
        "--venue", default="general", help="Target publisher profile (elsevier, ieee, springer, acm, general)"
    )
    ps_let.add_argument("--issn", help="Journal ISSN")
    ps_let.add_argument("--editor", help="Editor-in-Chief name")
    ps_let.add_argument("--authors", help="Comma-separated author names")
    ps_let.add_argument("--figure", help="Path to teaser/graphical abstract figure")
    ps_let.add_argument("--prior-doi", help="DOI of prior publication extended by this submission")
    ps_let.add_argument("--output", help="Output file path (Markdown or LaTeX)")
    ps_let.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    ps_hl = sub_sub.add_parser(
        "highlights", help="Generate and validate 3-5 research highlights against venue character limits"
    )
    ps_hl.add_argument("--target", help="Path to manuscript LaTeX file to extract candidate highlights from")
    ps_hl.add_argument("--bullets", help="Explicit bullet points (semicolon or newline-separated)")
    ps_hl.add_argument(
        "--venue", default="general", help="Target publisher profile (elsevier, ieee, springer, acm, general)"
    )
    ps_hl.add_argument("--output", help="Output file path (Markdown or LaTeX)")
    ps_hl.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    ps_tp = sub_sub.add_parser(
        "title-page", help="Generate unblinded standalone Title Page document for double-blind review fairness"
    )
    ps_tp.add_argument("--target", help="Path to manuscript LaTeX file to extract metadata from")
    ps_tp.add_argument("--authors", help="Comma-separated author names or author definitions")
    ps_tp.add_argument(
        "--venue", default="general", help="Target publisher profile (elsevier, ieee, springer, acm, general)"
    )
    ps_tp.add_argument("--funding", help="Funding and grant acknowledgments")
    ps_tp.add_argument("--conflicts", help="Declaration of competing interests")
    ps_tp.add_argument("--output", help="Output file path (LaTeX or Markdown)")
    ps_tp.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    ps_pc = sub_sub.add_parser("pack-code", help="Package code repository into reproducible anonymous ZIP archive")
    ps_pc.add_argument("code_dir", nargs="?", default=".", help="Path to code directory to package (default: .)")
    ps_pc.add_argument("--authors", help="Comma-separated author names to audit against")
    ps_pc.add_argument("--output", help="Output zip file path (default: anonymous_code.zip)")
    ps_pc.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    ps_bun = sub_sub.add_parser(
        "bundle", help="Generate all four submission artifacts and packaging manifest in one shot"
    )
    ps_bun.add_argument("--target", default=".", help="Path to manuscript LaTeX file or directory (default: .)")
    ps_bun.add_argument("--journal", help="Target journal name")
    ps_bun.add_argument("--authors", help="Comma-separated author names or author definitions")
    ps_bun.add_argument(
        "--venue", default="general", help="Target publisher profile (elsevier, ieee, springer, acm, general)"
    )
    ps_bun.add_argument("--issn", help="Journal ISSN")
    ps_bun.add_argument("--code-dir", help="Explicit path to code directory")
    ps_bun.add_argument("--no-code", action="store_true", help="Skip code packaging (e.g. theoretical paper)")
    ps_bun.add_argument("--figure", help="Path to teaser/graphical abstract figure")
    ps_bun.add_argument("--prior-doi", help="DOI of prior publication extended by this submission")
    ps_bun.add_argument("--funding", help="Funding and grant acknowledgments")
    ps_bun.add_argument("--conflicts", help="Declaration of competing interests")
    ps_bun.add_argument("--editor", help="Editor-in-Chief name")
    ps_bun.add_argument("--output", help="Output directory path (default: dist/submission/)")
    ps_bun.add_argument(
        "--strict",
        "--gate",
        action="store_true",
        dest="strict",
        help="Gate bundle generation on zero critical blockers (retractions, double-blind leaks, orphan proofs)",
    )
    ps_bun.add_argument(
        "--double-blind", action="store_true", help="Enforce double-blind anonymization rules during gate check"
    )
    ps_bun.add_argument("--live", action="store_true", help="Run live retraction lookups during gate check")
    ps_bun.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # config
    p_config = subparsers.add_parser(
        "config", aliases=["cfg"], help="Manage global (~/.scifi/config.json) and project (scifi.toml) configuration"
    )
    cfg_sub = p_config.add_subparsers(dest="config_action", help="Config action")
    cfg_sub.add_parser("show", help="Show resolved global and workspace configuration")
    pc_set = cfg_sub.add_parser(
        "set", help="Set a global config value (email, s2_api_key, default_venue, author_whitelist)"
    )
    pc_set.add_argument("key", help="Config key (email, s2_api_key, default_venue, author_whitelist)")
    pc_set.add_argument("value", help="Config value")
    pc_init = cfg_sub.add_parser("init", help="Create a template scifi.toml in the current workspace")
    pc_init.add_argument("--output", default="scifi.toml", help="Output path (default: scifi.toml)")
    pc_init.add_argument("--main-tex", default="main.tex", help="Main LaTeX file name")
    pc_init.add_argument("--bib-file", default="references.bib", help="BibTeX file name")
    pc_init.add_argument("--venue", default="ieee", help="Target venue name")
    pc_init.add_argument(
        "--double-blind", action="store_true", default=False, help="Enable double-blind mode by default"
    )
    pc_init.add_argument("--force", action="store_true", help="Overwrite existing scifi.toml")

    # zotero
    p_zotero = subparsers.add_parser(
        "zotero", aliases=["zot"], help="Manage local Zotero library, synchronization, and audit notes"
    )
    zot_sub = p_zotero.add_subparsers(dest="zotero_action", help="Zotero action")
    zot_sub.add_parser("status", help="Check local Zotero status, collections, and port 23119")
    pz_sync = zot_sub.add_parser("sync", help="Sync collection papers, references.bib, and flush staged writes")
    pz_sync.add_argument("--collection", help="Zotero collection name")
    pz_watch = zot_sub.add_parser("watch", help="Continuously watch and auto-sync Zotero collection and references.bib")
    pz_watch.add_argument("--collection", help="Zotero collection name")
    pz_watch.add_argument("--all", action="store_true", help="Watch all registered Zotero-enabled projects")
    pz_watch.add_argument("--interval", type=float, default=5.0, help="Polling interval in seconds (default: 5.0)")
    zot_sub.add_parser("flush", help="Flush offline staged notes to Zotero")
    pz_create = zot_sub.add_parser(
        "create-collection",
        aliases=["create", "link"],
        help="Create/ensure a Zotero collection and link it in .scifi/config.toml",
    )
    pz_create.add_argument("name", help="Zotero collection name")
    pz_create.add_argument("--no-save", action="store_true", help="Do not update .scifi/config.toml")
    pz_ann = zot_sub.add_parser("annotations", help="View user PDF highlights and comments")
    pz_ann.add_argument("--key", required=True, help="Zotero item key")

    # datasets
    p_datasets = subparsers.add_parser(
        "datasets", aliases=["ds", "data"], help="Search, download, and manage datasets with a default datasets folder"
    )
    ds_sub = p_datasets.add_subparsers(dest="datasets_action", help="Datasets action")
    pds_dir = ds_sub.add_parser("dir", help="Show or set the default datasets directory")
    pds_dir.add_argument("--set", dest="set_path", help="Set a new default datasets directory globally")
    pds_list = ds_sub.add_parser("list", help="List locally downloaded datasets")
    pds_list.add_argument("--dir", help="Override datasets directory")
    pds_list.add_argument("--json", action="store_true", help="Output JSON")
    pds_search = ds_sub.add_parser("search", help="Search datasets across Kaggle, Hugging Face, and Zenodo")
    pds_search.add_argument("query", help="Search query")
    pds_search.add_argument("--provider", default="all", choices=["all", "kaggle", "hf", "huggingface", "zenodo"])
    pds_search.add_argument("--limit", type=int, default=15, help="Max results per provider")
    pds_search.add_argument("--json", action="store_true", help="Output JSON")
    pds_dl = ds_sub.add_parser("download", help="Download a dataset from Kaggle, Hugging Face, Zenodo, or URL")
    pds_dl.add_argument("source", help="Provider (kaggle, hf, zenodo, url, or auto)")
    pds_dl.add_argument("identifier", help="Dataset identifier (owner/slug, repo_id, Zenodo ID/DOI, or URL)")
    pds_dl.add_argument("--dir", help="Override target directory")
    pds_dl.add_argument("--file", help="Download a specific file only")
    pds_dl.add_argument("--no-unzip", action="store_true", help="Keep archive compressed without extracting")
    pds_dl.add_argument("--json", action="store_true", help="Output JSON")
    pds_rm = ds_sub.add_parser("remove", help="Remove a dataset from the local manifest")
    pds_rm.add_argument("identifier", help="Dataset identifier or provider:identifier key")
    pds_rm.add_argument("--delete", action="store_true", help="Also delete files from disk")
    pds_rm.add_argument("--dir", help="Override datasets directory")
    pds_insp = ds_sub.add_parser("inspect", help="Inspect dataset schema and bounded sample without wasting tokens")
    pds_insp.add_argument("target", help="Local file/directory path or tracked dataset identifier")
    pds_insp.add_argument("--rows", type=int, default=5, help="Max sample rows to display (default: 5)")
    pds_insp.add_argument("--max-chars", type=int, default=80, help="Max characters per cell/value (default: 80)")
    pds_insp.add_argument("--max-columns", type=int, default=30, help="Max columns to display (default: 30)")
    pds_insp.add_argument("--max-files", type=int, default=20, help="Max files to list for directories (default: 20)")
    pds_insp.add_argument("--dir", help="Override datasets directory")
    pds_insp.add_argument("--json", action="store_true", help="Output JSON")

    # kaggle
    p_kaggle = subparsers.add_parser("kaggle", help="Control Kaggle datasets, competitions, and kernels/notebooks")
    kg_sub = p_kaggle.add_subparsers(dest="kaggle_section", help="Kaggle section")
    pkg_st = kg_sub.add_parser("status", help="Check Kaggle authentication and default datasets folder")
    pkg_st.add_argument("--json", action="store_true", help="Output JSON")
    pkg_login = kg_sub.add_parser("login", help="Configure and verify Kaggle API credentials")
    pkg_login.add_argument("--username", help="Kaggle username")
    pkg_login.add_argument("--key", help="Kaggle API key")
    pkg_login.add_argument("--from-file", help="Path to downloaded kaggle.json")
    pkg_login.add_argument(
        "--scifi-config", action="store_true", help="Save to ~/.scifi/config.json instead of ~/.kaggle/kaggle.json"
    )
    pkg_login.add_argument("--no-verify", action="store_true", help="Skip live API verification")
    pkg_login.add_argument("--json", action="store_true", help="Output JSON")

    pkg_ds = kg_sub.add_parser("datasets", help="Manage Kaggle datasets")
    pkg_ds_sub = pkg_ds.add_subparsers(dest="kaggle_ds_action", help="Kaggle dataset action")
    pkg_ds_s = pkg_ds_sub.add_parser("search", help="Search Kaggle datasets")
    pkg_ds_s.add_argument("query", nargs="?", default="", help="Search query")
    pkg_ds_s.add_argument("--sort-by", default="hottest", help="Sort order")
    pkg_ds_s.add_argument("--page", type=int, default=1)
    pkg_ds_s.add_argument("--limit", type=int, default=20)
    pkg_ds_s.add_argument("--json", action="store_true")
    pkg_ds_f = pkg_ds_sub.add_parser("files", help="List files in a Kaggle dataset")
    pkg_ds_f.add_argument("dataset", help="Dataset ref (owner/slug)")
    pkg_ds_f.add_argument("--json", action="store_true")
    pkg_ds_d = pkg_ds_sub.add_parser("download", help="Download a Kaggle dataset")
    pkg_ds_d.add_argument("dataset", help="Dataset ref (owner/slug)")
    pkg_ds_d.add_argument("--dir", help="Override target directory")
    pkg_ds_d.add_argument("--file", help="Download specific file")
    pkg_ds_d.add_argument("--no-unzip", action="store_true")
    pkg_ds_p = pkg_ds_sub.add_parser("push", help="Create or update a Kaggle dataset from a local folder")
    pkg_ds_p.add_argument("folder", help="Local folder containing dataset files")
    pkg_ds_p.add_argument("--title", help="Dataset title")
    pkg_ds_p.add_argument("--slug", help="Dataset slug")
    pkg_ds_p.add_argument("--public", action="store_true", help="Make dataset public (default: private)")
    pkg_ds_p.add_argument("--notes", default="Uploaded via SciFi", help="Version notes")
    pkg_ds_p.add_argument("--create", action="store_true", help="Create a new dataset instead of new version")

    pkg_comp = kg_sub.add_parser("competitions", help="Manage Kaggle competitions")
    pkg_comp_sub = pkg_comp.add_subparsers(dest="kaggle_comp_action", help="Competition action")
    pkg_c_l = pkg_comp_sub.add_parser("list", help="List competitions")
    pkg_c_l.add_argument("--search", help="Search filter")
    pkg_c_l.add_argument("--category", help="Category filter")
    pkg_c_l.add_argument("--page", type=int, default=1)
    pkg_c_l.add_argument("--json", action="store_true")
    pkg_c_f = pkg_comp_sub.add_parser("files", help="List competition files")
    pkg_c_f.add_argument("competition", help="Competition slug")
    pkg_c_d = pkg_comp_sub.add_parser("download", help="Download competition data")
    pkg_c_d.add_argument("competition", help="Competition slug")
    pkg_c_d.add_argument("--dir", help="Override target directory")
    pkg_c_d.add_argument("--file", help="Download specific file")
    pkg_c_d.add_argument("--no-unzip", action="store_true")
    pkg_c_subs = pkg_comp_sub.add_parser("submissions", help="List your competition submissions")
    pkg_c_subs.add_argument("competition", help="Competition slug")
    pkg_c_subs.add_argument("--json", action="store_true")
    pkg_c_sub = pkg_comp_sub.add_parser("submit", help="Submit a prediction file to a competition")
    pkg_c_sub.add_argument("competition", help="Competition slug")
    pkg_c_sub.add_argument("file", help="Path to submission CSV/file")
    pkg_c_sub.add_argument("-m", "--message", default="Submitted via SciFi", help="Submission description")

    pkg_kern = kg_sub.add_parser("kernels", help="Control Kaggle kernels/notebooks")
    pkg_kern_sub = pkg_kern.add_subparsers(dest="kaggle_kernel_action", help="Kernel action")
    pkg_k_l = pkg_kern_sub.add_parser("list", help="List kernels")
    pkg_k_l.add_argument("--search", help="Search filter")
    pkg_k_l.add_argument("--user", help="Filter by author")
    pkg_k_l.add_argument("--page", type=int, default=1)
    pkg_k_l.add_argument("--json", action="store_true")
    pkg_k_pull = pkg_kern_sub.add_parser("pull", help="Pull a kernel's code and metadata")
    pkg_k_pull.add_argument("kernel", help="Kernel ref (owner/slug)")
    pkg_k_pull.add_argument("--dir", help="Override target directory")
    pkg_k_push = pkg_kern_sub.add_parser("push", help="Push and run a kernel from a local folder")
    pkg_k_push.add_argument("folder", help="Folder containing kernel-metadata.json and code")
    pkg_k_st = pkg_kern_sub.add_parser("status", help="Check kernel execution status")
    pkg_k_st.add_argument("kernel", help="Kernel ref (owner/slug)")
    pkg_k_out = pkg_kern_sub.add_parser("output", help="Download kernel output files and logs")
    pkg_k_out.add_argument("kernel", help="Kernel ref (owner/slug)")
    pkg_k_out.add_argument("--dir", help="Override output directory")

    # zenodo
    p_zenodo = subparsers.add_parser(
        "zenodo", aliases=["zen"], help="Connect to Zenodo, manage depositions, reserve DOIs, and upload artifacts"
    )
    zen_sub = p_zenodo.add_subparsers(dest="zenodo_action", help="Zenodo action")
    pzen_st = zen_sub.add_parser("status", help="Check Zenodo token configuration and connectivity")
    pzen_st.add_argument("--sandbox", action="store_true", help="Use sandbox.zenodo.org")
    pzen_st.add_argument("--json", action="store_true", help="Output JSON")

    pzen_login = zen_sub.add_parser("login", help="Save and verify a Zenodo Personal Access Token")
    pzen_login.add_argument("--token", required=True, help="Zenodo Personal Access Token")
    pzen_login.add_argument("--sandbox", action="store_true", help="Verify against sandbox.zenodo.org")
    pzen_login.add_argument("--no-verify", action="store_true", help="Skip live API verification")
    pzen_login.add_argument("--json", action="store_true", help="Output JSON")

    pzen_list = zen_sub.add_parser("list", help="List your Zenodo depositions")
    pzen_list.add_argument("--status", choices=["draft", "published"], help="Filter by status")
    pzen_list.add_argument("--limit", type=int, default=20, help="Max depositions to return")
    pzen_list.add_argument("-q", "--query", help="Search query")
    pzen_list.add_argument("--sandbox", action="store_true", help="Use sandbox.zenodo.org")
    pzen_list.add_argument("--json", action="store_true", help="Output JSON")

    pzen_show = zen_sub.add_parser("show", help="Show details of a Zenodo deposition")
    pzen_show.add_argument("deposition_id", help="Zenodo deposition ID")
    pzen_show.add_argument("--sandbox", action="store_true", help="Use sandbox.zenodo.org")
    pzen_show.add_argument("--json", action="store_true", help="Output JSON")

    pzen_create = zen_sub.add_parser("create", help="Create a new Zenodo draft deposition")
    pzen_create.add_argument("--title", required=True, help="Deposition title")
    pzen_create.add_argument(
        "--type", dest="upload_type", default="software", help="Upload type (software, dataset, publication, other)"
    )
    pzen_create.add_argument("--description", help="Deposition description")
    pzen_create.add_argument("--creators", help="Semicolon-separated creator names (e.g., 'Doe, Jane; Smith, John')")
    pzen_create.add_argument("--keywords", help="Comma-separated keywords")
    pzen_create.add_argument("--license", help="License ID (e.g., MIT, cc-by-4.0)")
    pzen_create.add_argument("--no-reserve-doi", action="store_true", help="Do not pre-reserve a DOI")
    pzen_create.add_argument("--sandbox", action="store_true", help="Use sandbox.zenodo.org")
    pzen_create.add_argument("--json", action="store_true", help="Output JSON")

    pzen_upd = zen_sub.add_parser("update", help="Update metadata on a draft Zenodo deposition")
    pzen_upd.add_argument("deposition_id", help="Zenodo deposition ID")
    pzen_upd.add_argument("--title", help="New title")
    pzen_upd.add_argument("--description", help="New description")
    pzen_upd.add_argument("--keywords", help="Comma-separated keywords")
    pzen_upd.add_argument("--license", help="License ID")
    pzen_upd.add_argument("--sandbox", action="store_true", help="Use sandbox.zenodo.org")
    pzen_upd.add_argument("--json", action="store_true", help="Output JSON")

    pzen_up = zen_sub.add_parser("upload", help="Upload one or more files to a draft Zenodo deposition")
    pzen_up.add_argument("deposition_id", help="Zenodo deposition ID")
    pzen_up.add_argument("files", nargs="+", help="Local file path(s) to upload")
    pzen_up.add_argument("--sandbox", action="store_true", help="Use sandbox.zenodo.org")
    pzen_up.add_argument("--json", action="store_true", help="Output JSON")

    pzen_doi = zen_sub.add_parser("reserve-doi", help="Pre-reserve a DOI for a draft Zenodo deposition")
    pzen_doi.add_argument("deposition_id", help="Zenodo deposition ID")
    pzen_doi.add_argument("--sandbox", action="store_true", help="Use sandbox.zenodo.org")
    pzen_doi.add_argument("--json", action="store_true", help="Output JSON")

    pzen_pub = zen_sub.add_parser("publish", help="Publish a draft Zenodo deposition (mints permanent DOI)")
    pzen_pub.add_argument("deposition_id", help="Zenodo deposition ID")
    pzen_pub.add_argument("--yes", action="store_true", help="Confirm permanent publication")
    pzen_pub.add_argument("--sandbox", action="store_true", help="Use sandbox.zenodo.org")
    pzen_pub.add_argument("--json", action="store_true", help="Output JSON")

    pzen_push = zen_sub.add_parser("push-submission", help="Upload SciFi submission artifacts/code bundle to Zenodo")
    pzen_push.add_argument("--deposition-id", help="Existing draft deposition ID (creates a new draft if omitted)")
    pzen_push.add_argument(
        "--bundle-dir", default="submission_bundle", help="Directory containing submission bundle artifacts"
    )
    pzen_push.add_argument("--code-dir", default=".", help="Code directory to package if no bundle files are found")
    pzen_push.add_argument("--files", nargs="*", help="Explicit file path(s) to upload")
    pzen_push.add_argument("--title", help="Title for new deposition")
    pzen_push.add_argument("--description", help="Description for new deposition")
    pzen_push.add_argument("--creators", help="Semicolon-separated creator names")
    pzen_push.add_argument("--type", dest="upload_type", default="software", help="Upload type")
    pzen_push.add_argument("--keywords", help="Comma-separated keywords")
    pzen_push.add_argument("--license", help="License ID (e.g., MIT)")
    pzen_push.add_argument("--publish", action="store_true", help="Publish immediately after uploading")
    pzen_push.add_argument("--sandbox", action="store_true", help="Use sandbox.zenodo.org")
    pzen_push.add_argument("--json", action="store_true", help="Output JSON")

    # scaffold
    p_scaffold = subparsers.add_parser(
        "scaffold",
        aliases=["new", "bootstrap"],
        help="Scaffold a standard 2-pillar academic project (paper/ + code/ + .scifi/)",
    )
    p_scaffold.add_argument("target", nargs="?", default=".", help="Target directory for project")
    p_scaffold.add_argument("--title", default="Research Manuscript", help="Manuscript title")
    p_scaffold.add_argument("--venue", default="ieee", help="Target venue profile (ieee, neurips, acm)")
    p_scaffold.add_argument("--collection", help="Link to Zotero collection")

    # adapt
    p_adapt = subparsers.add_parser(
        "adapt", aliases=["migrate"], help="Migrate legacy codebase into standard 2-pillar SciFi structure"
    )
    p_adapt.add_argument("target", nargs="?", default=".", help="Target legacy codebase directory")
    p_adapt.add_argument("--venue", default="ieee", help="Target venue profile")
    p_adapt.add_argument("--collection", help="Link to Zotero collection")
    p_adapt.add_argument(
        "--match",
        "--auto-match",
        dest="auto_match",
        action="store_true",
        help="Auto-match best overlapping existing Zotero collection instead of project name",
    )
    p_adapt.add_argument(
        "--dry-run", action="store_true", help="Preview planned directory restructuring without moving files"
    )

    # setup
    p_setup = subparsers.add_parser(
        "setup",
        aliases=["init", "i"],
        help="Configure SciFi FastMCP server for Google Antigravity (global ~/.gemini/config/mcp_config.json or workspace .agents/mcp_config.json)",
    )
    p_setup.add_argument(
        "--auto", action="store_true", help="Non-interactive setup; install to all detected environments"
    )
    p_setup.add_argument(
        "--dry-run", action="store_true", help="Print planned configuration changes without modifying files"
    )
    p_setup.add_argument("--target", type=str, help="Install to a specific configuration file path")
    p_setup.add_argument("--scifi-root", type=str, help="Custom root directory for scifi repository")
    p_setup.add_argument("--list", action="store_true", help="List all supported and detected AI environments")
    p_setup.add_argument(
        "--rules", action="store_true", help="Synchronize SciFi scientific rules to workspace AGENTS.md"
    )
    p_setup.add_argument(
        "--workspace",
        action="store_true",
        help="Configure workspace Antigravity MCP manifest (.agents/mcp_config.json) and sync AGENTS.md",
    )
    p_setup.add_argument(
        "--use-uvx", action="store_true", help="Configure MCP client to execute via zero-install 'uvx scifi server'"
    )

    # sync
    p_sync = subparsers.add_parser("sync", help="Synchronize SciFi scientific rules to workspace AGENTS.md")
    p_sync.add_argument(
        "--dry-run", action="store_true", help="Print planned rule synchronization without modifying files"
    )

    # compile
    p_compile = subparsers.add_parser(
        "compile", aliases=["c", "build"], help="Compile a LaTeX manuscript and diagnose build errors"
    )
    p_compile.add_argument(
        "tex_file", nargs="?", default="main.tex", help="Path to main LaTeX (.tex) file (default: main.tex)"
    )
    p_compile.add_argument(
        "--engine",
        choices=["auto", "latexmk", "pdflatex", "xelatex", "lualatex"],
        default="auto",
        help="LaTeX engine to use (default: auto)",
    )
    p_compile.add_argument(
        "--no-clean", dest="clean", action="store_false", default=True, help="Do not remove auxiliary files"
    )
    p_compile.add_argument(
        "--render",
        "--render-pages",
        dest="render",
        action="store_true",
        help="Render compiled PDF pages to PNG screenshots for visual inspection",
    )
    p_compile.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # server
    p_server = subparsers.add_parser("server", aliases=["mcp", "serve"], help="Run the SciFi FastMCP server daemon")
    p_server.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio", help="MCP transport mode (default: stdio)"
    )

    # ui (cockpit)
    p_ui = subparsers.add_parser(
        "ui", aliases=["cockpit", "web"], help="Launch local SciFi Web Research Cockpit dashboard"
    )
    p_ui.add_argument("--port", type=int, default=8080, help="Port to bind Web Cockpit server (default: 8080)")
    p_ui.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    p_ui.add_argument("--no-browser", action="store_true", help="Do not automatically open web browser")
    p_ui.add_argument(
        "--db",
        default=str(DEFAULT_CENTRAL_STORE_PATH),
        help=f"Path to SQLite central store (default: {DEFAULT_CENTRAL_STORE_PATH})",
    )

    # package (bundle)
    p_package = subparsers.add_parser(
        "package", aliases=["bundle"], help="Build release packages (PyPI distributions and AI Agent Plugin bundle)"
    )
    p_package.add_argument(
        "--output-dir", "-o", default="dist", help="Output directory for generated packages (default: dist)"
    )
    p_package.add_argument("--plugin-only", action="store_true", help="Build only the AI Agent Plugin zip bundle")
    p_package.add_argument("--python-only", action="store_true", help="Build only Python wheel and source distribution")

    # upgrade (self-update)
    p_upgrade = subparsers.add_parser(
        "upgrade", aliases=["self-update"], help="Check for updates or upgrade SciFi using its detected install method"
    )
    p_upgrade.add_argument("--check", action="store_true", help="Check PyPI for a newer version without installing")
    p_upgrade.add_argument(
        "--dry-run", action="store_true", help="Print the planned upgrade command without executing it"
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """
    Main CLI entrypoint for SciFi.

    Args:
        argv: Command-line arguments. Defaults to sys.argv[1:].

    Returns:
        Exit code: 0 on success, non-zero on error.
    """
    reconfig_out = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfig_out):
        try:
            reconfig_out(encoding="utf-8", errors="replace")
            reconfig_err = getattr(sys.stderr, "reconfigure", None)
            if callable(reconfig_err):
                reconfig_err(encoding="utf-8", errors="replace")
        except Exception:
            pass

    actual_argv = list(sys.argv[1:] if argv is None else argv)

    try:
        from scifi.lifecycle import ensure_migrated_on_startup

        ensure_migrated_on_startup()
    except Exception:
        pass

    # Support nested Argus subcommands: `scifi argus scan ...` or `scifi argus search ...` or `scifi argus audit ...`
    if (
        len(actual_argv) > 1
        and actual_argv[0] in ("argus", "cite", "attribution")
        and actual_argv[1] in ("audit", "scan", "search")
    ):
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

    if args.command not in (
        "doctor",
        "doc",
        "check-paper",
        "setup",
        "init",
        "i",
        "upgrade",
        "zotero",
        "zot",
        "scaffold",
        "new",
        "bootstrap",
        "adapt",
        "migrate",
        "config",
        "cfg",
        "server",
    ):
        from scifi.literature.zotero.sync import run_auto_sync_once

        run_auto_sync_once()

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
            subparsers = getattr(parser, "_subparsers", None)
            actions = getattr(subparsers, "_actions", []) if subparsers else []
            for action in actions:
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
            subparsers = getattr(parser, "_subparsers", None)
            actions = getattr(subparsers, "_actions", []) if subparsers else []
            for action in actions:
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
    elif args.command in ("orwell", "stylometry", "prose"):
        return cmd_orwell(args)
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
    elif args.command in ("datasets", "ds", "data"):
        return cmd_datasets(args)
    elif args.command == "kaggle":
        return cmd_kaggle(args)
    elif args.command in ("zenodo", "zen"):
        return cmd_zenodo(args)
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
    elif args.command in ("upgrade", "self-update"):
        from scifi.lifecycle import perform_upgrade

        return perform_upgrade(
            dry_run=getattr(args, "dry_run", False),
            check_only=getattr(args, "check", False),
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
