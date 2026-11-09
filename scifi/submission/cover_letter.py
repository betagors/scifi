"""Editorial Cover Letter Generator for Journal & Conference Submissions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from scifi.submission.models import AuthorInfo, CoverLetterResult, normalize_authors
from scifi.submission.profiles import get_publisher_profile
from scifi.submission.title_page import extract_metadata_from_latex


def generate_cover_letter(
    manuscript_title: str | None = None,
    journal_name: str = "Target Journal",
    venue: str = "general",
    issn: str | None = None,
    editor_name: str | None = None,
    authors: Sequence[AuthorInfo] | None = None,
    abstract: str | None = None,
    contributions: Sequence[str] | None = None,
    figure_path: str | None = None,
    prior_doi: str | None = None,
    code_link: str | None = None,
    suggested_reviewers: Sequence[dict[str, str]] | None = None,
    opposed_reviewers: Sequence[dict[str, str]] | None = None,
    manuscript_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> CoverLetterResult:
    """
    Generate an academic editorial cover letter in Markdown and LaTeX format.
    """
    profile = get_publisher_profile(venue)

    ext_title, ext_authors, ext_abs = "", [], ""
    if manuscript_path:
        ext_title, ext_authors, ext_abs = extract_metadata_from_latex(manuscript_path)

    title = manuscript_title or ext_title or "Manuscript Title"
    author_list = normalize_authors(authors)
    if not author_list:
        author_list = ext_authors
    if not author_list:
        author_list = [
            AuthorInfo(
                name="[Author Name]",
                affiliation="[Institution / Department]",
                email="corresponding@institution.edu",
                is_corresponding=True,
            )
        ]

    corr = next((a for a in author_list if a.is_corresponding), author_list[0])
    editor = editor_name or "Editor-in-Chief"
    current_date = datetime.now().strftime("%B %d, %Y")

    issn_str = f" (ISSN: {issn})" if issn else ""

    # Build Markdown Cover Letter
    md: list[str] = [
        f"**Date:** {current_date}\n",
        f"**To:** {editor}",
        f"**Journal:** *{journal_name}*{issn_str}\n",
        f"**Dear {editor},**\n",
        f"We are pleased to submit our original research manuscript entitled **\"{title}\"** for publication in *{journal_name}* as a regular research article.\n",
    ]

    # Scope & Significance
    md.append("### Background & Significance")
    if abstract or ext_abs:
        short_abs = (abstract or ext_abs).split("\n\n")[0].strip()
        md.append(f"{short_abs}\n")
    else:
        short_abs = f"The enclosed paper addresses key theoretical and empirical challenges in this domain, directly aligning with the aims and scope of *{journal_name}*."
        md.append(f"{short_abs}\n")

    # Contributions
    if contributions:
        md.append("### Key Technical Contributions")
        for c in contributions:
            md.append(f"- {c}")
        md.append("")

    # Prior conference extension (IEEE / general)
    if prior_doi or profile.require_conference_extension_clause:
        prior_ref = prior_doi or "[Prior Conference Paper DOI / Citation]"
        md.extend([
            "### Prior Publication & Significant Extension",
            f"This manuscript extends our preliminary work published at {prior_ref}. "
            "In accordance with publication ethics and venue guidelines, this journal version incorporates "
            "substantially new technical contributions (> 30–50% new material), including complete mathematical "
            "formulations, expanded experimental validation across realistic baselines, and ablation analyses not present in the conference version.\n",
        ])

    # Visual / Teaser asset
    if figure_path:
        md.extend([
            "### Graphical Abstract / Visual Summary",
            f"A teaser figure and graphical summary representing our primary architecture is enclosed (`{figure_path}`).\n",
        ])

    # Springer Ethics
    if profile.require_ethics_declaration:
        md.extend([
            "### Ethics & Integrity Declarations",
            "- **Research Involving Human and/or Animal Participants:** This research did not involve human participants or animal experiments.",
            "- **Informed Consent:** Not applicable.",
            "- **Ethics Approval:** The study protocol complies with institutional and publisher research integrity standards.",
            "",
        ])

    # Declarations
    md.extend([
        "### Mandatory Declarations",
        "- **Originality:** This manuscript represents original work and is not currently under consideration for publication elsewhere.",
        "- **Authorship:** All named authors have reviewed and approved the manuscript and agree with its submission.",
        "- **Competing Interests:** The authors declare that they have no competing financial or non-financial interests.",
    ])

    if code_link:
        md.append(f"- **Data & Code Availability:** Source code, simulation scripts, and evaluation benchmarks are openly accessible at: {code_link}")
    else:
        md.append("- **Data & Code Availability:** Complete code, evaluation datasets, and environment setup scripts are packaged and available to reviewers upon request.")

    # Suggested & Opposed Reviewers
    if suggested_reviewers:
        md.append("\n### Suggested Reviewers")
        for r in suggested_reviewers:
            md.append(f"- **{r.get('name', 'Expert Reviewer')}** ({r.get('institution', 'Institution')}): `{r.get('email', '')}` — *{r.get('reason', 'Domain expertise in the core methodology')}*")

    if opposed_reviewers:
        md.append("\n### Opposed Reviewers (Conflict of Interest)")
        for r in opposed_reviewers:
            md.append(f"- **{r.get('name', 'Reviewer')}** ({r.get('institution', 'Institution')}): *{r.get('reason', 'Direct competing interest')}*")

    md.extend([
        "\nThank you for considering our manuscript for review in your prestigious journal. We look forward to receiving the reviewers' constructive feedback.\n",
        "Sincerely,",
        f"**{corr.name}**",
        f"{corr.affiliation}",
        f"Email: `{corr.email}`",
    ])

    md_text = "\n".join(md)

    # Build LaTeX Letter Class
    journal_target = f"{editor}\\\\Editor-in-Chief, {journal_name}"
    if issn_str:
        journal_target += f"\\\\{issn_str}"

    tex: list[str] = [
        r"\documentclass[11pt]{letter}",
        r"\usepackage[margin=1in]{geometry}",
        r"\usepackage{hyperref}",
        f"\\address{{{corr.name}\\\\{corr.affiliation}\\\\Email: \\url{{{corr.email}}}}}",
        r"\begin{document}",
        f"\\begin{{letter}}{{{journal_target}}}",
        r"\opening{Dear " + editor + r",}",
        f"We are pleased to submit our original research manuscript entitled ``{title}'' for consideration of publication in \\textit{{{journal_name}}}.",
        r"\par\vspace{1em}",
        f"\\noindent \\textbf{{Significance:}} {short_abs}",
        r"\par\vspace{0.5em}",
    ]

    if contributions:
        tex.extend([
            r"\noindent The primary technical contributions of our work include:",
            r"\begin{itemize}",
        ])
        for c in contributions:
            tex.append(f"  \\item {c}")
        tex.append(r"\end{itemize}")

    if prior_doi or profile.require_conference_extension_clause:
        prior_ref = prior_doi or "our previous conference article"
        tex.extend([
            r"\par\vspace{0.5em}",
            f"\\noindent \\textbf{{Prior Conference Extension:}} This submission extends {prior_ref} with substantial new technical contributions ($>30\\%$ new material), including complete proofs and comprehensive baseline evaluations.",
        ])

    if figure_path:
        tex.extend([
            r"\par\vspace{0.5em}",
            f"\\noindent \\textbf{{Graphical Abstract:}} A representative teaser figure is enclosed (\\texttt{{{figure_path}}}).",
        ])

    if profile.require_ethics_declaration:
        tex.extend([
            r"\par\vspace{0.5em}",
            r"\noindent \textbf{Ethics Declarations:} The study protocol satisfies all institutional research integrity requirements and involved no human or animal experiments.",
        ])

    if suggested_reviewers:
        tex.extend([
            r"\par\vspace{0.5em}",
            r"\noindent \textbf{Suggested Reviewers:}",
            r"\begin{itemize}",
        ])
        for r in suggested_reviewers:
            tex.append(f"  \\item \\textbf{{{r.get('name', 'Reviewer')}}} ({r.get('institution', '')}) --- \\url{{{r.get('email', '')}}}")
        tex.append(r"\end{itemize}")

    if code_link:
        tex.extend([
            r"\par\vspace{0.5em}",
            f"\\noindent \\textbf{{Data & Code Availability:}} Artifacts are openly available at \\url{{{code_link}}}.",
        ])

    tex.extend([
        r"\par\vspace{0.5em}",
        r"\noindent This manuscript is original, has not been published previously, and is not currently under consideration elsewhere. All authors have approved the submission.",
        r"\closing{Sincerely,}",
        r"\end{letter}",
        r"\end{document}",
    ])

    tex_text = "\n".join(tex)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.suffix == ".tex":
            out.write_text(tex_text, encoding="utf-8")
        else:
            out.write_text(md_text, encoding="utf-8")

    return CoverLetterResult(
        status="SUCCESS",
        journal_name=journal_name,
        venue=profile.venue_id,
        markdown_text=md_text,
        latex_text=tex_text,
        output_path=str(output_path) if output_path else None,
    )
