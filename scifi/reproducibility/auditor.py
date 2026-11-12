"""Conference Reproducibility and Open-Science Checklist Auditor (bacon)."""

from __future__ import annotations

import re
from pathlib import Path

from scifi.latex.project import resolve_latex_project
from scifi.reproducibility.models import (
    ReproducibilityAuditResult,
    ReproducibilityCategory,
    ReproducibilityIssue,
)


def audit_reproducibility(
    tex_path: Path | str,
    venue: str = "neurips",
    double_blind: bool = False,
) -> ReproducibilityAuditResult:
    """Audit manuscript against conference reproducibility checklists (NeurIPS/ICML/IEEE)."""
    target_path = Path(tex_path)
    if target_path.exists():
        try:
            proj = resolve_latex_project(target_path)
            full_text = proj.merged_text
        except Exception:
            full_text = target_path.read_text(encoding="utf-8", errors="replace")
    else:
        full_text = str(tex_path)

    # Strip comments
    clean_lines = [re.sub(r"(?<!\\)%.*$", "", line) for line in full_text.splitlines()]
    clean_text = "\n".join(clean_lines)

    checklist: dict[str, bool] = {}
    issues: list[ReproducibilityIssue] = []

    # 1. Random seeds & trial counts
    has_seeds = bool(
        re.search(r"\b(?:random\s+seeds?|seeds?\s*(?:=|in|\{)|over\s+\d+\s+seeds?)\b", clean_text, re.IGNORECASE)
    )
    checklist["seeds_specified"] = has_seeds
    if not has_seeds:
        issues.append(
            ReproducibilityIssue(
                category=ReproducibilityCategory.RANDOM_SEEDS,
                severity="WARNING",
                message="No explicit random seed specification found (e.g., 'evaluated across 5 random seeds').",
                recommendation="Specify exact random seeds and the number of runs to comply with conference reproducibility rubrics.",
            )
        )

    # 2. Error bars / confidence intervals / std
    has_error_bars = bool(
        re.search(
            r"(?:\\pm|\\mp|std\b|standard\s+deviation|confidence\s+intervals?|\bCI\b|error\s+bars?)",
            clean_text,
            re.IGNORECASE,
        )
    )
    checklist["error_bars_specified"] = has_error_bars
    if not has_error_bars:
        issues.append(
            ReproducibilityIssue(
                category=ReproducibilityCategory.ERROR_BARS,
                severity="WARNING",
                message="Empirical evaluation lacks explicit error bars, standard deviation (\\pm), or confidence intervals.",
                recommendation="Report mean values paired with standard deviations ($\\pm \\sigma$) or 95% confidence intervals.",
            )
        )

    # 3. Compute resources
    has_compute = bool(
        re.search(
            r"\b(?:NVIDIA|A100|H100|V100|RTX\s*\d+|TPU|GPU\s*hours?|compute\s*hours?|cluster)\b",
            clean_text,
            re.IGNORECASE,
        )
    )
    checklist["compute_specified"] = has_compute
    if not has_compute:
        issues.append(
            ReproducibilityIssue(
                category=ReproducibilityCategory.COMPUTE_RESOURCES,
                severity="WARNING",
                message="No compute hardware specifications or training hours disclosed (e.g., GPU type, number of devices, total compute hours).",
                recommendation="Add compute infrastructure details and training duration in the Experimental Setup or Appendix.",
            )
        )

    # 4. Hyperparameters
    has_hyperparams = bool(
        re.search(
            r"\b(?:learning\s+rate|batch\s+size|optimizer|weight\s+decay|hyperparameters?|grid\s+search)\b",
            clean_text,
            re.IGNORECASE,
        )
    )
    checklist["hyperparameters_specified"] = has_hyperparams
    if not has_hyperparams:
        issues.append(
            ReproducibilityIssue(
                category=ReproducibilityCategory.HYPERPARAMETERS,
                severity="WARNING",
                message="No hyperparameter tuning, search ranges, or optimizer configurations documented.",
                recommendation="Include a hyperparameter specification table detailing search bounds, learning rates, and batch sizes.",
            )
        )

    # 5. Code repository & anonymization
    github_links = re.findall(r"https?://(?:www\.)?github\.com/([a-zA-Z0-9_\-]+)/([a-zA-Z0-9_\-]+)", clean_text)
    anon_links = re.findall(r"anonymous\.4open\.science|openreview\.net/attachment", clean_text)

    if double_blind and github_links:
        checklist["code_link_anonymized"] = False
        issues.append(
            ReproducibilityIssue(
                category=ReproducibilityCategory.DOUBLE_BLIND_CODE,
                severity="CRITICAL",
                message=f"Direct personal GitHub repository link detected ({github_links[0][0]}/{github_links[0][1]}) under double-blind review.",
                recommendation="Replace direct GitHub links with an anonymized repository (e.g., Anonymous GitHub) to prevent desk rejection.",
            )
        )
    elif double_blind and anon_links:
        checklist["code_link_anonymized"] = True
    else:
        checklist["code_link_anonymized"] = bool(
            github_links or anon_links or "code will be made available" in clean_text.lower()
        )

    # Compute reproducibility score
    pass_count = sum(1 for v in checklist.values() if v)
    total_checks = len(checklist)
    score = int((pass_count / total_checks) * 100) if total_checks else 100

    return ReproducibilityAuditResult(
        status="SUCCESS",
        venue=venue,
        score=score,
        checklist_items=checklist,
        issues=issues,
    )
