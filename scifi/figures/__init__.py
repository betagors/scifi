"""Figure and Visual Accessibility Auditor module (da-vinci)."""

from scifi.figures.auditor import (
    audit_figure_accessibility,
    audit_latex_figures,
    parse_image_dimensions_and_dpi,
)
from scifi.figures.models import (
    FigureAuditResult,
    FigureIssue,
    FigureIssueCategory,
    FigureSeverity,
    ImageFileInfo,
)
from scifi.figures.renderer import (
    detect_pdf_renderer,
    find_figure_pages_in_pdf,
    render_pdf_pages,
)
from scifi.figures.vlm import (
    inspect_images_with_vlm,
    resolve_vlm_config,
)

__all__ = [
    "audit_figure_accessibility",
    "audit_latex_figures",
    "detect_pdf_renderer",
    "find_figure_pages_in_pdf",
    "inspect_images_with_vlm",
    "parse_image_dimensions_and_dpi",
    "render_pdf_pages",
    "resolve_vlm_config",
    "FigureAuditResult",
    "FigureIssue",
    "FigureIssueCategory",
    "FigureSeverity",
    "ImageFileInfo",
]
