"""Data models for author rebuttal and manuscript diff suite."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReviewItem:
    reviewer_id: str
    item_index: int
    critique_text: str
    category: str = "CLARIFICATION"

    def to_dict(self) -> dict[str, Any]:
        return {
            "reviewer_id": self.reviewer_id,
            "item_index": self.item_index,
            "critique_text": self.critique_text,
            "category": self.category,
        }


@dataclass
class RebuttalScaffold:
    status: str
    venue: str
    total_critiques_parsed: int
    reviewers: list[str] = field(default_factory=list)
    items: list[ReviewItem] = field(default_factory=list)
    markdown_template: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "venue": self.venue,
            "total_critiques_parsed": self.total_critiques_parsed,
            "reviewers": self.reviewers,
            "items": [i.to_dict() for i in self.items],
            "markdown_template": self.markdown_template,
        }


@dataclass
class ManuscriptDiffSummary:
    status: str
    old_tex: str
    new_tex: str
    added_lines: int
    deleted_lines: int
    modified_sections: list[dict[str, Any]] = field(default_factory=list)
    diff_ledger_markdown: str = ""
    diff_tex_path: str | None = None
    diff_pdf_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "old_tex": self.old_tex,
            "new_tex": self.new_tex,
            "added_lines": self.added_lines,
            "deleted_lines": self.deleted_lines,
            "modified_sections": self.modified_sections,
            "diff_ledger_markdown": self.diff_ledger_markdown,
            "diff_tex_path": self.diff_tex_path,
            "diff_pdf_path": self.diff_pdf_path,
        }
