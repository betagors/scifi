"""
scifi.doctor — End-to-End Multi-File Manuscript Readiness Auditor.

Executes a cohesive 6-stage peer-review readiness pipeline across single-file
(`paper.tex`) or multi-file (`main.tex` + `sections/*.tex`) LaTeX projects:
1. Bibliography & Citation Cross-Check (Alex):
   - Verifies that all `\\cite{...}` keys across all sections exist in `.bib` files
   - Detects uncited `.bib` entries and (when `live=True`) audits against Crossref/OpenAlex/arXiv
2. Attribution & Plagiarism Sentinel (Argus):
   - Scans all included `.tex` files for uncredited methods and synthetic AI tropes
3. Cross-Section Mathematical Notation Consistency (Turing):
   - Checks symbol font/case variance across all sections in the merged manuscript
4. Adversarial Claims & Assumptions Audit (Popper):
   - Scans all `.tex` files for unhedged overclaims and fragile idealized assumptions
5. Title, 5-Beat Abstract & SEO Triage (Shannon):
   - Extracts `\\title`, `abstract` (even from `sections/abstract.tex`), and `\\keywords`
   - Computes the 100-point Reviewer Triage Score
6. Venue Compliance & Double-Blind Anonymization (Venue + optional Compiler):
   - Checks double-blind leaks, negative `\\vspace` hacks, and unreferenced floats across files
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import bibtexparser

from scifi.argus.engine import ArgusEngine
from scifi.citation_verifier import audit_bib_file
from scifi.config import resolve_config
from scifi.figures import audit_figure_accessibility
from scifi.human import audit_human_prose
from scifi.latex.compiler import compile_latex
from scifi.latex.project import resolve_latex_project
from scifi.latex.venue import check_venue_compliance
from scifi.layout import audit_trim_budget
from scifi.logging import get_logger
from scifi.math.notation import check_notation
from scifi.proofs import audit_latex_proofs
from scifi.reproducibility import audit_reproducibility
from scifi.review.claims import audit_claims
from scifi.shannon import evaluate_manuscript_metadata

logger = get_logger(__name__)


def _extract_bib_keys_offline(bib_paths: list[Path]) -> set[str]:
    """Parse all BibTeX entry keys from a list of .bib files without network requests."""
    keys: set[str] = set()
    for bp in bib_paths:
        try:
            content = bp.read_text(encoding="utf-8", errors="replace")
            library = bibtexparser.parse_string(content)
            for e in library.entries:
                if getattr(e, "key", None):
                    keys.add(str(e.key).strip())
        except Exception:
            try:
                raw = bp.read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(r"@\w+\s*\{\s*([^,\s]+)\s*,", raw):
                    keys.add(m.group(1).strip())
            except Exception as e:
                logger.debug("Failed regex fallback for %s: %s", bp, e)
    return keys


def audit_manuscript(
    tex_or_dir_path: str | Path = ".",
    bib_path: str | Path | None = None,
    venue: str | None = None,
    double_blind: bool | None = None,
    compile_pdf: bool = False,
    live: bool = False,
    output_report: str | Path | None = None,
) -> dict[str, Any]:
    """
    Run the complete 6-stage SciFi Manuscript Readiness Pipeline on a single .tex file
    or multi-file LaTeX project directory (`main.tex` + `sections/*.tex`).
    """
    p = Path(tex_or_dir_path)
    workspace_dir = p if p.is_dir() else p.parent
    cfg = resolve_config(workspace_dir=workspace_dir)

    effective_venue = venue or cfg.target_venue or "general"
    effective_double_blind = double_blind if double_blind is not None else cfg.double_blind
    explicit_bib = bib_path or (cfg.bib_file if (workspace_dir / cfg.bib_file).is_file() else None)

    try:
        proj = resolve_latex_project(
            tex_or_dir_path,
            configured_main=cfg.main_tex,
            explicit_bib=explicit_bib,
        )
    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
        }

    # ── Stage 1: Bibliography & Citation Cross-Check (Alex) ──────────────────
    bib_keys = _extract_bib_keys_offline(proj.bib_files)
    cited_keys_set = set(proj.cited_keys)
    missing_bib_keys = sorted(cited_keys_set - bib_keys) if proj.bib_files else list(proj.cited_keys)
    uncited_bib_keys = sorted(bib_keys - cited_keys_set)

    live_bib_reports: list[dict[str, Any]] = []
    retracted_count = 0
    mismatch_count = 0
    if live and proj.bib_files:
        for bf in proj.bib_files:
            try:
                rep = audit_bib_file(bf, search_missing=True)
                retracted_count += rep.retracted_count
                mismatch_count += rep.mismatch_count
                live_bib_reports.append(
                    {
                        "bib_file": str(bf),
                        "total_entries": rep.total_entries,
                        "verified_count": rep.verified_count,
                        "retracted_count": rep.retracted_count,
                        "mismatch_count": rep.mismatch_count,
                    }
                )
            except Exception as e:
                logger.warning("Live bibliography audit failed for %s: %s", bf, e)

    stage_alex = {
        "bib_files": [str(b) for b in proj.bib_files],
        "total_bib_entries": len(bib_keys),
        "total_cited_keys": len(proj.cited_keys),
        "missing_bib_keys": missing_bib_keys,
        "uncited_bib_keys": uncited_bib_keys,
        "retracted_count": retracted_count,
        "mismatch_count": mismatch_count,
        "live_audit": live_bib_reports if live else "SKIPPED_OFFLINE (pass --live to query Crossref/OpenAlex)",
    }

    # ── Stage 2: Attribution & Plagiarism Audit (Argus) ──────────────────────
    argus_engine = ArgusEngine(
        author_whitelist=cfg.author_whitelist,
        preprint_doi=cfg.preprint_doi,
        enable_search=live,
    )
    argus_rep = argus_engine.audit_file(proj.entrypoint)
    stage_argus = argus_rep.to_dict()

    # ── Stage 3: Cross-Section Notation Consistency (Turing) ─────────────────
    stage_turing = check_notation(proj.entrypoint)

    # ── Stage 4: Adversarial Claims Scanner (Popper) ─────────────────────────
    stage_popper = audit_claims(proj.entrypoint)

    # ── Stage 5: Title, 5-Beat Abstract & SEO Scorecard (Shannon) ────────────
    stage_shannon = evaluate_manuscript_metadata(
        tex_path=proj.entrypoint,
        target_venue=effective_venue,
        live=live,
    )

    # ── Stage 6: Venue Compliance & Double-Blind Anonymization ───────────────
    stage_venue = check_venue_compliance(
        proj.entrypoint,
        venue=effective_venue,
        double_blind=effective_double_blind,
        author_names=cfg.author_whitelist,
    )

    # ── Stage 7: Humanizer & LaTeX Forensic Stylometry (Human) ───────────────
    stage_human = audit_human_prose(proj.entrypoint)

    # ── Stage 8: Figure & Visual Accessibility (Da Vinci) ───────────────────
    stage_figures = audit_figure_accessibility(proj.entrypoint)

    # ── Stage 9: Theorem–Proof Completeness (Euclid) ────────────────────────
    stage_proofs = audit_latex_proofs(proj.entrypoint)

    # ── Stage 10: Conference Reproducibility Checklist (Bacon) ──────────────
    stage_repro = audit_reproducibility(
        proj.entrypoint,
        venue=effective_venue or "neurips",
        double_blind=effective_double_blind,
    )

    # ── Stage 11: Page Budget Micro-Trimming (Layout) ────────────────────────
    stage_trim = audit_trim_budget(proj.entrypoint)

    stage_compiler: dict[str, Any] | None = None
    if compile_pdf:
        stage_compiler = compile_latex(entrypoint=str(proj.entrypoint))

    # ── Compute Overall Readiness Score (0 - 100) ────────────────────────────
    deductions: list[str] = []
    score = 100

    # Alex deductions (up to 25 pts)
    if missing_bib_keys:
        pen = min(15, len(missing_bib_keys) * 5)
        score -= pen
        deductions.append(
            f"-{pen} pts: {len(missing_bib_keys)} cited key(s) missing from .bib ({', '.join(missing_bib_keys[:4])})"
        )
    if retracted_count > 0:
        score -= 20
        deductions.append(f"-20 pts: {retracted_count} RETRACTED paper(s) cited in bibliography")

    # Argus deductions (up to 15 pts)
    if argus_rep.total_findings > 0:
        pen = min(15, argus_rep.total_findings * 5)
        score -= pen
        deductions.append(f"-{pen} pts: {argus_rep.total_findings} attribution or AI-trope flag(s) detected by Argus")

    # Turing notation deductions (up to 15 pts)
    multi_vars = stage_turing.get("multi_variant_symbols", [])
    if multi_vars:
        pen = min(15, len(multi_vars) * 5)
        score -= pen
        deductions.append(
            f"-{pen} pts: {len(multi_vars)} mathematical symbol(s) have inconsistent font/case across sections"
        )

    # Popper overclaim deductions (up to 15 pts)
    popper_flags = stage_popper.get("total_flags", 0)
    if popper_flags > 0:
        pen = min(15, popper_flags * 5)
        score -= pen
        deductions.append(
            f"-{pen} pts: {popper_flags} unhedged overclaim(s) or fragile assumption(s) flagged by Popper"
        )

    # Shannon triage score contribution (up to 15 pts deduction if triage < 70)
    shannon_total = (
        stage_shannon.get("triage_score", {}).get("total_score", 75) if stage_shannon.get("status") == "SUCCESS" else 60
    )
    if shannon_total < 70:
        pen = min(15, max(5, (70 - shannon_total) // 2))
        score -= pen
        deductions.append(f"-{pen} pts: Title/Abstract Triage Score is {shannon_total}/100 (target >= 70)")

    # Venue & double-blind deductions (up to 20 pts)
    venue_errors = stage_venue.get("errors_count", 0)
    venue_warnings = stage_venue.get("warnings_count", 0)
    if venue_errors > 0:
        pen = min(20, venue_errors * 10)
        score -= pen
        deductions.append(f"-{pen} pts: {venue_errors} critical venue/anonymization error(s)")
    if venue_warnings > 0:
        pen = min(10, venue_warnings * 3)
        score -= pen
        deductions.append(f"-{pen} pts: {venue_warnings} venue formatting/float warning(s)")

    # Humanizer forensic stylometry deductions (up to 15 pts if human_score < 70)
    human_score = stage_human.get("human_score", 100)
    if human_score < 70:
        pen = min(15, max(5, (70 - human_score) // 2))
        score -= pen
        deductions.append(
            f"-{pen} pts: Human Authenticity Score is {human_score}/100 ({stage_human.get('classification')})"
        )

    # Figure & visual accessibility deductions
    fig_crit = [i for i in stage_figures.get("issues", []) if i.get("severity") == "CRITICAL"]
    if fig_crit:
        pen = min(15, len(fig_crit) * 5)
        score -= pen
        deductions.append(f"-{pen} pts: {len(fig_crit)} critical figure resolution/format issue(s)")

    # Proof orphan theorem deductions
    if stage_proofs.orphan_theorems > 0:
        pen = min(15, stage_proofs.orphan_theorems * 5)
        score -= pen
        deductions.append(
            f"-{pen} pts: {stage_proofs.orphan_theorems} orphan theorem(s) lacking inline proof or appendix reference"
        )

    score = max(0, score)
    readiness_tier = (
        "READY_FOR_SUBMISSION" if score >= 85 else ("NEEDS_MINOR_REVISION" if score >= 65 else "MAJOR_ISSUES_DETECTED")
    )

    result: dict[str, Any] = {
        "status": "SUCCESS",
        "readiness_score": score,
        "readiness_tier": readiness_tier,
        "deductions": deductions,
        "project": proj.to_summary_dict(),
        "stages": {
            "alex_bibliography": stage_alex,
            "argus_attribution": stage_argus,
            "turing_notation": stage_turing,
            "popper_claims": stage_popper,
            "shannon_metadata": {
                "status": stage_shannon.get("status"),
                "title": stage_shannon.get("title"),
                "triage_score": stage_shannon.get("triage_score", {}).get("total_score"),
                "triage_status": stage_shannon.get("triage_score", {}).get("status"),
                "overlap_ratio": stage_shannon.get("overlap", {}).get("overlap_ratio"),
            },
            "venue_compliance": stage_venue,
            "human_stylometry": {
                "human_score": stage_human.get("human_score"),
                "classification": stage_human.get("classification"),
                "total_flags": stage_human.get("total_flags"),
                "dimensions": stage_human.get("dimensions"),
                "flags": stage_human.get("flags", []),
            },
            "figures_visual": stage_figures,
            "proofs_completeness": stage_proofs.to_dict(),
            "reproducibility": stage_repro.to_dict(),
            "trim_budget": stage_trim.to_dict(),
            "compiler": stage_compiler,
        },
    }

    report_md = format_doctor_report_markdown(result)
    result["report_markdown"] = report_md

    if output_report:
        out_p = Path(output_report)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(report_md, encoding="utf-8")
        result["output_report"] = str(out_p.resolve())

    return result


def format_doctor_report_markdown(data: dict[str, Any]) -> str:
    """Format the 6-stage Manuscript Readiness Audit into a clean Markdown report."""
    proj = data["project"]
    stages = data["stages"]
    alex = stages["alex_bibliography"]
    argus = stages["argus_attribution"]
    turing = stages["turing_notation"]
    popper = stages["popper_claims"]
    shannon = stages["shannon_metadata"]
    venue = stages["venue_compliance"]

    score = data["readiness_score"]
    tier = data["readiness_tier"]
    badge = "✅" if score >= 85 else ("⚠️" if score >= 65 else "❌")

    lines = [
        "# 🩺 SciFi Manuscript Peer-Review Readiness Report",
        "",
        f"**Overall Readiness Score:** {badge} **{score} / 100** (`{tier}`)",
        f"**Entrypoint:** `{proj['entrypoint']}` ({'Multi-file project' if proj['is_multifile'] else 'Single-file manuscript'})",
        f"**TeX Files Scanned ({proj['tex_files_count']}):** {', '.join(f'`{f}`' for f in proj['tex_files'])}",
        f"**BibTeX Files ({len(proj['bib_files'])}):** {', '.join(f'`{Path(b).name}`' for b in proj['bib_files']) or 'None discovered'}",
        "",
    ]

    if data.get("deductions"):
        lines.append("## 🔍 Score Deductions Summary")
        for d in data["deductions"]:
            lines.append(f"- {d}")
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## 1. Bibliography & Citation Cross-Check (Alex)",
            f"- **Cited Keys in Manuscript:** {alex['total_cited_keys']}",
            f"- **Entries in `.bib`:** {alex['total_bib_entries']}",
            f"- **Missing `.bib` Definitions:** {len(alex['missing_bib_keys'])} "
            + (f"(`{', '.join(alex['missing_bib_keys'][:8])}`)" if alex["missing_bib_keys"] else "✅ None"),
            f"- **Uncited `.bib` Entries:** {len(alex['uncited_bib_keys'])} "
            + (f"(`{', '.join(alex['uncited_bib_keys'][:8])}`)" if alex["uncited_bib_keys"] else "✅ None"),
            "",
            "## 2. Attribution & AI-Prose Sentinel (Argus)",
            f"- **Total Flags:** {argus['total_findings']} (Uncredited methods: {argus['academic_count']}, Informal/AI tropes: {argus['web_count']})",
        ]
    )
    for f in argus.get("findings", [])[:5]:
        loc = f"{f.get('source_file', '')}:{f.get('line_number', '')}".strip(":")
        lines.append(f"  - `[{f['id']}]` ({loc}): **{f['matched_entity']}** -> `{f['suggested_action']}`")
    lines.append("")

    multi_syms = turing.get("multi_variant_symbols", [])
    lines.extend(
        [
            "## 3. Cross-Section Mathematical Notation (Turing)",
            f"- **Sections Scanned:** {len(turing.get('sections_scanned', []))}",
            f"- **Inconsistent Symbol Variants:** {len(multi_syms)}",
        ]
    )
    for ms in multi_syms[:5]:
        lines.append(
            f"  - Base symbol `{ms['base_symbol']}` appears as {', '.join(f'`{v}`' for v in ms['variants_seen'])} "
            f"across sections: {', '.join(ms['sections'])}"
        )
    lines.append("")

    lines.extend(
        [
            "## 4. Adversarial Claims & Assumptions (Popper)",
            f"- **Overclaims / Fragile Assumptions Flagged:** {popper.get('total_flags', 0)}",
        ]
    )
    for fl in popper.get("flags", [])[:5]:
        loc = f"{fl.get('file', '')}:{fl.get('line', '')}".strip(":")
        lines.append(f'  - Line `{loc}`: *"{fl["matched_text"]}"* — {fl["critique"]}')
    lines.append("")

    lines.extend(
        [
            "## 5. Title, 5-Beat Abstract & SEO Scorecard (Shannon)",
            f"- **Detected Title:** *{shannon.get('title') or 'Not detected'}*",
            f"- **Reviewer Triage Score:** **{shannon.get('triage_score', 'N/A')} / 100** (`{shannon.get('triage_status', 'N/A')}`)",
            f"- **Title/Keyword Overlap:** {(shannon.get('overlap_ratio') or 0) * 100:.1f}% (target < 35%)",
            "",
            "## 6. Venue Compliance & Double-Blind Anonymization",
            f"- **Venue Profile:** `{venue['venue']}` (Double-Blind: `{venue['double_blind']}`)",
            f"- **Errors:** {venue['errors_count']} | **Warnings:** {venue['warnings_count']}",
        ]
    )
    for iss in venue.get("issues", [])[:8]:
        lines.append(f"  - **[{iss['severity']}]** `{iss['file']}:{iss['line']}` ({iss['category']}): {iss['message']}")

    human = stages.get("human_stylometry", {})
    if human:
        lines.extend(
            [
                "",
                "## 7. Humanizer & LaTeX Forensic Stylometry (Human)",
                f"- **Human Authenticity Score:** **{human.get('human_score', 'N/A')} / 100** (`{human.get('classification', 'N/A')}`)",
                f"- **Forensic & Stylometric Flags:** {human.get('total_flags', 0)}",
            ]
        )
        for hf in human.get("flags", [])[:5]:
            loc = f"{hf.get('file', '')}:{hf.get('line', '')}".strip(":")
            lines.append(
                f"  - **[{hf['severity']}]** `{loc}` ({hf['dimension']}): `{hf['matched_text']}` — {hf['explanation']}"
            )

    # 8. Figure & Visual Accessibility
    fig_stage = stages.get("figures_visual", {})
    if fig_stage:
        lines.extend(
            [
                "",
                "## 8. Figure & Visual Accessibility (Da Vinci)",
                f"- **Figures Inspected:** {fig_stage.get('total_figures_inspected', 0)} | **Issues:** {fig_stage.get('total_issues', 0)} | **Visual Clean Score:** **{fig_stage.get('clean_score', 100)} / 100**",
            ]
        )
        for fi in fig_stage.get("issues", [])[:5]:
            lines.append(f"  - **[{fi['severity']}]** `{fi['figure_ref']}` ({fi['category']}): {fi['message']}")

    # 9. Theorem-Proof Completeness
    proof_stage = stages.get("proofs_completeness", {})
    if proof_stage and proof_stage.get("total_theorems", 0) > 0:
        lines.extend(
            [
                "",
                "## 9. Theorem–Proof Completeness (Euclid)",
                f"- **Theorems/Lemmas Stated:** {proof_stage.get('total_theorems', 0)} | **Orphan Claims:** {proof_stage.get('orphan_theorems', 0)}",
            ]
        )
        for pi in proof_stage.get("issues", [])[:5]:
            lines.append(f"  - **[{pi.get('severity', 'WARNING')}]** `{pi.get('theorem')}`: {pi.get('message')}")

    # 10. Conference Reproducibility Checklist
    repro_stage = stages.get("reproducibility", {})
    if repro_stage:
        lines.extend(
            [
                "",
                f"## 10. Conference Reproducibility Checklist ({repro_stage.get('venue', 'neurips').upper()})",
                f"- **Reproducibility Score:** **{repro_stage.get('score', 100)} / 100**",
            ]
        )
        for k, v in repro_stage.get("checklist_items", {}).items():
            lines.append(f"  - [{'x' if v else ' '}] `{k}`")

    # 11. Page Budget & Micro-Trimming
    trim_stage = stages.get("trim_budget", {})
    if trim_stage and trim_stage.get("total_potential_lines_saved", 0) > 0:
        lines.extend(
            [
                "",
                "## 11. Page Budget & Micro-Trimming Opportunities (Layout)",
                f"- **Estimated Recoverable Lines:** **{trim_stage.get('total_potential_lines_saved', 0)} lines**",
                f"- **Abbreviated BibTeX Entries Available:** {trim_stage.get('bibtex_condensed_entries', 0)}",
            ]
        )

    lines.append("")
    return "\n".join(lines)
