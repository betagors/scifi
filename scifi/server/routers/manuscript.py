"""
FastMCP Router for Manuscript Verification, Compilation & Peer Review.
"""

from __future__ import annotations

from typing import Any

from scifi.doctor import audit_manuscript
from scifi.figures import audit_figure_accessibility
from scifi.human import audit_human_prose
from scifi.latex import check_venue_compliance, generate_latex_table
from scifi.layout import audit_trim_budget
from scifi.proofs import audit_latex_proofs
from scifi.rebuttal import diff_manuscript, format_rebuttal_scaffold
from scifi.reproducibility import audit_reproducibility
from scifi.review import audit_claims
from scifi.server.app import mcp
from scifi.shannon import evaluate_manuscript_metadata


@mcp.tool()
def scifi_compile_latex(
    entrypoint: str,
    engine: str = "latexmk",
    clean: bool = True,
) -> dict[str, Any]:
    """
    Autonomously compile LaTeX manuscripts with automated log error parsing and engine diagnostics.

    Args:
        entrypoint: Path to the main .tex manuscript file.
        engine: Compiler engine ('latexmk', 'pdflatex', 'xelatex', 'lualatex').
        clean: Whether to clean auxiliary build files upon completion.

    Returns:
        Dictionary with status (SUCCESS / ERROR), engine used, pdf_path, error list, and log excerpt.
    """
    import scifi.server as srv

    return srv.compile_latex(entrypoint=entrypoint, engine=engine, clean=clean)


@mcp.tool()
def scifi_audit_claims(
    file_path: str,
) -> dict[str, Any]:
    """
    Audit academic manuscript text for unstated assumptions, unhedged overclaims, and sweeping statements.

    Args:
        file_path: Path to LaTeX (.tex) or markdown/text manuscript file (or raw content string).

    Returns:
        Dictionary with status, total_flags, and detailed list of flagged statements with line numbers and reviewer critiques.
    """
    return audit_claims(tex_content_or_path=file_path)


@mcp.tool()
def scifi_audit_manuscript(
    tex_or_dir_path: str = ".",
    bib_path: str | None = None,
    venue: str | None = None,
    double_blind: bool | None = None,
    compile_pdf: bool = False,
    live: bool = False,
    output_report: str | None = None,
) -> dict[str, Any]:
    """
    Run the complete 6-stage SciFi Manuscript Readiness Pipeline (doctor) across a single .tex
    file or multi-file LaTeX project directory (main.tex + sections/*.tex).
    Combines Alex (bib cross-check), Argus (attribution), Turing (cross-section notation),
    Popper (claims), Shannon (title/abstract triage), and Venue/Double-Blind compliance.
    """
    return audit_manuscript(
        tex_or_dir_path=tex_or_dir_path,
        bib_path=bib_path,
        venue=venue,
        double_blind=double_blind,
        compile_pdf=compile_pdf,
        live=live,
        output_report=output_report,
    )


@mcp.tool()
def scifi_evaluate_title_abstract(
    title: str | None = None,
    abstract: str | None = None,
    keywords: list[str] | str | None = None,
    tex_path: str | None = None,
    target_venue: str | None = None,
    live: bool = False,
) -> dict[str, Any]:
    """
    Evaluate academic manuscript title, 5-beat cognitive abstract, and author keywords
    using Shannon's 100-point Reviewer Triage Scorecard and SEO checks.
    Accepts either explicit title/abstract/keywords OR tex_path (single .tex or multi-file directory).
    """
    return evaluate_manuscript_metadata(
        title=title,
        abstract=abstract,
        keywords=keywords,
        tex_path=tex_path,
        target_venue=target_venue,
        live=live,
    )


@mcp.tool()
def scifi_generate_latex_table(
    data_input: str | list[dict[str, Any]],
    caption: str = "Experimental comparison against state-of-the-art baselines.",
    label: str = "tab:results",
    lower_is_better: list[str] | None = None,
    precision: int = 2,
    highlight_best: bool = True,
    highlight_second: bool = True,
    output_path: str | None = None,
) -> dict[str, Any]:
    """
    Generate a publication-grade LaTeX booktabs table from CSV file, JSON file, or inline row objects.
    Automatically bolds best values (textbf), underlines second-best (underline), and pairs _std/_ci columns as $mean +- std$.
    """
    return generate_latex_table(
        data_input=data_input,
        caption=caption,
        label=label,
        lower_is_better=lower_is_better,
        precision=precision,
        highlight_best=highlight_best,
        highlight_second=highlight_second,
        output_path=output_path,
    )


@mcp.tool()
def scifi_check_venue_compliance(
    tex_or_dir_path: str,
    venue: str | None = None,
    double_blind: bool = False,
    author_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Audit a single-file or multi-file LaTeX project (main.tex + sections/*.tex) for venue compliance,
    double-blind anonymization leaks, forbidden negative vspace / margin hacks, and unreferenced floats.
    """
    return check_venue_compliance(
        tex_or_dir_path=tex_or_dir_path,
        venue=venue,
        double_blind=double_blind,
        author_names=author_names,
    )


@mcp.tool()
def scifi_audit_human(
    tex_or_dir_path: str,
    output_report: str | None = None,
) -> dict[str, Any]:
    """
    Audit a LaTeX manuscript (single .tex file or multi-file directory) or academic prose
    across 6 forensic stylometric and structural AI-detection dimensions:
    (1) List environments (R_IB bold ratio and item length CV),
    (2) Document preamble package stack and hyperref stereotyping,
    (3) Tabular column rigidity,
    (4) Macro abstraction ratio (mu_macro),
    (5) Mathematical syntax quirks (in-equation commentary rho_math_text, un-scoped subscripts, trapped punctuation),
    (6) Prose stylometry (Kobak et al. excess AI vocabulary, em-dashes, and sentence-length burstiness B_length).
    """
    return audit_human_prose(
        tex_or_dir_path=tex_or_dir_path,
        output_report=output_report,
    )


@mcp.tool()
def scifi_audit_figures(
    tex_path: str,
    base_dir: str | None = None,
    min_dpi: int = 300,
) -> dict[str, Any]:
    """
    Audit figures in a LaTeX manuscript for print resolution (min DPI >= 300),
    vector vs raster format for charts/plots, subfigure parity ((a), (b), (c) in body text),
    and colorblind accessibility (red/green curve collisions).
    """
    return audit_figure_accessibility(tex_path=tex_path, base_dir=base_dir, min_dpi=min_dpi)


@mcp.tool()
def scifi_trim_budget(
    tex_path: str,
    bib_path: str | None = None,
) -> dict[str, Any]:
    """
    Analyze LaTeX manuscript and BibTeX bibliography for legitimate typographic line savings:
    identifies widow/orphan lines in paragraphs (1-3 trailing words), condenses BibTeX conference/journal
    titles using standard ISO-4/IEEE abbreviations, and suggests float compaction.
    """
    res = audit_trim_budget(tex_path=tex_path, bib_path=bib_path)
    return res.to_dict()


@mcp.tool()
def scifi_audit_proofs(
    tex_path: str,
) -> dict[str, Any]:
    """
    Audit mathematical theorems, lemmas, propositions, and corollaries for completeness:
    detects orphan theorems lacking inline proofs or explicit pointers to appendix derivations,
    and verifies that referenced appendix labels exist.
    """
    res = audit_latex_proofs(tex_path=tex_path)
    return res.to_dict()


@mcp.tool()
def scifi_audit_reproducibility(
    tex_path: str,
    venue: str = "neurips",
    double_blind: bool = False,
) -> dict[str, Any]:
    """
    Audit manuscript against conference reproducibility checklists (NeurIPS/ICML/IEEE):
    checks for explicit random seeds, trial counts, error bars (+- std), compute hardware disclosures,
    hyperparameter specifications, and double-blind repository anonymization.
    """
    res = audit_reproducibility(tex_path=tex_path, venue=venue, double_blind=double_blind)
    return res.to_dict()


@mcp.tool()
def scifi_format_rebuttal(
    reviews_text: str,
    venue: str = "openreview",
) -> dict[str, Any]:
    """
    Parse raw peer reviews into a disciplined, 4-beat author response template:
    (1) Summary & Direct Answer, (2) Action Taken & Manuscript Revision,
    (3) Empirical/Theoretical Evidence, (4) Revised Manuscript Excerpt.
    """
    res = format_rebuttal_scaffold(reviews_text=reviews_text, venue=venue)
    return res.to_dict()


@mcp.tool()
def scifi_diff_manuscript(
    old_tex_path: str,
    new_tex_path: str,
    generate_pdf: bool = False,
    output_tex: str | None = None,
) -> dict[str, Any]:
    """
    Perform a section-by-section diff between two LaTeX manuscripts, generating a markdown diff ledger
    and invoking latexdiff (if installed) to generate marked-up LaTeX diff and revision PDF.
    """
    res = diff_manuscript(
        old_tex_path=old_tex_path,
        new_tex_path=new_tex_path,
        generate_pdf=generate_pdf,
        output_tex=output_tex,
    )
    return res.to_dict()
