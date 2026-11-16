"""
FastMCP Router for Manuscript Verification, Compilation & Peer Review.
"""

from __future__ import annotations

from typing import Any

from scifi.doctor import audit_manuscript
from scifi.figures import audit_figure_accessibility, detect_pdf_renderer, render_pdf_pages
from scifi.latex import check_venue_compliance, discover_tex_toolchain, generate_latex_table
from scifi.layout import audit_trim_budget
from scifi.orwell import audit_orwell_prose, calibrate_orwell_voice, verify_edit_invariants
from scifi.proofs import audit_latex_proofs
from scifi.rebuttal import diff_manuscript, format_rebuttal_scaffold
from scifi.reproducibility import audit_reproducibility
from scifi.review import audit_claims
from scifi.server.app import mcp
from scifi.shannon import evaluate_manuscript_metadata


@mcp.tool()
def scifi_compile_latex(
    entrypoint: str,
    engine: str = "auto",
    clean: bool = True,
    render_pages: bool = False,
    render_dpi: int = 150,
    max_render_pages: int = 10,
    include_raw_log: bool = False,
) -> dict[str, Any]:
    """
    Autonomously compile LaTeX manuscripts with cached toolchain auto-discovery (MiKTeX/TeX Live/TinyTeX),
    structured log error parsing, compiler metadata, and optional PDF-to-PNG page rendering.

    Args:
        entrypoint: Path to the main .tex manuscript file.
        engine: Compiler engine ('latexmk', 'pdflatex', 'xelatex', 'lualatex', or 'auto').
        clean: Whether to clean auxiliary build files upon completion.
        render_pages: If True, render compiled PDF pages to PNG screenshots for visual inspection.
        render_dpi: DPI for rendered page PNGs (default: 150).
        max_render_pages: Maximum number of pages to render when render_pages=True.
        include_raw_log: If True, include the full raw TeX compiler stdout/stderr log (default: False).

    Returns:
        Dictionary with status, engine, engine_path, distribution, compiler_version, duration_seconds,
        page_count, pdf_path, error list, and optional rendered_pages.
    """
    import scifi.server as srv

    if render_pages:
        res = srv.compile_latex(
            entrypoint=entrypoint,
            engine=engine,
            clean=clean,
            render_pages=render_pages,
            render_dpi=render_dpi,
            max_render_pages=max_render_pages,
        )
    else:
        res = srv.compile_latex(entrypoint=entrypoint, engine=engine, clean=clean)
    if not include_raw_log and isinstance(res, dict) and "log" in res:
        res = {k: v for k, v in res.items() if k != "log"}
    return res


@mcp.tool()
def scifi_compiler_info(
    workspace_dir: str | None = None,
) -> dict[str, Any]:
    """
    Inspect the active LaTeX compiler toolchain and PDF visual renderer without running a full build.
    Reports TeX distribution (MiKTeX, TeX Live, TinyTeX), exact engine paths, version, bin_dir,
    cached status, and available PDF-to-PNG renderer (pdftoppm, PyMuPDF, pypdfium2).
    """
    tc = discover_tex_toolchain(workspace_dir=workspace_dir)
    renderer = detect_pdf_renderer(extra_bin_dir=tc.get("bin_dir"))
    return {
        **tc,
        "pdf_renderer": renderer,
    }


@mcp.tool()
def scifi_render_pdf(
    pdf_path: str,
    pages: str | list[int] | None = None,
    dpi: int = 150,
    max_pages: int = 12,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """
    Render pages of a PDF manuscript or standalone figure PDF into PNG screenshots ("Eyes of SciFi")
    so the model can visually inspect layout, plots, labels, equations, and figure alignment via read_file.

    Args:
        pdf_path: Path to the PDF file to render.
        pages: Optional page numbers or range string (e.g. "1,3-5" or [1, 2]). Defaults to first max_pages.
        dpi: Rendering resolution in DPI (default: 150).
        max_pages: Maximum number of pages to render in one call (default: 12).
        output_dir: Optional directory for output PNGs (defaults to `<pdf_dir>/.scifi_renders/<stem>`).
    """
    return render_pdf_pages(
        pdf_path=pdf_path,
        output_dir=output_dir,
        pages=pages,
        dpi=dpi,
        max_pages=max_pages,
    )


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
    include_markdown: bool = False,
    render_previews: bool = False,
) -> dict[str, Any]:
    """
    Run the complete 6-stage SciFi Manuscript Readiness Pipeline (doctor) across a single .tex
    file or multi-file LaTeX project directory (main.tex + sections/*.tex).
    Combines Alex (bib cross-check), Argus (attribution), Turing (cross-section notation),
    Popper (claims), Shannon (title/abstract triage), and Venue/Double-Blind compliance.
    """
    res = audit_manuscript(
        tex_or_dir_path=tex_or_dir_path,
        bib_path=bib_path,
        venue=venue,
        double_blind=double_blind,
        compile_pdf=compile_pdf,
        live=live,
        output_report=output_report,
        render_previews=render_previews,
    )
    if not include_markdown and isinstance(res, dict) and "report_markdown" in res:
        res = {k: v for k, v in res.items() if k != "report_markdown"}
    return res


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
def scifi_audit_orwell(
    tex_or_dir_path: str,
    output_report: str | None = None,
    include_markdown: bool = False,
    include_raw_inventory: bool = False,
) -> dict[str, Any]:
    """
    Audit a LaTeX manuscript (single .tex file or multi-file directory) or academic prose
    across 6 forensic stylometric and structural dimensions (Orwell), using any calibrated
    [orwell.voice] profile in scifi.toml when present.
    """
    res = audit_orwell_prose(
        tex_or_dir_path=tex_or_dir_path,
        output_report=output_report,
        include_raw_inventory=include_raw_inventory,
    )
    if not include_markdown and isinstance(res, dict):
        omit_keys = {"report_markdown"}
        if res.get("total_flags", 0) == 0 and not include_raw_inventory:
            omit_keys.add("confounder_notes")
        res = {k: v for k, v in res.items() if k not in omit_keys}
    return res


@mcp.tool()
def scifi_calibrate_orwell(
    corpus_dir: str | None = None,
    preset: str | None = None,
    exemplar_dir: str | None = None,
    notation_only: bool = False,
    blend_preset: str | None = None,
    output_toml: str | None = None,
    write_toml: bool = True,
) -> dict[str, Any]:
    """
    Calibrate a guarded [orwell.voice] stylometric profile into scifi.toml from a built-in
    preset, an exemplar papers directory, or the author's past .tex/.pdf papers.
    """
    return calibrate_orwell_voice(
        corpus_dir=corpus_dir,
        preset=preset,
        exemplar_dir=exemplar_dir,
        notation_only=notation_only,
        blend_preset=blend_preset,
        output_toml=output_toml,
        write_toml=write_toml,
    )


@mcp.tool()
def scifi_verify_edit_invariants(
    before_input: str,
    after_input: str,
) -> dict[str, Any]:
    """
    Verify that a prose rewrite preserved all semantic invariants: numbers,
    math/equations, and \\cite{}/\\ref{}/\\eqref{}/\\label{} keys.
    """
    return verify_edit_invariants(before_input=before_input, after_input=after_input)


@mcp.tool()
def scifi_audit_figures(
    tex_path: str,
    base_dir: str | None = None,
    min_dpi: int = 300,
    render_previews: bool = True,
    pdf_path: str | None = None,
    render_dpi: int = 150,
    vlm_check: bool = False,
    vlm_provider: str | None = None,
    vlm_model: str | None = None,
) -> dict[str, Any]:
    """
    Audit figures in a LaTeX manuscript for print resolution (min DPI >= 300),
    vector vs raster format for charts/plots, subfigure parity ((a), (b), (c) in body text),
    colorblind accessibility, render PNG visual previews of figures & figure-bearing PDF pages,
    and optionally run a VLM visual defect check (overlapping labels, cut-off legends, margin overflow).
    """
    return audit_figure_accessibility(
        tex_path=tex_path,
        base_dir=base_dir,
        min_dpi=min_dpi,
        render_previews=render_previews,
        pdf_path=pdf_path,
        render_dpi=render_dpi,
        vlm_check=vlm_check,
        vlm_provider=vlm_provider,
        vlm_model=vlm_model,
    )


@mcp.tool()
def scifi_trim_budget(
    tex_path: str,
    bib_path: str | None = None,
    render_previews: bool = True,
    pdf_path: str | None = None,
    render_dpi: int = 150,
    pages: str | None = None,
    vlm_check: bool = False,
    vlm_provider: str | None = None,
    vlm_model: str | None = None,
) -> dict[str, Any]:
    """
    Analyze LaTeX manuscript and BibTeX bibliography for legitimate typographic line savings:
    identifies widow/orphan lines in paragraphs (1-3 trailing words), condenses BibTeX conference/journal
    titles using standard ISO-4/IEEE abbreviations, renders compiled PDF pages to PNG, and optionally
    runs a VLM visual layout check for awkward page-break whitespace, orphan headings, and margin overflow.
    """
    res = audit_trim_budget(
        tex_path=tex_path,
        bib_path=bib_path,
        render_previews=render_previews,
        pdf_path=pdf_path,
        render_dpi=render_dpi,
        pages=pages,
        vlm_check=vlm_check,
        vlm_provider=vlm_provider,
        vlm_model=vlm_model,
    )
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
    standard: str | None = None,
    check_pitfalls: bool = True,
) -> dict[str, Any]:
    """
    Audit manuscript against Core ML or ML-Systems reporting checklists
    (ml, ml-systems) and scan for statistical pitfalls (multiple testing,
    train/test data leakage, and nested seed-vs-rollout pseudoreplication).
    """
    res = audit_reproducibility(
        tex_path=tex_path,
        venue=venue,
        double_blind=double_blind,
        standard=standard,
        check_pitfalls=check_pitfalls,
    )
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
