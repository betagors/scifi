"""
Canonical data models for Phase 1 literature discovery and graph sessions.
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


__all__ = [
    "AuthorRecord",
    "PaperIdentifierRecord",
    "PaperVersionRecord",
    "PaperLocationRecord",
    "CitationRecord",
    "GraphSessionRecord",
    "PaperRecord",
]
