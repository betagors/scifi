"""
Canonical data models for Phase 1 and Phase 2 literature discovery, evidence, and research gap sessions.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AuthorRecord:
    id: str
    name: str
    orcid: Optional[str] = None
    email: Optional[str] = None
    institution: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthorRecord:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class PaperIdentifierRecord:
    paper_id: str
    provider: str
    external_id: str
    is_canonical: bool = False

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaperIdentifierRecord:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class PaperVersionRecord:
    id: str
    paper_id: str
    version_type: str
    version_label: Optional[str] = None
    doi: Optional[str] = None
    release_date: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaperVersionRecord:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class PaperLocationRecord:
    id: str
    paper_id: str
    location_type: str
    is_oa: bool = False
    oa_status: str = "closed"
    landing_page_url: Optional[str] = None
    pdf_url: Optional[str] = None
    local_pdf_path: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaperLocationRecord:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class CitationRecord:
    source_paper_id: str
    target_paper_id: str
    is_influential: bool = False
    context: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CitationRecord:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class CitationContextRecord:
    id: str
    source_paper_id: str
    target_paper_id: str
    context_text: str
    section_name: Optional[str] = None
    intent: Optional[str] = None
    is_influential: bool = False

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CitationContextRecord:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class EvidenceRecord:
    id: str
    paper_id: str
    evidence_type: str
    extracted_text: str
    extraction_method: str
    reporting_paper_id: Optional[str] = None
    source_section: Optional[str] = None
    source_location: Optional[str] = None
    confidence: Optional[float] = None
    retrieved_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceRecord:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class PaperGapRecord:
    id: str
    paper_id: str
    gap_type: str
    claim_summary: str
    primary_evidence_id: str
    verification_status: str = "candidate"
    corroborating_count: int = 0
    contradicting_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaperGapRecord:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class GraphSessionRecord:
    id: str
    title: str
    seed_paper_id: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphSessionRecord:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class PaperRecord:
    id: str
    title: str
    year: Optional[int] = None
    publication_date: Optional[str] = None
    citation_count: int = 0
    influential_citation_count: int = 0
    recent_citation_growth: float = 0.0
    is_retracted: bool = False
    authors: list[AuthorRecord] = field(default_factory=list)
    identifiers: list[PaperIdentifierRecord] = field(default_factory=list)
    versions: list[PaperVersionRecord] = field(default_factory=list)
    locations: list[PaperLocationRecord] = field(default_factory=list)
    abstract: Optional[str] = None
    venue_name: Optional[str] = None
    venue_tier: Optional[str] = None

    def generate_cite_key(self) -> str:
        """
        Generate standardized BibTeX key format: [FirstAuthorLastName][Year][FirstWordOfTitle]
        E.g., author="Ashish Vaswani", year=2017, title="Attention Is All You Need" -> "Vaswani2017Attention"
        Strips special characters and stop words, defaulting cleanly if author or year missing (e.g. "Unknown2024Title").
        """
        # 1. Author part
        author_part = "Unknown"
        if self.authors:
            first = self.authors[0]
            name = ""
            if isinstance(first, AuthorRecord):
                name = first.name
            elif isinstance(first, dict):
                name = first.get("name", "")
            elif isinstance(first, str):
                name = first
            else:
                name = getattr(first, "name", "")

            name = name.strip() if name else ""
            if name:
                if "," in name:
                    family = name.split(",")[0].strip()
                else:
                    parts = name.split()
                    family = parts[-1] if parts else ""

                clean_family = re.sub(r"[^A-Za-z0-9]", "", family)
                if clean_family:
                    if clean_family.islower():
                        author_part = clean_family.capitalize()
                    else:
                        author_part = clean_family

        # 2. Year part
        year_part = ""
        if self.year is not None:
            year_part = str(self.year)
        elif self.publication_date:
            match = re.search(r"\b(19\d\d|20\d\d)\b", str(self.publication_date))
            if match:
                year_part = match.group(1)

        if not year_part:
            year_part = "Unknown"

        # 3. Title part
        title_part = "Title"
        if self.title:
            words = re.findall(r"[A-Za-z0-9]+", self.title)
            stop_words = {
                "a", "an", "the", "and", "or", "but", "if", "then", "else", "when",
                "at", "from", "by", "on", "off", "for", "in", "out", "over", "to",
                "into", "with", "about", "against", "between", "through", "during",
                "before", "after", "above", "below", "up", "down", "is", "are", "was",
                "were", "be", "been", "being", "of", "pdf",
            }
            for w in words:
                if w.lower() not in stop_words:
                    title_part = w.capitalize()
                    break
            if title_part == "Title" and words:
                title_part = words[0].capitalize()

        return f"{author_part}{year_part}{title_part}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "year": self.year,
            "publication_date": self.publication_date,
            "citation_count": self.citation_count,
            "influential_citation_count": self.influential_citation_count,
            "recent_citation_growth": self.recent_citation_growth,
            "is_retracted": self.is_retracted,
            "authors": [a.to_dict() if hasattr(a, "to_dict") else a for a in self.authors],
            "identifiers": [i.to_dict() if hasattr(i, "to_dict") else i for i in self.identifiers],
            "versions": [v.to_dict() if hasattr(v, "to_dict") else v for v in self.versions],
            "locations": [loc.to_dict() if hasattr(loc, "to_dict") else loc for loc in self.locations],
            "abstract": self.abstract,
            "venue_name": self.venue_name,
            "venue_tier": self.venue_tier,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaperRecord:
        data = data.copy()
        if "authors" in data and isinstance(data["authors"], list):
            data["authors"] = [
                AuthorRecord.from_dict(a) if isinstance(a, dict) else a
                for a in data["authors"]
            ]
        if "identifiers" in data and isinstance(data["identifiers"], list):
            data["identifiers"] = [
                PaperIdentifierRecord.from_dict(i) if isinstance(i, dict) else i
                for i in data["identifiers"]
            ]
        if "versions" in data and isinstance(data["versions"], list):
            data["versions"] = [
                PaperVersionRecord.from_dict(v) if isinstance(v, dict) else v
                for v in data["versions"]
            ]
        if "locations" in data and isinstance(data["locations"], list):
            data["locations"] = [
                PaperLocationRecord.from_dict(loc) if isinstance(loc, dict) else loc
                for loc in data["locations"]
            ]

        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class BenchmarkRecord:
    id: str
    name: str
    domain: str = ""
    canonical_url: Optional[str] = None
    description: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BenchmarkRecord:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class EvaluationMetricRecord:
    id: str
    name: str
    goal: str = "maximize"
    unit: Optional[str] = None
    description: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.goal, str) or self.goal.lower() not in ("maximize", "minimize"):
            raise ValueError(f"Invalid evaluation metric goal '{self.goal}'. Must be 'maximize' or 'minimize'.")
        self.goal = self.goal.lower()

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationMetricRecord:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class EvaluationConditionRecord:
    id: str
    name: str
    dataset_split: Optional[str] = "test"
    hardware: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationConditionRecord:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class BenchmarkResultRecord:
    id: str
    paper_id: str
    benchmark_id: str
    metric_id: str
    condition_id: Optional[str] = None
    metric_value: float = 0.0
    is_sota: bool = False
    rank: Optional[int] = None
    evidence_id: Optional[str] = None
    table_or_figure: Optional[str] = None
    result_date: Optional[str] = None
    provenance_source: str = "author_reported"

    def __post_init__(self) -> None:
        if self.metric_value is not None:
            self.metric_value = float(self.metric_value)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BenchmarkResultRecord:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)




@dataclass
class ProjectRecord:
    id: str
    name: str
    workspace_path: str
    description: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectRecord:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_row(cls, row: Any) -> ProjectRecord:
        if hasattr(row, "keys"):
            return cls.from_dict(dict(row))
        return cls(
            id=str(row[0]),
            name=str(row[1]),
            workspace_path=str(row[2]),
            description=row[3] if len(row) > 3 and row[3] is not None else None,
            created_at=str(row[4]) if len(row) > 4 and row[4] is not None else None,
            updated_at=str(row[5]) if len(row) > 5 and row[5] is not None else None,
        )


@dataclass
class ReprintRequestRecord:
    id: str
    project_id: Optional[str]
    paper_id: str
    author_name: str
    author_email: Optional[str] = None
    author_affiliation: Optional[str] = None
    status: str = "DRAFT_READY"
    subject: str = ""
    body: str = ""
    mailto_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReprintRequestRecord:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_row(cls, row: Any) -> ReprintRequestRecord:
        if hasattr(row, "keys"):
            return cls.from_dict(dict(row))
        return cls(
            id=str(row[0]),
            project_id=str(row[1]) if row[1] is not None else None,
            paper_id=str(row[2]),
            author_name=str(row[3]),
            author_email=row[4] if row[4] is not None else None,
            author_affiliation=row[5] if row[5] is not None else None,
            status=str(row[6]) if row[6] is not None else "DRAFT_READY",
            subject=str(row[7]) if row[7] is not None else "",
            body=str(row[8]) if row[8] is not None else "",
            mailto_url=row[9] if len(row) > 9 and row[9] is not None else None,
            created_at=str(row[10]) if len(row) > 10 and row[10] is not None else None,
            updated_at=str(row[11]) if len(row) > 11 and row[11] is not None else None,
        )

__all__ = [
    "AuthorRecord",
    "BenchmarkRecord",
    "BenchmarkResultRecord",
    "CitationContextRecord",
    "CitationRecord",
    "EvaluationConditionRecord",
    "EvaluationMetricRecord",
    "EvidenceRecord",
    "GraphSessionRecord",
    "PaperGapRecord",
    "PaperIdentifierRecord",
    "PaperLocationRecord",
    "PaperRecord",
    "PaperVersionRecord",
    "ProjectRecord",
    "ReprintRequestRecord",
]
