"""
Data models for the Argus Attribution and Plagiarism Detection Engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from scifi.citation_verifier.models import CitationMetadata


class AttributionCategory(str, Enum):
    CANONICAL_ACADEMIC = "CANONICAL_ACADEMIC"
    COMMON_KNOWLEDGE = "COMMON_KNOWLEDGE"
    INFORMAL_WEB = "INFORMAL_WEB"
    PREPRINT_ALIGNMENT = "PREPRINT_ALIGNMENT"


class SuggestedAction(str, Enum):
    CITE = "CITE"
    REFORMULATE = "REFORMULATE"
    IGNORE = "IGNORE"


@dataclass
class AttributionFinding:
    id: str
    line_number: Optional[int]
    text_snippet: str
    matched_entity: Optional[str]
    category: AttributionCategory
    suggested_action: SuggestedAction
    confidence: float
    remediation_hint: str
    candidate_work: Optional[CitationMetadata] = None
    bibtex_entry: Optional[str] = None
    cite_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
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

    def summary_markdown(self) -> str:
        lines = [
            f"### [{self.id}] {self.category.value} (Confidence: {self.confidence:.0%})",
            f"- **Line:** {self.line_number if self.line_number is not None else 'N/A'}",
            f"- **Entity / Topic:** `{self.matched_entity or 'Uncredited text'}`",
            f"- **Action:** **{self.suggested_action.value}**",
            f"- **Snippet:** *\"{self.text_snippet[:150]}{'...' if len(self.text_snippet) > 150 else ''}\"*",
            f"- **Hint:** {self.remediation_hint}",
        ]
        if self.candidate_work and self.suggested_action == SuggestedAction.CITE:
            lines.append(f"- **Suggested Work:** *{self.candidate_work.title}* ({self.candidate_work.year})")
            if self.candidate_work.canonical_doi:
                lines.append(f"- **DOI:** [{self.candidate_work.canonical_doi}](https://doi.org/{self.candidate_work.canonical_doi})")
            if self.cite_key:
                lines.append(f"- **Cite Key:** `\\cite{{{self.cite_key}}}`")
        return "\n".join(lines)


@dataclass
class AttributionReport:
    source_file: Optional[str]
    findings: List[AttributionFinding] = field(default_factory=list)

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_file": self.source_file,
            "total_findings": self.total_findings,
            "academic_count": self.academic_count,
            "web_count": self.web_count,
            "common_knowledge_count": self.common_knowledge_count,
            "preprint_count": self.preprint_count,
            "findings": [f.to_dict() for f in self.findings],
        }

    def summary_markdown(self) -> str:
        lines = [
            f"# Argus Attribution & Integrity Audit Report",
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
