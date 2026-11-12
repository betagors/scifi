"""Data models for reproducibility and open-science checklist auditor."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ReproducibilityCategory(StrEnum):
    RANDOM_SEEDS = "RANDOM_SEEDS"
    ERROR_BARS = "ERROR_BARS"
    COMPUTE_RESOURCES = "COMPUTE_RESOURCES"
    HYPERPARAMETERS = "HYPERPARAMETERS"
    CODE_AVAILABILITY = "CODE_AVAILABILITY"
    DOUBLE_BLIND_CODE = "DOUBLE_BLIND_CODE"


@dataclass
class ReproducibilityIssue:
    category: ReproducibilityCategory
    severity: str
    message: str
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "severity": self.severity,
            "message": self.message,
            "recommendation": self.recommendation,
        }


@dataclass
class ReproducibilityAuditResult:
    status: str
    venue: str
    score: int
    checklist_items: dict[str, bool] = field(default_factory=dict)
    issues: list[ReproducibilityIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "venue": self.venue,
            "score": self.score,
            "checklist_items": self.checklist_items,
            "total_issues": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }
