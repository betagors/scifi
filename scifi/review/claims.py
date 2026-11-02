"""
scifi.review.claims — Adversarial claim scanner and assumption auditor.

Scans LaTeX manuscript text or source files for:
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


def audit_claims(tex_content_or_path: str | Path) -> dict:
    """
    Audit LaTeX manuscript text or file for overclaims and unstated/fragile assumptions.

    Args:
        tex_content_or_path: Path to a .tex/.md file, or raw text content string.

    Returns:
        dict: {
            "status": "SUCCESS" | "ERROR",
            "file": str (optional),
            "total_flags": int,
            "flags": list[dict],
            "message": str (on error)
        }
    """
    file_path: str | None = None

    if isinstance(tex_content_or_path, Path):
        if not tex_content_or_path.exists():
            return {
                "status": "ERROR",
                "message": f"File not found: {tex_content_or_path}",
                "error_message": f"File not found: {tex_content_or_path}",
            }
        file_path = str(tex_content_or_path)
        text = tex_content_or_path.read_text(encoding="utf-8", errors="replace")
    elif isinstance(tex_content_or_path, str):
        if "\n" not in tex_content_or_path:
            p = Path(tex_content_or_path)
            try:
                if p.is_file():
                    file_path = str(p)
                    text = p.read_text(encoding="utf-8", errors="replace")
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
                    text = tex_content_or_path
            except (OSError, ValueError):
                text = tex_content_or_path
        else:
            text = tex_content_or_path
    else:
        return {
            "status": "ERROR",
            "message": f"Invalid input type: {type(tex_content_or_path).__name__}",
        }

    lines = text.splitlines()
    flagged_issues: list[dict] = []

    for line_idx, line in enumerate(lines, start=1):
        # Strip unescaped TeX comments
        clean_line = re.sub(r"(?<!\\)%.*$", "", line).strip()
        if not clean_line:
            continue

        for pattern, rule_desc in OVERCLAIM_PATTERNS:
            matches = re.finditer(pattern, clean_line, re.IGNORECASE)
            for m in matches:
                flagged_issues.append({
                    "line": line_idx,
                    "matched_text": m.group(0),
                    "critique": rule_desc,
                    "snippet": clean_line[:120],
                })

    result: dict = {
        "status": "SUCCESS",
        "total_flags": len(flagged_issues),
        "flags": flagged_issues,
    }
    if file_path:
        result["file"] = file_path

    return result
