"""
Data models for the Argus Attribution and Plagiarism Detection Engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from scifi.citation_verifier.models import CitationMetadata


class AttributionCategory(StrEnum):
    """Categories classifying intellectual attribution sources and gaps.

    Attributes:
        CANONICAL_ACADEMIC: Formal peer-reviewed or authoritative academic literature.
        COMMON_KNOWLEDGE: Widely accepted domain facts that do not strictly require citation.
        INFORMAL_WEB: Non-peer-reviewed online resources (blog posts, forum discussions).
        PREPRINT_ALIGNMENT: High-overlap frontier preprint or unpublished arXiv manuscript.
    """

    CANONICAL_ACADEMIC = "CANONICAL_ACADEMIC"
    COMMON_KNOWLEDGE = "COMMON_KNOWLEDGE"
    INFORMAL_WEB = "INFORMAL_WEB"
    PREPRINT_ALIGNMENT = "PREPRINT_ALIGNMENT"


class SuggestedAction(StrEnum):
    """Recommended remediation actions for flagged attribution gaps.

    Attributes:
        CITE: Insert a formal BibTeX citation and bibliography reference.
        REFORMULATE: Rewrite or rephrase informal phrasing into rigorous academic prose.
        IGNORE: Benign common knowledge or standard notation requiring no modification.
    """

    CITE = "CITE"
    REFORMULATE = "REFORMULATE"
    IGNORE = "IGNORE"


@dataclass
class AttributionFinding:
    id: str
    line_number: int | None
    text_snippet: str
    matched_entity: str | None
    category: AttributionCategory
    suggested_action: SuggestedAction
    confidence: float
    remediation_hint: str
    candidate_work: CitationMetadata | None = None
    bibtex_entry: str | None = None
    cite_key: str | None = None
    source_file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "id": self.id,
            "line_number": self.line_number,
            "text_snippet": self.text_snippet,
            "matched_entity": self.matched_entity,
            "category": self.category.value,
            "suggested_action": self.suggested_action.value,
            "confidence": round(self.confidence, 2),
            "remediation_hint": self.remediation_hint,
            "cite_key": self.cite_key,
            "bibtex_entry": self.bibtex_entry,
            "candidate_work": self.candidate_work.to_dict() if self.candidate_work else None,
        }
        if self.source_file:
            res["source_file"] = self.source_file
        return res

    def summary_markdown(self) -> str:
        loc_str = (
            f"`{self.source_file}:{self.line_number}`"
            if self.source_file and self.line_number is not None
            else str(self.line_number if self.line_number is not None else "N/A")
        )
        lines = [
            f"### [{self.id}] {self.category.value} (Confidence: {self.confidence:.0%})",
            f"- **Line:** {loc_str}",
            f"- **Entity / Topic:** `{self.matched_entity or 'Uncredited text'}`",
            f"- **Action:** **{self.suggested_action.value}**",
            f'- **Snippet:** *"{self.text_snippet[:150]}{"..." if len(self.text_snippet) > 150 else ""}"*',
            f"- **Hint:** {self.remediation_hint}",
        ]
        if self.candidate_work and self.suggested_action == SuggestedAction.CITE:
            lines.append(f"- **Suggested Work:** *{self.candidate_work.title}* ({self.candidate_work.year})")
            if self.candidate_work.canonical_doi:
                lines.append(
                    f"- **DOI:** [{self.candidate_work.canonical_doi}](https://doi.org/{self.candidate_work.canonical_doi})"
                )
            if self.cite_key:
                lines.append(f"- **Cite Key:** `\\cite{{{self.cite_key}}}`")
        return "\n".join(lines)


@dataclass
class AttributionReport:
    source_file: str | None
    findings: list[AttributionFinding] = field(default_factory=list)
    files_scanned: list[str] = field(default_factory=list)

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @property
    def academic_count(self) -> int:
        return sum(1 for f in self.findings if f.category == AttributionCategory.CANONICAL_ACADEMIC)

    @property
    def web_count(self) -> int:
        return sum(1 for f in self.findings if f.category == AttributionCategory.INFORMAL_WEB)

    @property
    def common_knowledge_count(self) -> int:
        return sum(1 for f in self.findings if f.category == AttributionCategory.COMMON_KNOWLEDGE)

    @property
    def preprint_count(self) -> int:
        return sum(1 for f in self.findings if f.category == AttributionCategory.PREPRINT_ALIGNMENT)

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "source_file": self.source_file,
            "total_findings": self.total_findings,
            "academic_count": self.academic_count,
            "web_count": self.web_count,
            "common_knowledge_count": self.common_knowledge_count,
            "preprint_count": self.preprint_count,
            "findings": [f.to_dict() for f in self.findings],
        }
        if self.files_scanned:
            res["files_scanned"] = self.files_scanned
        return res

    def summary_markdown(self) -> str:
        lines = [
            "# Argus Attribution & Integrity Audit Report",
            f"**File:** `{self.source_file or 'Raw Input Text'}`  ",
            f"**Total Flags:** {self.total_findings} | "
            f"**Academic Gaps:** {self.academic_count} | "
            f"**Web / Informal:** {self.web_count} | "
            f"**Preprint Alignments:** {self.preprint_count}",
            "",
            "---",
            "",
        ]
        if not self.findings:
            lines.append("No attribution deficiencies or plagiarism indicators detected. Clean manuscript.")
            return "\n".join(lines)

        for f in self.findings:
            lines.append(f.summary_markdown())
            lines.append("")

        return "\n".join(lines)
