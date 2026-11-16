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

    def to_dict(self, compact_candidate: bool = True) -> dict[str, Any]:
        candidate_payload: dict[str, Any] | None = None
        if self.candidate_work:
            if compact_candidate:
                candidate_payload = {
                    "title": self.candidate_work.title,
                    "year": self.candidate_work.year,
                    "venue": self.candidate_work.venue,
                    "canonical_doi": self.candidate_work.canonical_doi,
                    "canonical_url": self.candidate_work.canonical_url,
                    "authors": [a.name for a in self.candidate_work.authors[:5]],
                    "citation_count": self.candidate_work.citation_count,
                    "is_retracted": self.candidate_work.is_retracted,
                }
            else:
                candidate_payload = self.candidate_work.to_dict()
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
            "candidate_work": candidate_payload,
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

    def to_dict(self, compact_candidate: bool = True) -> dict[str, Any]:
        res: dict[str, Any] = {
            "source_file": self.source_file,
            "total_findings": self.total_findings,
            "academic_count": self.academic_count,
            "web_count": self.web_count,
            "common_knowledge_count": self.common_knowledge_count,
            "preprint_count": self.preprint_count,
            "findings": [f.to_dict(compact_candidate=compact_candidate) for f in self.findings],
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


class EntailmentStatus(StrEnum):
    """Status enumeration classifying claim-to-citation entailment outcomes.

    Attributes:
        SUPPORTED: Cited work's abstract or full text supports the claim and any cited metrics.
        OFF_TOPIC: Cited work has negligible topical overlap with the claim sentence.
        CONTRADICTS: Cited work contains statements contradicting the claim's assertion.
        MISSING_METRIC: Claim cites a quantitative metric or value absent from the cited work.
        INSUFFICIENT_EVIDENCE: Abstract and full text could not be retrieved for the cited work.
    """

    SUPPORTED = "SUPPORTED"
    OFF_TOPIC = "OFF_TOPIC"
    CONTRADICTS = "CONTRADICTS"
    MISSING_METRIC = "MISSING_METRIC"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass
class EntailmentFinding:
    """Single claim-to-citation entailment audit finding for a cited sentence.

    Attributes:
        id: Unique finding identifier (e.g., ``ENTAIL-001``).
        line_number: 1-based line number of the claim sentence in the source file.
        cite_key: BibTeX citation key referenced in the claim sentence.
        claim_text: Cleaned claim sentence text.
        status: Entailment classification outcome.
        confidence: Confidence score in ``[0.0, 1.0]``.
        reason: Human-readable explanation of the entailment verdict.
        evidence_source: Source of the retrieved evidence (e.g., ``OpenAlex Abstract``, ``Unpaywall PDF``).
        paper_title: Resolved title of the cited paper.
        paper_doi: Resolved DOI of the cited paper.
        missing_metrics: Quantitative metrics or values cited in the claim but missing from evidence.
        contradiction_excerpt: Evidence sentence excerpt that contradicts the claim, if any.
        topical_overlap: Lexical keyword overlap ratio between claim and cited paper.
        source_file: Relative path to source file in multi-file LaTeX projects.
    """

    id: str
    line_number: int | None
    cite_key: str
    claim_text: str
    status: EntailmentStatus
    confidence: float
    reason: str
    evidence_source: str | None = None
    paper_title: str | None = None
    paper_doi: str | None = None
    missing_metrics: list[str] = field(default_factory=list)
    contradiction_excerpt: str | None = None
    topical_overlap: float = 0.0
    source_file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize finding to a JSON-compatible dictionary."""
        res: dict[str, Any] = {
            "id": self.id,
            "line_number": self.line_number,
            "cite_key": self.cite_key,
            "claim_text": self.claim_text,
            "status": self.status.value,
            "confidence": round(self.confidence, 2),
            "reason": self.reason,
            "evidence_source": self.evidence_source,
            "paper_title": self.paper_title,
            "paper_doi": self.paper_doi,
            "missing_metrics": list(self.missing_metrics),
            "contradiction_excerpt": self.contradiction_excerpt,
            "topical_overlap": round(self.topical_overlap, 3),
        }
        if self.source_file:
            res["source_file"] = self.source_file
        return res

    def summary_markdown(self) -> str:
        """Render a concise Markdown summary block for this entailment finding."""
        loc_str = (
            f"`{self.source_file}:{self.line_number}`"
            if self.source_file and self.line_number is not None
            else str(self.line_number if self.line_number is not None else "N/A")
        )
        badge = {
            EntailmentStatus.SUPPORTED: "🟢 SUPPORTED",
            EntailmentStatus.OFF_TOPIC: "🟠 OFF_TOPIC",
            EntailmentStatus.CONTRADICTS: "🚨 CONTRADICTS",
            EntailmentStatus.MISSING_METRIC: "⚠️ MISSING_METRIC",
            EntailmentStatus.INSUFFICIENT_EVIDENCE: "ℹ️ INSUFFICIENT_EVIDENCE",
        }.get(self.status, self.status.value)
        lines = [
            f"### [{self.id}] `{self.cite_key}` — {badge} ({self.confidence:.0%})",
            f"- **Line:** {loc_str}",
            f'- **Claim:** *"{self.claim_text[:180]}{"..." if len(self.claim_text) > 180 else ""}"*',
            f"- **Reason:** {self.reason}",
        ]
        if self.paper_title:
            lines.append(f"- **Cited Paper:** *{self.paper_title}*")
        if self.paper_doi:
            lines.append(f"- **DOI:** [{self.paper_doi}](https://doi.org/{self.paper_doi})")
        if self.evidence_source:
            lines.append(f"- **Evidence Source:** {self.evidence_source}")
        if self.missing_metrics:
            lines.append(f"- **Missing Metrics:** {', '.join(self.missing_metrics)}")
        if self.contradiction_excerpt:
            lines.append(f'- **Contradicting Excerpt:** *"{self.contradiction_excerpt[:200]}"*')
        return "\n".join(lines)


@dataclass
class EntailmentReport:
    """Aggregated claim-to-citation entailment audit report.

    Attributes:
        source_file: Path or label of the audited manuscript.
        bib_file: Path to the BibTeX file used to resolve citation keys.
        findings: All evaluated claim-citation pairs.
        files_scanned: List of source files scanned in multi-file LaTeX projects.
    """

    source_file: str | None
    bib_file: str | None = None
    findings: list[EntailmentFinding] = field(default_factory=list)
    files_scanned: list[str] = field(default_factory=list)

    @property
    def total_checked(self) -> int:
        return len(self.findings)

    @property
    def supported_count(self) -> int:
        return sum(1 for f in self.findings if f.status == EntailmentStatus.SUPPORTED)

    @property
    def off_topic_count(self) -> int:
        return sum(1 for f in self.findings if f.status == EntailmentStatus.OFF_TOPIC)

    @property
    def contradicts_count(self) -> int:
        return sum(1 for f in self.findings if f.status == EntailmentStatus.CONTRADICTS)

    @property
    def missing_metric_count(self) -> int:
        return sum(1 for f in self.findings if f.status == EntailmentStatus.MISSING_METRIC)

    @property
    def insufficient_evidence_count(self) -> int:
        return sum(1 for f in self.findings if f.status == EntailmentStatus.INSUFFICIENT_EVIDENCE)

    @property
    def flagged_count(self) -> int:
        return self.off_topic_count + self.contradicts_count + self.missing_metric_count

    def to_dict(self) -> dict[str, Any]:
        """Serialize report to a JSON-compatible dictionary."""
        res: dict[str, Any] = {
            "source_file": self.source_file,
            "bib_file": self.bib_file,
            "total_checked": self.total_checked,
            "flagged_count": self.flagged_count,
            "supported_count": self.supported_count,
            "off_topic_count": self.off_topic_count,
            "contradicts_count": self.contradicts_count,
            "missing_metric_count": self.missing_metric_count,
            "insufficient_evidence_count": self.insufficient_evidence_count,
            "findings": [f.to_dict() for f in self.findings],
        }
        if self.files_scanned:
            res["files_scanned"] = self.files_scanned
        return res

    def summary_markdown(self) -> str:
        """Render a Markdown summary of the claim-to-citation entailment audit."""
        lines = [
            "# Claim-to-Citation Entailment Audit Report",
            f"**File:** `{self.source_file or 'Raw Input Text'}`  ",
            f"**BibTeX:** `{self.bib_file or 'N/A'}`  ",
            f"**Checked:** {self.total_checked} | "
            f"**Supported:** {self.supported_count} | "
            f"**Off-Topic:** {self.off_topic_count} | "
            f"**Contradictions:** {self.contradicts_count} | "
            f"**Missing Metrics:** {self.missing_metric_count} | "
            f"**Insufficient Evidence:** {self.insufficient_evidence_count}",
            "",
            "---",
            "",
        ]
        flagged = [
            f
            for f in self.findings
            if f.status
            in (
                EntailmentStatus.OFF_TOPIC,
                EntailmentStatus.CONTRADICTS,
                EntailmentStatus.MISSING_METRIC,
            )
        ]
        if not flagged:
            lines.append("No off-topic, contradicting, or unsupported metric citations detected.")
            return "\n".join(lines)

        for f in flagged:
            lines.append(f.summary_markdown())
            lines.append("")

        return "\n".join(lines)
