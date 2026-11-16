"""Reproducibility, ML-Systems Reporting, and Statistical-Pitfall Auditor (bacon)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from scifi.latex.project import resolve_latex_project
from scifi.reproducibility.models import (
    ReproducibilityAuditResult,
    ReproducibilityCategory,
    ReproducibilityIssue,
)

SUPPORTED_STANDARDS = ("ml", "ml-systems")


@dataclass(frozen=True)
class _CheckSpec:
    """Declarative specification for a single checklist item."""

    key: str
    category: ReproducibilityCategory
    pattern: str
    severity: str
    message: str
    recommendation: str


_CORE_ML_SPECS: tuple[_CheckSpec, ...] = (
    _CheckSpec(
        key="seeds_specified",
        category=ReproducibilityCategory.RANDOM_SEEDS,
        pattern=r"\b(?:random\s+seeds?|seeds?\s*(?:=|in|\{)|over\s+\d+\s+seeds?|across\s+\d+\s+(?:random\s+)?seeds?)\b",
        severity="WARNING",
        message="No explicit random seed specification found (e.g., 'evaluated across 5 random seeds').",
        recommendation="Specify exact random seeds and the number of runs to comply with conference reproducibility rubrics.",
    ),
    _CheckSpec(
        key="error_bars_specified",
        category=ReproducibilityCategory.ERROR_BARS,
        pattern=r"(?:\\pm|\\mp|std\b|standard\s+deviation|confidence\s+intervals?|\bCI\b|error\s+bars?)",
        severity="WARNING",
        message="Empirical evaluation lacks explicit error bars, standard deviation (\\pm), or confidence intervals.",
        recommendation="Report mean values paired with standard deviations ($\\pm \\sigma$) or 95% confidence intervals.",
    ),
    _CheckSpec(
        key="compute_specified",
        category=ReproducibilityCategory.COMPUTE_RESOURCES,
        pattern=r"\b(?:NVIDIA|A100|H100|V100|RTX\s*\d+|TPU|GPU\s*hours?|compute\s*hours?|cluster)\b",
        severity="WARNING",
        message="No compute hardware specifications or training hours disclosed (e.g., GPU type, number of devices, total compute hours).",
        recommendation="Add compute infrastructure details and training duration in the Experimental Setup or Appendix.",
    ),
    _CheckSpec(
        key="hyperparameters_specified",
        category=ReproducibilityCategory.HYPERPARAMETERS,
        pattern=r"\b(?:learning\s+rate|batch\s+size|optimizer|weight\s+decay|hyperparameters?|grid\s+search)\b",
        severity="WARNING",
        message="No hyperparameter tuning, search ranges, or optimizer configurations documented.",
        recommendation="Include a hyperparameter specification table detailing search bounds, learning rates, and batch sizes.",
    ),
)

_STANDARD_CHECKLISTS: dict[str, tuple[_CheckSpec, ...]] = {
    "ml": _CORE_ML_SPECS,
    "ml-systems": (
        *_CORE_ML_SPECS,
        _CheckSpec(
            key="system_parameters_specified",
            category=ReproducibilityCategory.SYSTEM_PARAMETERS,
            pattern=r"\b(?:simulation\s+parameters?|system\s+parameters?|parameter\s+settings?|environment\s+settings?|time[- ]?slot|horizon\s+[TKH]|discount\s+factor)\b|\\gamma\s*=",
            severity="WARNING",
            message="No explicit system/environment or simulation parameter specification found.",
            recommendation="Include a dedicated simulation/system parameter table or specification block detailing environment horizons, bounds, and operating regimes.",
        ),
        _CheckSpec(
            key="solver_or_tolerance_specified",
            category=ReproducibilityCategory.SOLVER_FIDELITY,
            pattern=r"\b(?:tolerance|stopping\s+criteri(?:on|a)|convergence\s+threshold|step[- ]?size|clip(?:ping)?\s+ratio|target\s+update|replay\s+buffer|rollouts?|episodes?|iterations?\s+per)\b",
            severity="WARNING",
            message="No numerical solver tolerance, stopping criterion, or rollout/iteration protocol specified.",
            recommendation="Document solver tolerances, stopping criteria, or training/evaluation rollout horizons.",
        ),
    ),
}


def _resolve_standard(venue: str, standard: str | None) -> str:
    """Resolve the reporting standard from an explicit flag or venue name."""
    if standard:
        norm = standard.strip().lower()
        if norm not in SUPPORTED_STANDARDS:
            raise ValueError(
                f"Unsupported reporting standard '{standard}'. Choose from: {', '.join(SUPPORTED_STANDARDS)}."
            )
        return norm
    venue_norm = venue.strip().lower()
    if venue_norm in ("ml-systems", "ieee", "ieee-t", "elsevier", "acm"):
        return "ml-systems"
    return "ml"


def _run_checklist_specs(
    clean_text: str,
    specs: tuple[_CheckSpec, ...],
    checklist: dict[str, bool],
    issues: list[ReproducibilityIssue],
) -> None:
    """Evaluate a sequence of declarative checklist specs against manuscript text."""
    for spec in specs:
        passed = bool(re.search(spec.pattern, clean_text, re.IGNORECASE))
        checklist[spec.key] = passed
        if not passed:
            issues.append(
                ReproducibilityIssue(
                    category=spec.category,
                    severity=spec.severity,
                    message=spec.message,
                    recommendation=spec.recommendation,
                )
            )


def _check_code_and_anonymization(
    clean_text: str,
    double_blind: bool,
    enforce_code_check: bool,
    checklist: dict[str, bool],
    issues: list[ReproducibilityIssue],
) -> None:
    """Check repository availability and double-blind anonymization."""
    github_links = re.findall(r"https?://(?:www\.)?github\.com/([a-zA-Z0-9_\-]+)/([a-zA-Z0-9_\-]+)", clean_text)
    anon_links = re.findall(r"anonymous\.4open\.science|openreview\.net/attachment", clean_text)
    anon_supp_archive = bool(
        re.search(
            r"(?:supplementary\s+(?:material|code|archive|file)s?|anonymized\s+(?:code|research\s+suite|archive))[^.\n]*?\.zip\b",
            clean_text,
            re.IGNORECASE,
        )
    )

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
    elif double_blind and (anon_links or anon_supp_archive):
        checklist["code_link_anonymized"] = True
    elif enforce_code_check:
        checklist["code_link_anonymized"] = bool(
            github_links or anon_links or anon_supp_archive or "code will be made available" in clean_text.lower()
        )


def _check_statistical_pitfalls(clean_text: str, issues: list[ReproducibilityIssue]) -> None:
    """Scan manuscript prose for common statistical pitfalls (multiple testing, leakage, pseudoreplication)."""
    # 1. Multiple-testing correction: >= 3 p-value assertions without any correction mention
    p_value_hits = re.findall(r"\bp\s*(?:<|<=|=)\s*0\.\d+", clean_text, re.IGNORECASE)
    has_correction = bool(
        re.search(
            r"\b(?:Bonferroni|Benjamini|Hochberg|Holm|FDR|false\s+discovery\s+rate|Tukey|Sidak|Dunnett|FWER|family[- ]wise|adjusted\s+p)\b",
            clean_text,
            re.IGNORECASE,
        )
    )
    if len(p_value_hits) >= 3 and not has_correction:
        issues.append(
            ReproducibilityIssue(
                category=ReproducibilityCategory.MULTIPLE_TESTING,
                severity="WARNING",
                message=(
                    f"Detected {len(p_value_hits)} p-value comparisons without a multiple-testing correction "
                    "(e.g., Bonferroni, Benjamini-Hochberg / FDR)."
                ),
                recommendation="Apply and report a multiple-hypothesis correction (FDR or FWER) or justify why unadjusted p-values are appropriate.",
            )
        )

    # 2. Data leakage: preprocessing / feature selection / oversampling before splitting
    leakage_match = re.search(
        r"(?:normaliz\w*|standardiz\w*|StandardScaler|feature\s+selection|PCA|imput\w*|SMOTE|oversampl\w*)"
        r"[^.]{0,80}"
        r"(?:before|prior\s+to)\s+(?:the\s+)?(?:train[- ]test\s+split|splitting|cross[- ]validation)"
        r"|(?:on|across)\s+the\s+(?:entire|whole|full)\s+dataset\s+(?:before|prior\s+to)\s+(?:splitting|cross[- ]validation)",
        clean_text,
        re.IGNORECASE,
    )
    if leakage_match:
        issues.append(
            ReproducibilityIssue(
                category=ReproducibilityCategory.DATA_LEAKAGE,
                severity="CRITICAL",
                message="Potential train/test data leakage: preprocessing, scaling, or feature selection appears to occur before data splitting.",
                recommendation="Fit all scalers, imputers, feature selectors, and oversamplers strictly inside the training fold after splitting.",
            )
        )

    # 3. Pseudoreplication / nested-variance pitfall: large rollout/sample count from <= 3 seeds/runs
    unit_match = re.search(
        r"\b(?:across|over|from|using|with)\s+(\d+)\s+(?:random\s+|training\s+|independent\s+)?(seeds?|runs?|policies|trials?|splits?|folds?|initializations?)\b"
        r"|\b(\d+)\s+(?:random\s+|training\s+|independent\s+)(seeds?|runs?|policies|initializations?)\b",
        clean_text,
        re.IGNORECASE,
    )
    n_matches = re.findall(
        r"\b(?:[Nn]\s*=\s*(\d+)|(\d{2,})\s+(?:evaluation\s+|test\s+)?(?:episodes?|rollouts?|trajectories|samples?|instances?))\b",
        clean_text,
        re.IGNORECASE,
    )
    has_nested_variance = bool(
        re.search(
            r"\bN_\{?(?:\\mathrm\{)?(?:train|eval|seed|rollout)\}?\}?"
            r"|\b(?:training\s+seeds?\s+and\s+.*?rollouts?|seed\s+variance|rollout\s+variance|mixed[- ]effect|hierarchical|nested|two[- ]stage\s+variance|across\s+seeds?\s+and\s+(?:episodes?|rollouts?))\b",
            clean_text,
            re.IGNORECASE,
        )
    )
    if unit_match and n_matches and not has_nested_variance:
        unit_count = int(unit_match.group(1) or unit_match.group(3))
        unit_label = (unit_match.group(2) or unit_match.group(4)).lower()
        max_n = max(int(g1 or g2) for g1, g2 in n_matches)
        if 1 <= unit_count <= 3 and max_n >= max(50, unit_count * 20):
            issues.append(
                ReproducibilityIssue(
                    category=ReproducibilityCategory.PSEUDOREPLICATION,
                    severity="WARNING",
                    message=(
                        f"Possible nested-variance pseudoreplication: large sample/rollout count (N={max_n}) reported "
                        f"from only {unit_count} independent {unit_label} without separating seed vs. rollout variance."
                    ),
                    recommendation=(
                        "Separate training/initialization seed variance ($N_{\\mathrm{train}}$) from evaluation rollout/split "
                        "variance ($N_{\\mathrm{eval}}$), or increase independent training seeds (>= 5)."
                    ),
                )
            )


def audit_reproducibility(
    tex_path: Path | str,
    venue: str = "neurips",
    double_blind: bool = False,
    standard: str | None = None,
    check_pitfalls: bool = True,
) -> ReproducibilityAuditResult:
    """Audit manuscript against Core ML or ML-Systems reporting checklists and statistical pitfalls."""
    resolved_standard = _resolve_standard(venue=venue, standard=standard)

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

    specs = _STANDARD_CHECKLISTS[resolved_standard]
    _run_checklist_specs(clean_text, specs, checklist, issues)
    _check_code_and_anonymization(
        clean_text=clean_text,
        double_blind=double_blind,
        enforce_code_check=(resolved_standard in ("ml", "ml-systems")),
        checklist=checklist,
        issues=issues,
    )

    if check_pitfalls:
        _check_statistical_pitfalls(clean_text, issues)

    # Compute reproducibility score
    pass_count = sum(1 for v in checklist.values() if v)
    total_checks = len(checklist)
    score = int((pass_count / total_checks) * 100) if total_checks else 100

    return ReproducibilityAuditResult(
        status="SUCCESS",
        venue=venue,
        standard=resolved_standard,
        score=score,
        checklist_items=checklist,
        issues=issues,
    )
