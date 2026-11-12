"""Data models for theorem-proof completeness sentinel."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ProofIssueCategory(StrEnum):
    """Categories classifying theorem-proof completeness deficiencies.

    Attributes:
        ORPHAN_THEOREM: Theorem, lemma, or proposition lacking an inline or appendix proof.
        UNRESOLVED_APPENDIX_PROOF: Appendix proof reference points to an undefined LaTeX label.
        EMPTY_APPENDIX_PROOF: Targeted appendix section exists but contains no substantive proof.
    """

    ORPHAN_THEOREM = "ORPHAN_THEOREM"
    UNRESOLVED_APPENDIX_PROOF = "UNRESOLVED_APPENDIX_PROOF"
    EMPTY_APPENDIX_PROOF = "EMPTY_APPENDIX_PROOF"


@dataclass
class TheoremProofRecord:
    env_type: str
    label: str
    name_or_title: str
    has_inline_proof: bool = False
    referenced_appendix_label: str | None = None
    appendix_verified: bool = False
    line_number: int | None = None
    file_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "env_type": self.env_type,
            "label": self.label,
            "name_or_title": self.name_or_title,
            "has_inline_proof": self.has_inline_proof,
            "referenced_appendix_label": self.referenced_appendix_label,
            "appendix_verified": self.appendix_verified,
            "line_number": self.line_number,
            "file_name": self.file_name,
        }


@dataclass
class ProofAuditResult:
    status: str
    total_theorems: int
    orphan_theorems: int
    theorems: list[TheoremProofRecord] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total_theorems": self.total_theorems,
            "orphan_theorems": self.orphan_theorems,
            "theorems": [t.to_dict() for t in self.theorems],
            "issues": self.issues,
        }
