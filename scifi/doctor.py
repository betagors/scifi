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

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import bibtexparser

from scifi.argus.engine import ArgusEngine
from scifi.cache import RegistryCache
from scifi.citation_verifier import audit_bib_file
from scifi.config import resolve_config, validate_workspace_config
from scifi.figures import audit_figure_accessibility
from scifi.latex.compiler import compile_latex
from scifi.latex.project import resolve_latex_project
from scifi.latex.venue import check_venue_compliance
from scifi.layout import audit_trim_budget
from scifi.logging import get_logger
from scifi.math.notation import check_notation
from scifi.orwell import audit_orwell_prose
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


def _extract_critical_blockers(stages: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract critical submission blockers (retractions, double-blind leaks, orphan proofs)."""
    blockers: list[dict[str, Any]] = []

    alex = stages.get("alex_bibliography", {})
    retracted = int(alex.get("retracted_count", 0) or 0)
    if retracted > 0:
        blockers.append(
            {
                "type": "retraction",
                "severity": "CRITICAL",
                "location": ", ".join(alex.get("bib_files", [])) or "bibliography",
                "message": f"{retracted} retracted paper(s) cited in bibliography.",
            }
        )

    venue = stages.get("venue_compliance", {})
    for iss in venue.get("issues", []):
        if iss.get("category") == "ANONYMIZATION_LEAK" and iss.get("severity") == "ERROR":
            loc = f"{iss.get('file', '')}:{iss.get('line', '')}".strip(":")
            blockers.append(
                {
                    "type": "double_blind_leak",
                    "severity": "CRITICAL",
                    "location": loc,
                    "message": iss.get("message", "Double-blind anonymization leak detected."),
                }
            )

    repro = stages.get("reproducibility", {})
    for iss in repro.get("issues", []):
        if str(iss.get("category", "")).lower() == "double_blind_code" and iss.get("severity") == "CRITICAL":
            blockers.append(
                {
                    "type": "double_blind_leak",
                    "severity": "CRITICAL",
                    "location": iss.get("location", "manuscript"),
                    "message": iss.get("message", "Non-anonymous repository URL detected."),
                }
            )

    proofs = stages.get("proofs_completeness", {})
    orphan_count = int(proofs.get("orphan_theorems", 0) or 0)
    if orphan_count > 0:
        proof_issues = [i for i in proofs.get("issues", []) if i.get("severity") == "CRITICAL"]
        if proof_issues:
            for pi in proof_issues:
                blockers.append(
                    {
                        "type": "orphan_proof",
                        "severity": "CRITICAL",
                        "location": pi.get("theorem", ""),
                        "message": pi.get("message", "Orphan theorem without proof."),
                    }
                )
        else:
            blockers.append(
                {
                    "type": "orphan_proof",
                    "severity": "CRITICAL",
                    "location": "proofs",
                    "message": f"{orphan_count} orphan theorem(s) lacking proof or appendix reference.",
                }
            )

    return blockers


def _extract_issue_signatures(stages: dict[str, Any]) -> dict[str, str]:
    """Build deterministic issue_id -> description mapping for cross-draft diffing."""
    issues: dict[str, str] = {}

    alex = stages.get("alex_bibliography", {})
    for key in alex.get("missing_bib_keys", []):
        issues[f"alex:missing_bib:{key}"] = f"Missing .bib key: {key}"
    if int(alex.get("retracted_count", 0) or 0) > 0:
        issues["alex:retracted_citations"] = f"{alex['retracted_count']} retracted citation(s)"

    argus = stages.get("argus_attribution", {})
    for f in argus.get("findings", []):
        src = f.get("source_file", "")
        ent = f.get("matched_entity", "")
        issues[f"argus:{src}:{ent}"] = f"Argus ({src}): {ent}"

    turing = stages.get("turing_notation", {})
    for ms in turing.get("multi_variant_symbols", []):
        sym = ms.get("base_symbol", "")
        issues[f"turing:notation:{sym}"] = f"Inconsistent notation for '{sym}'"

    popper = stages.get("popper_claims", {})
    for fl in popper.get("flags", []):
        src = fl.get("file", "")
        txt = (fl.get("matched_text", "") or "")[:40]
        issues[f"popper:{src}:{txt}"] = f"Popper ({src}): {txt}"

    shannon = stages.get("shannon_metadata", {})
    triage = shannon.get("triage_score")
    if isinstance(triage, (int, float)) and triage < 70:
        issues["shannon:low_triage_score"] = f"Title/Abstract Triage Score < 70 ({triage}/100)"

    venue = stages.get("venue_compliance", {})
    for iss in venue.get("issues", []):
        if iss.get("severity") in ("ERROR", "WARNING"):
            cat = iss.get("category", "")
            src = iss.get("file", "")
            msg = (iss.get("message", "") or "")[:60]
            issues[f"venue:{cat}:{src}:{msg}"] = f"[{iss.get('severity')}] {src}: {msg}"

    human = stages.get("human_stylometry", {})
    h_score = human.get("human_score")
    if isinstance(h_score, (int, float)) and h_score < 70:
        issues["human:low_authenticity_score"] = f"Human Authenticity Score < 70 ({h_score}/100)"

    figures = stages.get("figures_visual", {})
    for fi in figures.get("issues", []):
        if fi.get("severity") == "CRITICAL":
            cat = fi.get("category", "")
            ref = fi.get("figure_ref", "")
            issues[f"figures:{cat}:{ref}"] = f"Figure '{ref}': {(fi.get('message', '') or '')[:60]}"

    proofs = stages.get("proofs_completeness", {})
    for pi in proofs.get("issues", []):
        cat = pi.get("category", "")
        thm = pi.get("theorem", "")
        issues[f"proofs:{cat}:{thm}"] = f"Proof '{thm}': {(pi.get('message', '') or '')[:60]}"

    return issues


def _history_file_path(tex_or_dir_path: str | Path) -> Path:
    """Resolve the .scifi/audit_history.json path for a workspace or file."""
    p = Path(tex_or_dir_path)
    workspace_dir = p if p.is_dir() else p.parent
    return workspace_dir / ".scifi" / "audit_history.json"


def load_audit_history(tex_or_dir_path: str | Path = ".") -> list[dict[str, Any]]:
    """Load persisted doctor audit runs from `.scifi/audit_history.json`."""
    hist_path = _history_file_path(tex_or_dir_path)
    if not hist_path.is_file():
        return []
    try:
        data = json.loads(hist_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("runs"), list):
            return data["runs"]
    except Exception as e:
        logger.warning("Failed to read audit history at %s: %s", hist_path, e)
    return []


def record_audit_history(
    workspace_dir: Path,
    result: dict[str, Any],
    venue: str,
    double_blind: bool,
) -> dict[str, Any]:
    """Persist a doctor run to `.scifi/audit_history.json` and return the delta vs previous run."""
    hist_path = workspace_dir / ".scifi" / "audit_history.json"
    runs = load_audit_history(workspace_dir)

    stages = result.get("stages", {})
    curr_issues = _extract_issue_signatures(stages)
    curr_score = int(result.get("readiness_score", 0))
    blockers = result.get("critical_blockers", [])

    prev = runs[-1] if runs else None
    run_number = len(runs) + 1

    if prev is not None:
        prev_issues = prev.get("issues", {})
        if not isinstance(prev_issues, dict):
            prev_issues = {}
        prev_keys = set(prev_issues.keys())
        curr_keys = set(curr_issues.keys())
        fixed_keys = sorted(prev_keys - curr_keys)
        regressed_keys = sorted(curr_keys - prev_keys)
        prev_score = int(prev.get("readiness_score", 0))
        delta: dict[str, Any] = {
            "history_path": str(hist_path),
            "run_number": run_number,
            "previous_run_number": prev.get("run_number", len(runs)),
            "previous_timestamp": prev.get("timestamp"),
            "previous_score": prev_score,
            "score_delta": curr_score - prev_score,
            "fixed_issues": [{"id": k, "description": prev_issues[k]} for k in fixed_keys],
            "regressed_issues": [{"id": k, "description": curr_issues[k]} for k in regressed_keys],
            "persisting_issues_count": len(curr_keys & prev_keys),
        }
    else:
        delta = {
            "history_path": str(hist_path),
            "run_number": run_number,
            "previous_run_number": None,
            "previous_timestamp": None,
            "previous_score": None,
            "score_delta": None,
            "fixed_issues": [],
            "regressed_issues": [],
            "persisting_issues_count": len(curr_issues),
        }

    entry = {
        "run_number": run_number,
        "timestamp": datetime.now(UTC).isoformat(),
        "entrypoint": result.get("project", {}).get("entrypoint"),
        "venue": venue,
        "double_blind": double_blind,
        "readiness_score": curr_score,
        "readiness_tier": result.get("readiness_tier"),
        "critical_blockers_count": len(blockers),
        "critical_blockers": blockers,
        "issues": curr_issues,
    }
    runs.append(entry)

    hist_path.parent.mkdir(parents=True, exist_ok=True)
    hist_path.write_text(
        json.dumps({"schema_version": 1, "runs": runs}, indent=2),
        encoding="utf-8",
    )
    return delta


def audit_manuscript(
    tex_or_dir_path: str | Path = ".",
    bib_path: str | Path | None = None,
    venue: str | None = None,
    double_blind: bool | None = None,
    compile_pdf: bool = False,
    live: bool = False,
    output_report: str | Path | None = None,
    persist_history: bool = True,
    parallel: bool = True,
    render_previews: bool = False,
) -> dict[str, Any]:
    """
    Run the complete SciFi Manuscript Readiness Pipeline on a single .tex file
    or multi-file LaTeX project directory (`main.tex` + `sections/*.tex`).
    """
    p = Path(tex_or_dir_path)
    workspace_dir = p if p.is_dir() else p.parent
    config_validation = validate_workspace_config(workspace_dir=workspace_dir)
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

    live_cache = RegistryCache() if live else None
    live_bib_reports: list[dict[str, Any]] = []
    retracted_count = 0
    mismatch_count = 0
    if live and proj.bib_files:
        for bf in proj.bib_files:
            try:
                rep = audit_bib_file(bf, search_missing=True, cache=live_cache)
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

    # ── Stages 2–11: Independent Manuscript Audits (parallel or sequential) ──
    argus_engine = ArgusEngine(
        author_whitelist=cfg.author_whitelist,
        preprint_doi=cfg.preprint_doi,
        enable_search=live,
        cache=live_cache,
    )

    if parallel:
        with ThreadPoolExecutor(max_workers=6) as pool:
            fut_argus = pool.submit(argus_engine.audit_file, proj.entrypoint)
            fut_turing = pool.submit(check_notation, proj.entrypoint)
            fut_popper = pool.submit(audit_claims, proj.entrypoint)
            fut_shannon = pool.submit(
                evaluate_manuscript_metadata,
                tex_path=proj.entrypoint,
                target_venue=effective_venue,
                live=live,
            )
            fut_venue = pool.submit(
                check_venue_compliance,
                proj.entrypoint,
                venue=effective_venue,
                double_blind=effective_double_blind,
                author_names=cfg.author_whitelist,
            )
            fut_human = pool.submit(audit_orwell_prose, proj.entrypoint)
            fut_figures = pool.submit(audit_figure_accessibility, proj.entrypoint, render_previews=render_previews)
            fut_proofs = pool.submit(audit_latex_proofs, proj.entrypoint)
            fut_repro = pool.submit(
                audit_reproducibility,
                proj.entrypoint,
                venue=effective_venue or "neurips",
                double_blind=effective_double_blind,
            )
            fut_trim = pool.submit(audit_trim_budget, proj.entrypoint, render_previews=render_previews)

            argus_rep = fut_argus.result()
            stage_turing = fut_turing.result()
            stage_popper = fut_popper.result()
            stage_shannon = fut_shannon.result()
            stage_venue = fut_venue.result()
            stage_human = fut_human.result()
            stage_figures = fut_figures.result()
            stage_proofs = fut_proofs.result()
            stage_repro = fut_repro.result()
            stage_trim = fut_trim.result()
    else:
        argus_rep = argus_engine.audit_file(proj.entrypoint)
        stage_turing = check_notation(proj.entrypoint)
        stage_popper = audit_claims(proj.entrypoint)
        stage_shannon = evaluate_manuscript_metadata(
            tex_path=proj.entrypoint,
            target_venue=effective_venue,
            live=live,
        )
        stage_venue = check_venue_compliance(
            proj.entrypoint,
            venue=effective_venue,
            double_blind=effective_double_blind,
            author_names=cfg.author_whitelist,
        )
        stage_human = audit_orwell_prose(proj.entrypoint)
        stage_figures = audit_figure_accessibility(proj.entrypoint, render_previews=render_previews)
        stage_proofs = audit_latex_proofs(proj.entrypoint)
        stage_repro = audit_reproducibility(
            proj.entrypoint,
            venue=effective_venue or "neurips",
            double_blind=effective_double_blind,
        )
        stage_trim = audit_trim_budget(proj.entrypoint, render_previews=render_previews)

    stage_argus = argus_rep.to_dict()

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

    result["config_validation"] = config_validation
    result["critical_blockers"] = _extract_critical_blockers(result["stages"])
    if persist_history:
        result["history_delta"] = record_audit_history(
            workspace_dir=workspace_dir,
            result=result,
            venue=effective_venue,
            double_blind=effective_double_blind,
        )

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

    blockers = data.get("critical_blockers", [])
    if blockers:
        lines.append("## 🚫 Critical Submission Blockers")
        for b in blockers:
            loc = f" (`{b['location']}`)" if b.get("location") else ""
            lines.append(f"- **[{b['type'].upper()}]**{loc}: {b['message']}")
        lines.append("")

    delta = data.get("history_delta")
    if delta:
        lines.append("## 📈 Readiness Ledger (Draft Progress)")
        run_num = delta.get("run_number", 1)
        prev_score = delta.get("previous_score")
        if prev_score is not None:
            sc_delta = delta.get("score_delta", 0)
            delta_str = f"+{sc_delta}" if sc_delta > 0 else str(sc_delta)
            lines.append(f"- **Run #{run_num}** | **Score Delta:** `{delta_str} pts` (previous: {prev_score}/100)")
            fixed = delta.get("fixed_issues", [])
            regressed = delta.get("regressed_issues", [])
            lines.append(f"- **Fixed Issues ({len(fixed)}):** " + ("None" if not fixed else ""))
            for fx in fixed[:8]:
                lines.append(f"  - ✅ {fx['description']}")
            lines.append(f"- **Regressed Issues ({len(regressed)}):** " + ("None" if not regressed else ""))
            for rg_item in regressed[:8]:
                lines.append(f"  - ❌ {rg_item['description']}")
        else:
            lines.append("- **Run #1** recorded in `.scifi/audit_history.json` (baseline established).")
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
                "## 7. Orwell Academic Prose & LaTeX Stylometry (Orwell)",
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
