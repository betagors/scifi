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
]


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
