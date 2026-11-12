"""Data models for figure and visual accessibility auditor (da-vinci)."""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class FigureSeverity(StrEnum):
    """Severity ratings for scientific figure and visualization audit findings.

    Attributes:
        INFO: Informational observation or optional visual polish hint.
        WARNING: Quality concern (e.g. raster chart or borderline print DPI).
        CRITICAL: Venue rejection risk (e.g. missing figure file, inaccessible palette).
    """

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class FigureIssueCategory(StrEnum):
    r"""Categories classifying scientific figure defects and accessibility issues.

    Attributes:
        LOW_DPI: Raster figure below the standard print resolution ceiling (<300 DPI).
        RASTER_CHART: Plots or curves rendered as bitmap instead of scalable vector format.
        UNREFERENCED_SUBFIGURE: Subfigure defined in LaTeX but never discussed in body text.
        COLORBLIND_RISK: Confusable red-green palettes without secondary visual distinctions.
        MISSING_FIGURE_FILE: Graphic file path referenced in `\includegraphics` not found.
        LABEL_READABILITY: Inconsistent, unreadable, or missing figure axis labels.
    """

    LOW_DPI = "LOW_DPI"
    RASTER_CHART = "RASTER_CHART"
    UNREFERENCED_SUBFIGURE = "UNREFERENCED_SUBFIGURE"
    COLORBLIND_RISK = "COLORBLIND_RISK"
    MISSING_FIGURE_FILE = "MISSING_FIGURE_FILE"
    LABEL_READABILITY = "LABEL_READABILITY"


@dataclass
class ImageFileInfo:
    path: Path
    width: int = 0
    height: int = 0
    dpi: int | None = None
    is_vector: bool = False
    format_name: str = ""


@dataclass
class FigureIssue:
    category: FigureIssueCategory
    severity: FigureSeverity
    figure_ref: str
    message: str
    line_number: int | None = None
    file_path: str | None = None
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "figure_ref": self.figure_ref,
            "message": self.message,
            "line_number": self.line_number,
            "file_path": self.file_path,
            "recommendation": self.recommendation,
        }


@dataclass
class FigureAuditResult:
    status: str
    total_figures_inspected: int
    issues: list[FigureIssue] = field(default_factory=list)
    clean_score: int = 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total_figures_inspected": self.total_figures_inspected,
            "total_issues": len(self.issues),
            "clean_score": self.clean_score,
            "issues": [i.to_dict() for i in self.issues],
        }
