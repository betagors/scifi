"""
scifi.review.claims — Adversarial claim scanner and assumption auditor.

Scans LaTeX manuscript text, single .tex files, or multi-file LaTeX projects
(via \\input / \\include) for:
- Overstated impact adverbs without quantitative bounds
- Absolute claims of total elimination or solution
- Unhedged optimality assertions
- Unverified priority claims ("first to...")
- Sweeping superiority claims over all existing methods
- Fragile idealized assumptions (perfect CSI, perfect information)
"""

from __future__ import annotations

import re
from pathlib import Path

from scifi.latex.project import resolve_latex_project

# Common patterns indicating unhedged or sweeping claims
OVERCLAIM_PATTERNS: list[tuple[str, str]] = [
    (
        r"\b(drastically|dramatically|enormously|tremendously)\s+(improves?|improved|improving|reduces?|reduced|reducing|increases?|increased|increasing)\b",
        "Overstated impact adverb without exact quantitative bound",
    ),
    (
        r"\b(completely|totally|entirely)\s+(eliminat(e|es|ed|ing)|solv(e|es|ed|ing))\b",
        "Absolute claim of total elimination/solution",
    ),
    (
        r"(?<!sub-)(?<!near-)(?<!quasi-)(?<!non-)\b(optimal|optimality)\b(?!\s+(bound|guarantee|condition|policy|gap|sub-))",
        "Claim of 'optimal' without formal optimality condition or proof context",
    ),
    (
        r"\b(first\s+work\s+to|for\s+the\s+first\s+time|first\s+paper\s+to|first\s+to)\b",
        "Priority claim ('first to...') requiring exhaustive literature proof",
    ),
    (
        r"\boutperform(s|ed|ing)?\s+all\s+(existing|prior|state-of-the-art)\b",
        "Sweeping superiority claim over all existing methods",
    ),
    (
        r"\bperfect\s+(information|knowledge|csi|synchronization)\b",
        "Fragile idealized assumption: verify if justified in system model",
    ),
    (
        r"\b((?:novel|new|so-called|apparent)\s+(?:[a-zA-Z\-]+\s+)?paradox|(?:standard|classical|conventional)\s+[a-zA-Z\-]+\s+(?:theory|analysis|framework|condition)\s+(?:completely\s+)?(?:breaks?\s+down|fails?))\b",
        "Potential strawman theory critique ('paradox' / 'classical theory breaks down'): verify that standard assumptions are not mischaracterized and frame refinements on their exact merit",
    ),
    (
        r"\b((?:slsqp|bfgs|l-bfgs|nelder-mead|cobyla)[^.\n]{0,60}\b(?:socp|sdp|milp|lp|conic)\s+solver|\b(?:socp|sdp|milp|lp|conic)\s+solver[^.\n]{0,60}\b(?:slsqp|bfgs|l-bfgs|nelder-mead|cobyla))\b",
        "Formulation class vs. numerical solver conflation: distinguish the mathematical problem class (e.g., LP/SOCP/SDP/MILP) from the general-purpose numerical solver executed in code",
    ),
    (
        r"\b((?:fitted|regression)\s+(?:curve|trend|line|model|fit)\s+(?:quantitatively\s+)?(?:verifies|validates|confirms|proves)\s+(?:the\s+)?(?:theoretical|analytical|derived)\s+(?:bound|theorem|constant))\b",
        "Empirical curve-fit vs. analytical bound conflation: a regression fit demonstrates functional scaling consistency, not quantitative verification of analytical bound constants unless slopes and baselines match",
    ),
]


_TABLE_LATENCY_RE = re.compile(
    r"(?:~|\\approx\s*)?\b\d+(?:\.\d+)?\s*(?:\\,|~)?(?:ms|msec|sec|seconds)\b",
    re.IGNORECASE,
)
_CITE_RE = re.compile(r"\\cite[pt]?\s*\{")
_FOOTNOTE_MARKER_RE = re.compile(r"(\\textsuperscript|\\tnote|\\footnote|\^[{]?[a-zA-Z*]+[}]?)")


def _normalize_numeric_cell(cell: str) -> str:
    """Normalize a LaTeX table cell for invariance comparison."""
    cleaned = re.sub(r"\\(?:mathbf|textbf|mathrm|text|textit)\{([^}]*)\}", r"\1", cell)
    cleaned = cleaned.replace("$", "").replace("\\,", "").replace("~", " ")
    return " ".join(cleaned.split()).strip()


def _scan_tables(lines: list[str], source_file: str | None = None) -> list[dict]:
    """Scan LaTeX tabular blocks for cross-paper latency comparisons and policy-invariant columns."""
    flagged: list[dict] = []
    clean_lines = [re.sub(r"(?<!\\)%.*$", "", line) for line in lines]
    full_text = "\n".join(clean_lines)
    if "\\begin{tabular" not in full_text:
        return flagged

    for match in re.finditer(r"\\begin\{tabular\*?\}.*?\\end\{tabular\*?\}", full_text, re.DOTALL):
        start_line = full_text[: match.start()].count("\n") + 1
        block = match.group(0)
        # Check surrounding table environment for explicit hardware/invariance notes
        ctx_start = max(0, match.start() - 400)
        ctx_end = min(len(full_text), match.end() + 400)
        surrounding = full_text[ctx_start:ctx_end].lower()

        body = re.sub(r"^\\begin\{tabular\*?\}(?:\{[^}]*\}){1,2}", "", block)
        body = re.sub(r"\\end\{tabular\*?\}$", "", body)
        raw_rows = [r.strip() for r in re.split(r"\\\\(?:\[[^\]]*\])?", body) if r.strip()]

        rows: list[list[str]] = []
        for raw_row in raw_rows:
            row_clean = re.sub(r"\\(?:toprule|midrule|bottomrule|hline)\b", "", raw_row)
            row_clean = re.sub(r"\\cline\{[^}]*\}", "", row_clean).strip()
            if not row_clean or "\\multicolumn" in row_clean:
                continue
            cells = [c.strip() for c in re.split(r"(?<!\\)&", row_clean)]
            if len(cells) >= 2:
                rows.append(cells)

        if len(rows) < 2:
            continue

        # 1. Cross-paper wall-clock latency in cited literature tables
        cited_latency_rows = [
            r for r in rows[1:] if _CITE_RE.search(" ".join(r)) and _TABLE_LATENCY_RE.search(" ".join(r))
        ]
        if len(cited_latency_rows) >= 2 and not any(
            k in surrounding for k in ("disparate hardware", "different hardware", "same hardware", "as-reported")
        ):
            item: dict = {
                "line": start_line,
                "matched_text": "Cross-paper wall-clock latency table",
                "critique": (
                    "Literature comparison table compares raw wall-clock runtime (ms/s) across cited papers "
                    "with potentially disparate hardware, problem scales, or software stacks. Prefer "
                    "hardware-agnostic complexity/paradigm comparisons or add an explicit disparate-hardware footnote."
                ),
                "snippet": cited_latency_rows[0][0][:120],
            }
            if source_file:
                item["file"] = source_file
            flagged.append(item)

        # 2. Policy-invariant numeric columns in evaluation tables (>= 3 data rows)
        data_rows = rows[1:]
        if len(data_rows) >= 3:
            header = rows[0]
            num_cols = min(len(header), min(len(r) for r in data_rows))
            for col_idx in range(num_cols):
                if _FOOTNOTE_MARKER_RE.search(header[col_idx]):
                    continue
                norm_vals = []
                for r in data_rows:
                    cell = r[col_idx]
                    if _CITE_RE.search(cell):
                        continue
                    norm = _normalize_numeric_cell(cell)
                    if re.search(r"\d", norm):
                        norm_vals.append(norm)
                if len(norm_vals) >= 3 and len(norm_vals) == len(data_rows) and len(set(norm_vals)) == 1:
                    item = {
                        "line": start_line,
                        "matched_text": f"Identical column '{header[col_idx][:40]}': {norm_vals[0]}",
                        "critique": (
                            "Invariant/degenerate table column (identical value across all rows) may look like a "
                            "copy-paste error to reviewers. Replace with a discriminative metric and note the "
                            "invariant in the caption, or attach a column-header footnote explaining why it is invariant."
                        ),
                        "snippet": f"{header[col_idx]} -> {norm_vals[0]}"[:120],
                    }
                    if source_file:
                        item["file"] = source_file
                    flagged.append(item)

    return flagged


def _scan_lines(lines: list[str], source_file: str | None = None) -> list[dict]:
    flagged_issues: list[dict] = []
    for line_idx, line in enumerate(lines, start=1):
        # Strip unescaped TeX comments
        clean_line = re.sub(r"(?<!\\)%.*$", "", line).strip()
        if not clean_line:
            continue

        for pattern, rule_desc in OVERCLAIM_PATTERNS:
            matches = re.finditer(pattern, clean_line, re.IGNORECASE)
            for m in matches:
                item: dict = {
                    "line": line_idx,
                    "matched_text": m.group(0),
                    "critique": rule_desc,
                    "snippet": clean_line[:120],
                }
                if source_file:
                    item["file"] = source_file
                flagged_issues.append(item)
    flagged_issues.extend(_scan_tables(lines, source_file=source_file))
    return flagged_issues


def audit_claims(tex_content_or_path: str | Path) -> dict:
    """
    Audit LaTeX manuscript text, file, or multi-file LaTeX directory for overclaims
    and unstated/fragile assumptions.

    Args:
        tex_content_or_path: Path to a .tex/.md file, project directory, or raw text content string.

    Returns:
        dict: {
            "status": "SUCCESS" | "ERROR",
            "file": str (optional),
            "files_scanned": list[str] (optional),
            "total_flags": int,
            "flags": list[dict],
            "message": str (on error)
        }
    """
    file_path: str | None = None
    files_scanned: list[str] = []
    flagged_issues: list[dict] = []

    if isinstance(tex_content_or_path, Path):
        if not tex_content_or_path.exists():
            return {
                "status": "ERROR",
                "message": f"File not found: {tex_content_or_path}",
                "error_message": f"File not found: {tex_content_or_path}",
            }
        if tex_content_or_path.is_dir() or tex_content_or_path.suffix.lower() == ".tex":
            try:
                proj = resolve_latex_project(tex_content_or_path)
                file_path = str(proj.entrypoint)
                files_scanned = [f.relative_path for f in proj.files]
                for src_file in proj.files:
                    src_label = src_file.relative_path if proj.is_multifile else None
                    flagged_issues.extend(_scan_lines(src_file.lines, source_file=src_label))
            except Exception as e:
                return {
                    "status": "ERROR",
                    "message": str(e),
                    "error_message": str(e),
                }
        else:
            file_path = str(tex_content_or_path)
            text = tex_content_or_path.read_text(encoding="utf-8", errors="replace")
            flagged_issues.extend(_scan_lines(text.splitlines()))
    elif isinstance(tex_content_or_path, str):
        if "\n" not in tex_content_or_path:
            p = Path(tex_content_or_path)
            try:
                if p.exists():
                    if p.is_dir() or p.suffix.lower() == ".tex":
                        proj = resolve_latex_project(p)
                        file_path = str(proj.entrypoint)
                        files_scanned = [f.relative_path for f in proj.files]
                        for src_file in proj.files:
                            src_label = src_file.relative_path if proj.is_multifile else None
                            flagged_issues.extend(_scan_lines(src_file.lines, source_file=src_label))
                    else:
                        file_path = str(p)
                        text = p.read_text(encoding="utf-8", errors="replace")
                        flagged_issues.extend(_scan_lines(text.splitlines()))
                elif (
                    tex_content_or_path.endswith(".tex")
                    or tex_content_or_path.endswith(".md")
                    or tex_content_or_path.endswith(".txt")
                ):
                    return {
                        "status": "ERROR",
                        "message": f"File not found: {tex_content_or_path}",
                        "error_message": f"File not found: {tex_content_or_path}",
                    }
                else:
                    flagged_issues.extend(_scan_lines(tex_content_or_path.splitlines()))
            except (OSError, ValueError):
                flagged_issues.extend(_scan_lines(tex_content_or_path.splitlines()))
        else:
            flagged_issues.extend(_scan_lines(tex_content_or_path.splitlines()))
    else:
        return {
            "status": "ERROR",
            "message": f"Invalid input type: {type(tex_content_or_path).__name__}",
        }

    result: dict = {
        "status": "SUCCESS",
        "total_flags": len(flagged_issues),
        "flags": flagged_issues,
    }
    if file_path:
        result["file"] = file_path
    if files_scanned:
        result["files_scanned"] = files_scanned

    return result
