"""Standalone Unblinded Title Page Generator for Academic Submissions."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Sequence

from scifi.latex.project import resolve_latex_project
from scifi.submission.models import AuthorInfo, TitlePageResult
from scifi.submission.profiles import get_publisher_profile


def extract_metadata_from_latex(tex_path: str | Path) -> tuple[str, list[AuthorInfo], str]:
    """Extract paper title, author roster, and abstract from a LaTeX file."""
    p = Path(tex_path)
    if not p.exists():
        return "", [], ""

    try:
        proj = resolve_latex_project(p)
        full_text = proj.merged_text
    except Exception:
        full_text = p.read_text(encoding="utf-8", errors="replace")

    # Title
    m_title = re.search(r"\\title\s*\{([^}]+)\}", full_text)
    title = m_title.group(1).strip() if m_title else ""

    # Abstract
    m_abs = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", full_text, re.DOTALL)
    abstract = m_abs.group(1).strip() if m_abs else ""

    # Authors
    authors: list[AuthorInfo] = []
    m_auth = re.search(r"\\author\s*\{([^}]+)\}", full_text)
    if m_auth:
        raw_authors = m_auth.group(1)
        # Check for unblinded author blocks
        for chunk in re.split(r"\\and|\band\b|\\\\", raw_authors):
            name = re.sub(r"\\thanks\{[^}]*\}|\\IEEEauthorblockN\{|\}", "", chunk).strip()
            if name and not any(w in name.lower() for w in ("anonymous", "blind", "under review", "author")):
                authors.append(AuthorInfo(name=name, affiliation="University/Institution", email="author@institution.edu"))

    return title, authors, abstract


def generate_title_page(
    title: str | None = None,
    authors: Sequence[AuthorInfo] | None = None,
    venue: str = "general",
    manuscript_path: str | Path | None = None,
    abstract: str | None = None,
    funding: str | None = None,
    conflicts: str | None = None,
    data_availability: str | None = None,
    output_path: str | Path | None = None,
) -> TitlePageResult:
    """
    Generate an unblinded Title Page document in LaTeX and Markdown for review fairness.
    """
    profile = get_publisher_profile(venue)

    extracted_title, extracted_authors, extracted_abs = "", [], ""
    if manuscript_path:
        extracted_title, extracted_authors, extracted_abs = extract_metadata_from_latex(manuscript_path)

    final_title = title or extracted_title or "Manuscript Title"
    final_abs = abstract or extracted_abs

    author_list = list(authors) if authors else extracted_authors
    if not author_list:
        author_list = [
            AuthorInfo(
                name="[Author Name]",
                affiliation="[Affiliation / Department / Institution]",
                email="corresponding@institution.edu",
                orcid="0000-0000-0000-0000",
                is_corresponding=True,
                credit_role="Conceptualization, Methodology, Writing - original draft",
            )
        ]

    # Map unique affiliations to numerical indices
    affiliations_map: dict[str, int] = {}
    for a in author_list:
        if a.affiliation not in affiliations_map:
            affiliations_map[a.affiliation] = len(affiliations_map) + 1

    # Find corresponding author
    corr = next((a for a in author_list if a.is_corresponding), author_list[0])

    # Build Markdown
    md_lines: list[str] = [
        f"# Title Page: {final_title}\n",
        "## Authors and Affiliations\n",
    ]
    for a in author_list:
        idx = affiliations_map[a.affiliation]
        corr_star = "*" if a.is_corresponding else ""
        orcid_str = f" (ORCID: {a.orcid})" if a.orcid else ""
        md_lines.append(f"- **{a.name}**^{idx}{corr_star}^{orcid_str}")

    md_lines.append("\n## Affiliations\n")
    for aff, idx in affiliations_map.items():
        md_lines.append(f"{idx}. {aff}")

    md_lines.append(f"\n* Corresponding author: {corr.email} ({corr.name})")

    if funding:
        md_lines.append(f"\n## Funding / Grant Disclosures\n{funding}")

    if conflicts or profile.venue_id in ("elsevier", "springer"):
        conf_text = conflicts or "The authors declare that they have no known competing financial interests or personal relationships that could have appeared to influence the work reported in this paper."
        md_lines.append(f"\n## Declaration of Competing Interests\n{conf_text}")

    if profile.require_credit_statement or any(a.credit_role for a in author_list):
        md_lines.append("\n## CRediT Authorship Contribution Statement")
        for a in author_list:
            role = a.credit_role or "Conceptualization, Methodology, Writing - review & editing"
            md_lines.append(f"- **{a.name}**: {role}.")

    if data_availability:
        md_lines.append(f"\n## Data and Code Availability\n{data_availability}")

    md_text = "\n".join(md_lines)

    # Build Standalone LaTeX Title Page
    tex_lines = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[margin=1in]{geometry}",
        r"\usepackage{hyperref}",
        r"\usepackage{authblk}",
        r"\title{" + final_title + r"}",
    ]

    for a in author_list:
        idx = affiliations_map[a.affiliation]
        corr_mark = r"$^*$" if a.is_corresponding else ""
        tex_lines.append(f"\\author[{idx}]{{{a.name}{corr_mark}}}")

    for aff, idx in affiliations_map.items():
        tex_lines.append(f"\\affil[{idx}]{{{aff}}}")

    tex_lines.extend([
        r"\date{\today}",
        r"\begin{document}",
        r"\maketitle",
        r"\thispagestyle{empty}",
        r"\vspace{1em}",
        f"\\noindent $^*$Corresponding author: \\texttt{{{corr.email}}}\\\\ ",
    ])
    if corr.orcid:
        tex_lines.append(f"\\noindent ORCID: \\url{{https://orcid.org/{corr.orcid}}}\\\\ ")

    if funding:
        tex_lines.extend([
            r"\section*{Funding and Grant Acknowledgments}",
            funding,
        ])

    conf_text = conflicts or "The authors declare that they have no known competing financial interests or personal relationships."
    tex_lines.extend([
        r"\section*{Declaration of Competing Interests}",
        conf_text,
    ])

    if profile.require_credit_statement or any(a.credit_role for a in author_list):
        tex_lines.extend([
            r"\section*{CRediT Authorship Contribution Statement}",
            r"\begin{description}",
        ])
        for a in author_list:
            role = a.credit_role or "Writing - original draft, Methodology"
            tex_lines.append(f"  \\item[{a.name}:] {role}.")
        tex_lines.append(r"\end{description}")

    if data_availability:
        tex_lines.extend([
            r"\section*{Data and Code Availability}",
            data_availability,
        ])

    tex_lines.append(r"\end{document}")
    tex_text = "\n".join(tex_lines)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.suffix == ".tex":
            out.write_text(tex_text, encoding="utf-8")
        else:
            out.write_text(md_text, encoding="utf-8")

    return TitlePageResult(
        status="SUCCESS",
        title=final_title,
        venue=profile.venue_id,
        authors_count=len(author_list),
        latex_text=tex_text,
        markdown_text=md_text,
        output_path=str(output_path) if output_path else None,
    )
