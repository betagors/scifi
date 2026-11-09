"""Data models for figure and visual accessibility auditor (da-vinci)."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class FigureSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class FigureIssueCategory(str, Enum):
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
