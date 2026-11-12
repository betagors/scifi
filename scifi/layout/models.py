"""Data models for page budget and trimming assistant."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TrimSuggestionType(StrEnum):
    WIDOW_LINE = "WIDOW_LINE"
    BIBTEX_ABBREVIATION = "BIBTEX_ABBREVIATION"
    TABLE_PADDING = "TABLE_PADDING"
    FLOAT_REDUCTION = "FLOAT_REDUCTION"


@dataclass
class TrimSuggestion:
    suggestion_type: TrimSuggestionType
    target: str
    description: str
    potential_savings_lines: int
    proposed_text: str = ""
    line_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggestion_type": self.suggestion_type.value,
            "target": self.target,
            "description": self.description,
            "potential_savings_lines": self.potential_savings_lines,
            "proposed_text": self.proposed_text,
            "line_number": self.line_number,
        }


@dataclass
class TrimBudgetResult:
    status: str
    total_potential_lines_saved: int
    bibtex_condensed_entries: int
    suggestions: list[TrimSuggestion] = field(default_factory=list)
    abbreviated_bib: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total_potential_lines_saved": self.total_potential_lines_saved,
            "bibtex_condensed_entries": self.bibtex_condensed_entries,
            "total_suggestions": len(self.suggestions),
            "suggestions": [s.to_dict() for s in self.suggestions],
        }
