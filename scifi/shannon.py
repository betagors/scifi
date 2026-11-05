"""
scifi.shannon — Academic Title, 5-Beat Abstract, and SEO Evaluation Engine.

Provides programmatic access to Shannon's 100-point Reviewer Triage Scorecard,
academic SEO checks, dual-audience accessibility metrics, keyword overlap/density,
and automatic extraction of \\title, abstract, and \\keywords across single-file
or multi-file LaTeX projects (e.g. main.tex + sections/abstract.tex).
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from scifi.latex.project import resolve_latex_project, strip_tex_comments
from skills.shannon.scripts.test_keywords import (
    check_keyword_relevance,
    check_title_collision,
    compute_abstract_keyword_density,
    compute_title_keyword_overlap,
    evaluate_academic_seo,
    evaluate_accessibility,
    evaluate_triage_score,
    generate_diagnostic_report,
)


RE_LATEX_CMD_CLEAN = re.compile(r"\\[a-zA-Z]+\*?\{([^}]*)\}")
RE_ABSTRACT_ENV = re.compile(
    r"\\begin\{abstract\}(.*?)\\end\{abstract\}",
    re.DOTALL | re.IGNORECASE,
)
RE_KEYWORDS_ENV = re.compile(
    r"\\begin\{(?:IEEEkeywords|keywords)\}(.*?)\\end\{(?:IEEEkeywords|keywords)\}",
    re.DOTALL | re.IGNORECASE,
)


def _extract_braced_arg(text: str, cmd_pattern: str) -> str | None:
    """Extract balanced `{...}` content following a LaTeX command like \\title or \\abstract."""
    m = re.search(cmd_pattern, text)
    if not m:
        return None
    idx = m.end()
    while idx < len(text) and text[idx].isspace():
        idx += 1
    # Skip optional [short title]
    if idx < len(text) and text[idx] == "[":
        depth_sq = 1
        idx += 1
        while idx < len(text) and depth_sq > 0:
            if text[idx] == "[":
                depth_sq += 1
            elif text[idx] == "]":
                depth_sq -= 1
            idx += 1
        while idx < len(text) and text[idx].isspace():
            idx += 1

    if idx >= len(text) or text[idx] != "{":
        return None

    depth = 1
    idx += 1
    start = idx
    while idx < len(text) and depth > 0:
        ch = text[idx]
        if ch == "{" and (idx == 0 or text[idx - 1] != "\\"):
            depth += 1
        elif ch == "}" and (idx == 0 or text[idx - 1] != "\\"):
            depth -= 1
        idx += 1

    if depth == 0:
        return text[start : idx - 1].strip()
    return None


def _clean_latex_markup(raw: str) -> str:
    """Strip common LaTeX formatting macros while preserving readable text and numbers."""
    text = strip_tex_comments(raw)
    text = text.replace("\\%", "%").replace("\\&", "&")
    text = re.sub(r"\\thanks\{[^}]*\}", "", text)
    text = re.sub(r"\\footnote\{[^}]*\}", "", text)
    text = re.sub(r"\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{[^}]*\}", "", text)
    text = re.sub(r"\\\\", " ", text)
    # Unwrap formatting commands like \textbf{...}, \emph{...}, \textit{...}
    for _ in range(3):
        text = RE_LATEX_CMD_CLEAN.sub(r"\1", text)
    text = re.sub(r"\$([^$]+)\$", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+\*?", " ", text)
    text = re.sub(r"[{}~]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_latex_metadata(path_or_tex: str | Path) -> dict[str, Any]:
    """
    Extract title, abstract, and keywords from a single .tex file, a multi-file LaTeX
    directory (where e.g. \\input{sections/abstract} holds the abstract), or raw LaTeX text.
    """
    proj = resolve_latex_project(path_or_tex)
    clean_merged = strip_tex_comments(proj.merged_text)

    # 1. Title
    raw_title = _extract_braced_arg(clean_merged, r"\\title\b")
    title = _clean_latex_markup(raw_title) if raw_title else ""

    # 2. Abstract (\begin{abstract}...\end{abstract} or \abstract{...})
    raw_abstract: str | None = None
    m_abs = RE_ABSTRACT_ENV.search(clean_merged)
    if m_abs:
        raw_abstract = m_abs.group(1)
    else:
        raw_abstract = _extract_braced_arg(clean_merged, r"\\abstract\b")
    abstract = _clean_latex_markup(raw_abstract) if raw_abstract else ""

    # 3. Keywords (\begin{IEEEkeywords}, \begin{keywords}, \keywords{...}, \ccsdesc{...})
    raw_kw: str | None = None
    m_kw = RE_KEYWORDS_ENV.search(clean_merged)
    if m_kw:
        raw_kw = m_kw.group(1)
    else:
        raw_kw = _extract_braced_arg(clean_merged, r"\\(?:keywords|IEEEkeywords)\b")

    keywords: list[str] = []
    if raw_kw:
        cleaned_kw = _clean_latex_markup(raw_kw)
        # Split on comma, semicolon, or \sep / \and
        parts = re.split(r"[,;•·]|\bsep\b|\band\b", cleaned_kw)
        keywords = [p.strip() for p in parts if p.strip()]

    return {
        "title": title,
        "abstract": abstract,
        "keywords": keywords,
        "entrypoint": str(proj.entrypoint),
        "files_scanned": [f.relative_path for f in proj.files],
    }


def evaluate_manuscript_metadata(
    title: str | None = None,
    abstract: str | None = None,
    keywords: list[str] | str | None = None,
    tex_path: str | Path | None = None,
    target_venue: str | None = None,
    live: bool = False,
) -> dict[str, Any]:
    """
    Evaluate manuscript title, 5-beat abstract, and keywords using Shannon's 100-point rubric.

    Can be called either with explicit `title`, `abstract`, `keywords` strings OR with
    `tex_path` pointing to a `.tex` file or multi-file LaTeX directory.
    """
    extracted_info: dict[str, Any] = {}
    if tex_path is not None:
        try:
            extracted_info = extract_latex_metadata(tex_path)
        except Exception as e:
            return {
                "status": "ERROR",
                "error_message": str(e),
            }

    final_title = (title if title is not None else extracted_info.get("title", "")).strip()
    final_abstract = (abstract if abstract is not None else extracted_info.get("abstract", "")).strip()

    if isinstance(keywords, str):
        final_keywords = [k.strip() for k in keywords.split(",") if k.strip()]
    elif isinstance(keywords, list):
        final_keywords = [str(k).strip() for k in keywords if str(k).strip()]
    else:
        final_keywords = list(extracted_info.get("keywords", []))

    if not final_title and not final_abstract:
        return {
            "status": "ERROR",
            "error_message": "Could not find a title or abstract to evaluate. Provide --title/--abstract or a valid LaTeX manuscript.",
        }

    # If keywords are missing in the LaTeX draft, synthesize top candidate keyphrases from title/abstract
    synthesized_keywords = False
    if not final_keywords:
        synthesized_keywords = True
        words = [w.lower() for w in re.findall(r"[A-Za-z]{5,}", final_title)]
        final_keywords = list(dict.fromkeys(words[:4])) or ["scientific method"]

    triage = evaluate_triage_score(final_title, final_abstract, final_keywords)
    seo = evaluate_academic_seo(final_title, final_abstract, final_keywords)
    accessibility = evaluate_accessibility(final_abstract)
    overlap = compute_title_keyword_overlap(final_title, final_keywords)
    density = compute_abstract_keyword_density(final_abstract, final_keywords)
    collision = check_title_collision(final_title, live=live)
    relevance = check_keyword_relevance(final_keywords, live=live)

    evaluation: dict[str, Any] = {
        "status": "SUCCESS",
        "title": final_title,
        "abstract": final_abstract,
        "keywords": final_keywords,
        "keywords_synthesized": synthesized_keywords,
        "target_venue": target_venue,
        "triage_score": triage,
        "seo": seo,
        "accessibility": accessibility,
        "overlap": overlap,
        "density": density,
        "collision": collision,
        "relevance": relevance,
    }
    if extracted_info:
        evaluation["entrypoint"] = extracted_info.get("entrypoint")
        evaluation["files_scanned"] = extracted_info.get("files_scanned")

    evaluation["report_text"] = generate_diagnostic_report(evaluation)
    return evaluation
