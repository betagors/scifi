"""
FastMCP Router: Academic Paper Submission Suite Tools.
"""

from __future__ import annotations

from typing import Any

from scifi.logging import get_logger
from scifi.server.app import mcp
from scifi.submission import (
    generate_cover_letter,
    generate_highlights,
    generate_title_page,
    package_anonymous_code,
    prepare_submission_bundle,
)

logger = get_logger(__name__)


@mcp.tool()
def scifi_generate_highlights(
    bullets: list[str] | str | None = None,
    venue: str = "general",
    manuscript_path: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    """
    Generate and validate 3-5 research highlights against venue character limits (e.g. Elsevier 85-char ceiling).
    """
    res = generate_highlights(
        bullets=bullets,
        venue=venue,
        manuscript_path=manuscript_path,
        output_path=output_path,
    )
    return res.to_dict()


@mcp.tool()
def scifi_generate_title_page(
    title: str | None = None,
    authors: list[dict[str, Any]] | list[str] | str | None = None,
    venue: str = "general",
    manuscript_path: str | None = None,
    funding: str | None = None,
    conflicts: str | None = None,
    data_availability: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    """
    Generate an unblinded standalone Title Page document (LaTeX and Markdown) for double-blind review fairness.
    """
    res = generate_title_page(
        title=title,
        authors=authors,
        venue=venue,
        manuscript_path=manuscript_path,
        funding=funding,
        conflicts=conflicts,
        data_availability=data_availability,
        output_path=output_path,
    )
    return res.to_dict()


@mcp.tool()
def scifi_generate_cover_letter(
    manuscript_title: str | None = None,
    journal_name: str = "Target Journal",
    venue: str = "general",
    issn: str | None = None,
    editor_name: str | None = None,
    authors: list[dict[str, Any]] | list[str] | str | None = None,
    figure_path: str | None = None,
    prior_doi: str | None = None,
    code_link: str | None = None,
    manuscript_path: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    """
    Generate an academic editorial cover letter in Markdown and LaTeX format tailored to publisher guidelines.
    """
    res = generate_cover_letter(
        manuscript_title=manuscript_title,
        journal_name=journal_name,
        venue=venue,
        issn=issn,
        editor_name=editor_name,
        authors=authors,
        figure_path=figure_path,
        prior_doi=prior_doi,
        code_link=code_link,
        manuscript_path=manuscript_path,
        output_path=output_path,
    )
    return res.to_dict()


@mcp.tool()
def scifi_package_anonymous_code(
    code_dir: str,
    output_zip_path: str | None = None,
    author_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Package a code directory into a reproducible anonymous ZIP archive with git history, secrets, and author paths scrubbed.
    """
    res = package_anonymous_code(
        code_dir=code_dir,
        output_zip_path=output_zip_path,
        author_names=author_names,
    )
    return res.to_dict()


@mcp.tool()
def scifi_prepare_submission_bundle(
    target_dir_or_tex: str = ".",
    journal_name: str | None = None,
    venue: str = "general",
    issn: str | None = None,
    authors: list[dict[str, Any]] | list[str] | str | None = None,
    code_dir: str | None = None,
    no_code: bool = False,
    figure_path: str | None = None,
    prior_doi: str | None = None,
    funding: str | None = None,
    conflicts: str | None = None,
    editor_name: str | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """
    Generate all four submission artifacts (cover letter, highlights, title page, anonymous code zip) and packaging manifest in one shot.
    """
    res = prepare_submission_bundle(
        target_dir_or_tex=target_dir_or_tex,
        journal_name=journal_name,
        venue=venue,
        issn=issn,
        authors=authors,
        code_dir=code_dir,
        no_code=no_code,
        figure_path=figure_path,
        prior_doi=prior_doi,
        funding=funding,
        conflicts=conflicts,
        editor_name=editor_name,
        output_dir=output_dir,
    )
    return res.to_dict()
