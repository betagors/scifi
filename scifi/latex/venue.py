"""
scifi.latex.venue — Multi-File Venue Compliance & Double-Blind Anonymization Auditor.

Audits single-file or multi-file LaTeX projects (`main.tex` + `sections/*.tex`) for:
1. Double-blind anonymization leaks:
   - Non-anonymized `\\author{...}` blocks or `\\affiliation{...}`
   - `\\thanks{...}` grant/institution disclosures
   - `\\section*{Acknowledgments}` or `acknowledgments` environments
   - Self-identifying URLs (e.g. non-anonymous GitHub links) or whitelisted author names
2. Layout & formatting hacks forbidden by top venues (IEEE, NeurIPS, ICML, CVPR, ACM):
   - Negative `\\vspace{-...}` compression hacks
   - `\\baselinestretch` or `\\linespread` tampering
   - `\\geometry{...}` or `\\setlength{\\textwidth}` margin tampering
3. Cross-file float & prose hygiene:
   - Defined `\\label{fig:...}` or `\\label{tab:...}` never referenced via `\\ref`/`\\cref`/`\\autoref`
   - Conversational em-dashes (`---` or `—`) in academic prose
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from scifi.latex.project import RE_COMMENT, resolve_latex_project


RE_NEG_VSPACE = re.compile(r"\\vspace\*?\s*\{\s*-[0-9.]+")
RE_LINE_SPREAD = re.compile(r"\\(?:renewcommand\s*\{\s*\\baselinestretch\s*\}|linespread\s*\{)")
RE_MARGIN_HACK = re.compile(
    r"\\(?:geometry\s*\{|setlength\s*\{\s*\\(?:textwidth|textheight|topmargin|oddsidemargin|evensidemargin)\s*\})"
)
RE_AUTHOR_CMD = re.compile(r"\\author\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
RE_THANKS_CMD = re.compile(r"\\thanks\s*\{([^}]*)\}")
RE_ACK_SECTION = re.compile(
    r"\\(?:section|subsection|paragraph)\*?\s*\{\s*acknowledge?ments?\s*\}|\\begin\s*\{\s*ack(?:s|nowledgments?)?\s*\}",
    re.IGNORECASE,
)
RE_NON_ANON_REPO = re.compile(
    r"https?://(?:www\.)?(?:github\.com|gitlab\.com|huggingface\.co)/(?!anonymous)[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
    re.IGNORECASE,
)
RE_LABEL = re.compile(r"\\label\s*\{\s*([^}]+?)\s*\}")
RE_REF = re.compile(r"\\(?:[a-zA-Z]*ref|subref)\*?\s*\{\s*([^}]+?)\s*\}")
RE_RASTER_GRAPHICS = re.compile(
    r"\\includegraphics(?:\[[^\]]*\])?\s*\{\s*([^}]+\.(?:png|jpg|jpeg|bmp))\s*\}",
    re.IGNORECASE,
)
RE_EM_DASH = re.compile(r"(?<!-)---(?!-)|—")

ANONYMOUS_MARKERS = ("anonymous", "blind", "under review", "paper id", "submission id")


def check_venue_compliance(
    tex_or_dir_path: str | Path,
    venue: str | None = None,
    double_blind: bool = False,
    author_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Audit a single-file or multi-file LaTeX manuscript for venue compliance,
    double-blind anonymization leaks, formatting hacks, and cross-file float references.
    """
    try:
        proj = resolve_latex_project(tex_or_dir_path)
    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
        }

    venue_norm = (venue or "general").strip().lower()
    # NeurIPS, ICML, ICLR, CVPR, ACL, EMNLP, AAAI, CCS are double-blind by default
    if venue_norm in ("neurips", "icml", "iclr", "cvpr", "iccv", "eccv", "acl", "emnlp", "aaai", "ccs"):
        double_blind = True

    issues: list[dict[str, Any]] = []
    defined_labels: dict[str, tuple[str, int]] = {}
    referenced_labels: set[str] = set()

    author_list = [a.strip() for a in (author_names or []) if a.strip()]

    for src_file in proj.files:
        rel = src_file.relative_path
        for line_idx, raw_line in enumerate(src_file.lines, start=1):
            clean_line = RE_COMMENT.sub("", raw_line)
            if not clean_line.strip():
                continue

            # 1. Negative \vspace hacks
            if RE_NEG_VSPACE.search(clean_line):
                issues.append({
                    "category": "LAYOUT_HACK",
                    "severity": "WARNING",
                    "file": rel,
                    "line": line_idx,
                    "message": "Negative \\vspace detected; often Desk-Rejected by IEEE/NeurIPS/ACM formatting checks.",
                    "snippet": clean_line.strip()[:120],
                })

            # 2. Baselinestretch / linespread tampering
            if RE_LINE_SPREAD.search(clean_line):
                issues.append({
                    "category": "LAYOUT_HACK",
                    "severity": "ERROR",
                    "file": rel,
                    "line": line_idx,
                    "message": "Line spacing override (\\baselinestretch or \\linespread) violates standard venue style guides.",
                    "snippet": clean_line.strip()[:120],
                })

            # 3. Margin tampering
            if RE_MARGIN_HACK.search(clean_line):
                issues.append({
                    "category": "LAYOUT_HACK",
                    "severity": "WARNING",
                    "file": rel,
                    "line": line_idx,
                    "message": "Explicit page geometry/margin modification detected; verify compliance with venue template.",
                    "snippet": clean_line.strip()[:120],
                })

            # 4. Double-blind anonymization checks
            if double_blind:
                m_auth = RE_AUTHOR_CMD.search(clean_line)
                if m_auth:
                    auth_body = m_auth.group(1).strip().lower()
                    if auth_body and not any(m in auth_body for m in ANONYMOUS_MARKERS):
                        issues.append({
                            "category": "ANONYMIZATION_LEAK",
                            "severity": "ERROR",
                            "file": rel,
                            "line": line_idx,
                            "message": f"Non-anonymized \\author{{{m_auth.group(1).strip()[:50]}}} block in double-blind mode.",
                            "snippet": clean_line.strip()[:120],
                        })

                if RE_THANKS_CMD.search(clean_line):
                    issues.append({
                        "category": "ANONYMIZATION_LEAK",
                        "severity": "ERROR",
                        "file": rel,
                        "line": line_idx,
                        "message": "\\thanks{...} footnote detected in double-blind mode (may leak institution or grant IDs).",
                        "snippet": clean_line.strip()[:120],
                    })

                if RE_ACK_SECTION.search(clean_line):
                    issues.append({
                        "category": "ANONYMIZATION_LEAK",
                        "severity": "ERROR",
                        "file": rel,
                        "line": line_idx,
                        "message": "Acknowledgments section present in double-blind submission.",
                        "snippet": clean_line.strip()[:120],
                    })

                m_repo = RE_NON_ANON_REPO.search(clean_line)
                if m_repo:
                    issues.append({
                        "category": "ANONYMIZATION_LEAK",
                        "severity": "WARNING",
                        "file": rel,
                        "line": line_idx,
                        "message": f"Potential non-anonymized repository URL '{m_repo.group(0)}' in double-blind mode (use anonymous.4open.science).",
                        "snippet": clean_line.strip()[:120],
                    })

                for a_name in author_list:
                    if re.search(r"\b" + re.escape(a_name) + r"\b", clean_line, re.IGNORECASE):
                        issues.append({
                            "category": "ANONYMIZATION_LEAK",
                            "severity": "ERROR",
                            "file": rel,
                            "line": line_idx,
                            "message": f"Author name '{a_name}' appears in manuscript text during double-blind audit.",
                            "snippet": clean_line.strip()[:120],
                        })

            # 5. Conversational em-dashes in prose (outside math/tables)
            if RE_EM_DASH.search(clean_line) and not clean_line.strip().startswith("\\"):
                issues.append({
                    "category": "STYLE_HYGIENE",
                    "severity": "INFO",
                    "file": rel,
                    "line": line_idx,
                    "message": "Em-dash (--- or —) detected; academic rules recommend parentheses, commas, or discrete clauses.",
                    "snippet": clean_line.strip()[:120],
                })

            # 6. Collect labels & references across all project files
            for lm in RE_LABEL.finditer(clean_line):
                lbl = lm.group(1).strip()
                if lbl:
                    defined_labels[lbl] = (rel, line_idx)

            for rm in RE_REF.finditer(clean_line):
                for part in rm.group(1).split(","):
                    if part.strip():
                        referenced_labels.add(part.strip())

    # Check for unreferenced figure/table labels across the whole project
    unreferenced_floats: list[dict[str, Any]] = []
    for lbl, (rel_file, l_no) in defined_labels.items():
        if lbl.startswith(("fig:", "tab:", "alg:")) and lbl not in referenced_labels:
            unreferenced_floats.append({"label": lbl, "file": rel_file, "line": l_no})
            issues.append({
                "category": "UNREFERENCED_FLOAT",
                "severity": "WARNING",
                "file": rel_file,
                "line": l_no,
                "message": f"Float label '\\label{{{lbl}}}' is defined in {rel_file}:{l_no} but never referenced via \\ref/\\cref in any section.",
                "snippet": f"\\label{{{lbl}}}",
            })

    # Check for missing includes
    for missing_inc in proj.missing_includes:
        issues.append({
            "category": "MISSING_INCLUDE",
            "severity": "ERROR",
            "file": proj.entrypoint.name,
            "line": 1,
            "message": f"Included LaTeX file '{missing_inc}' could not be found on disk.",
            "snippet": f"\\input{{{missing_inc}}}",
        })

    errors_count = sum(1 for i in issues if i["severity"] == "ERROR")
    warnings_count = sum(1 for i in issues if i["severity"] == "WARNING")

    return {
        "status": "COMPLIANT" if errors_count == 0 and warnings_count == 0 else ("VIOLATIONS_FOUND" if errors_count > 0 else "WARNINGS_FOUND"),
        "is_compliant": errors_count == 0,
        "venue": venue_norm,
        "double_blind": double_blind,
        "entrypoint": str(proj.entrypoint),
        "is_multifile": proj.is_multifile,
        "files_scanned": [f.relative_path for f in proj.files],
        "errors_count": errors_count,
        "warnings_count": warnings_count,
        "total_issues": len(issues),
        "unreferenced_floats": unreferenced_floats,
        "issues": issues,
    }
