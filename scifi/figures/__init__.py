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

__all__ = [
    "audit_figure_accessibility",
    "audit_latex_figures",
    "parse_image_dimensions_and_dpi",
    "FigureAuditResult",
    "FigureIssue",
    "FigureIssueCategory",
    "FigureSeverity",
    "ImageFileInfo",
]
