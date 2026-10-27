"""
Data models for citation verification and auditing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    RETRACTED = "RETRACTED"
    ERRATA_EXISTS = "ERRATA_EXISTS"
    MISMATCH = "MISMATCH"
    UNRESOLVED = "UNRESOLVED"


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class Author:
    name: str
    family: Optional[str] = None
    given: Optional[str] = None
    orcid: Optional[str] = None

    @classmethod
    def from_string(cls, name_str: str) -> Author:
        name_str = name_str.strip()
        if not name_str:
            return cls(name="Unknown")
        if "," in name_str:
            parts = [p.strip() for p in name_str.split(",", 1)]
            family = parts[0]
            given = parts[1] if len(parts) > 1 else ""
            return cls(name=f"{given} {family}".strip(), family=family, given=given)
        parts = name_str.rsplit(" ", 1)
        if len(parts) == 2:
            return cls(name=name_str, family=parts[1], given=parts[0])
        return cls(name=name_str, family=name_str, given="")


@dataclass
class Discrepancy:
    field: str
    claimed: Any
    verified: Any
    severity: Severity
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "claimed": self.claimed,
            "verified": self.verified,
            "severity": self.severity.value,
            "message": self.message,
        }


@dataclass
class ClaimedMetadata:
    title: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    doi: Optional[str] = None
    entry_key: Optional[str] = None
    raw_entry: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CitationMetadata:
    identifier_type: str
    identifier_value: str
    status: VerificationStatus = VerificationStatus.UNRESOLVED
    canonical_doi: Optional[str] = None
    canonical_url: Optional[str] = None
    title: Optional[str] = None
    authors: List[Author] = field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    publisher: Optional[str] = None
    entry_type: str = "article"
    citation_count: Optional[int] = None
    is_retracted: bool = False
    retraction_details: Optional[str] = None
    has_errata: bool = False
    errata_details: Optional[str] = None
    source_registry: str = "Unknown"
    discrepancies: List[Discrepancy] = field(default_factory=list)
    claimed_metadata: Optional[ClaimedMetadata] = None

    def generate_cite_key(self) -> str:
        """Generate a clean BibTeX citation key: [FirstAuthorSurname][Year][FirstWordOfTitle]"""
        author_part = "Anon"
        if self.authors:
            first = self.authors[0]
            family = first.family or first.name.split()[-1] if first.name else "Anon"
            # Strip non-alphanumeric
            author_part = re.sub(r"[^A-Za-z0-9]", "", family)
        year_part = str(self.year) if self.year else "nodate"
        title_part = ""
        if self.title:
            # take first significant word (> 3 chars)
            words = re.findall(r"[A-Za-z0-9]+", self.title)
            stop_words = {"the", "a", "an", "on", "in", "for", "with", "and", "to", "of"}
            for w in words:
                if w.lower() not in stop_words:
                    title_part = w.capitalize()
                    break
            if not title_part and words:
                title_part = words[0].capitalize()
        return f"{author_part}{year_part}{title_part}"

    def to_bibtex(self, key: Optional[str] = None) -> str:
        """Format metadata as a clean, standardized BibTeX entry."""
        cite_key = key or self.generate_cite_key()
        entry_type = self.entry_type or "article"

        # Format authors as: Family, Given and Family2, Given2 ...
        author_strs = []
        for a in self.authors:
            if a.family and a.given:
                author_strs.append(f"{a.family}, {a.given}")
            else:
                author_strs.append(a.name)
        authors_formatted = " and ".join(author_strs) if author_strs else "Unknown"

        lines = [f"@{entry_type}{{{cite_key},"]
        if self.title:
            # Protect capital letters in title with braces
            escaped_title = self.title.replace("{", "").replace("}", "")
            lines.append(f"  title = {{{escaped_title}}},")
        if authors_formatted:
            lines.append(f"  author = {{{authors_formatted}}},")
        if self.year:
            lines.append(f"  year = {{{self.year}}},")
        if self.venue:
            if entry_type in ("inproceedings", "conference"):
                lines.append(f"  booktitle = {{{self.venue}}},")
            else:
                lines.append(f"  journal = {{{self.venue}}},")
        if self.volume:
            lines.append(f"  volume = {{{self.volume}}},")
        if self.issue:
            lines.append(f"  number = {{{self.issue}}},")
        if self.pages:
            lines.append(f"  pages = {{{self.pages}}},")
        if self.publisher:
            lines.append(f"  publisher = {{{self.publisher}}},")
        if self.canonical_doi:
            lines.append(f"  doi = {{{self.canonical_doi}}},")
        if self.canonical_url:
            lines.append(f"  url = {{{self.canonical_url}}},")

        # Trim trailing comma on last property
        if lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]
        lines.append("}")
        return "\n".join(lines)

    def to_apa(self) -> str:
        """Format as APA 7th edition string."""
        # Authors format: Last, F. M., & Last2, F.
        author_parts = []
        for a in self.authors:
            if a.family and a.given:
                initials = " ".join([f"{n[0]}." for n in a.given.split() if n])
                author_parts.append(f"{a.family}, {initials}".strip())
            else:
                author_parts.append(a.name)

        if not author_parts:
            author_str = "Unknown"
        elif len(author_parts) == 1:
            author_str = author_parts[0]
        elif len(author_parts) == 2:
            author_str = f"{author_parts[0]} & {author_parts[1]}"
        elif len(author_parts) <= 20:
            author_str = ", ".join(author_parts[:-1]) + f", & {author_parts[-1]}"
        else:
            author_str = ", ".join(author_parts[:19]) + f", ... {author_parts[-1]}"

        year_str = f"({self.year})" if self.year else "(n.d.)"
        title_str = self.title if self.title else "Untitled"

        parts = [f"{author_str} {year_str}. {title_str}."]
        venue_parts = []
        if self.venue:
            venue_parts.append(f"*{self.venue}*")
        if self.volume:
            vol = f"*{self.volume}*"
            if self.issue:
                vol += f"({self.issue})"
            venue_parts.append(vol)
        if self.pages:
            venue_parts.append(self.pages)

        if venue_parts:
            parts.append(", ".join(venue_parts) + ".")

        if self.canonical_doi:
            parts.append(f"https://doi.org/{self.canonical_doi}")
        elif self.canonical_url:
            parts.append(self.canonical_url)

        return " ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "identifier_type": self.identifier_type,
            "identifier_value": self.identifier_value,
            "canonical_doi": self.canonical_doi,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "authors": [
                {"name": a.name, "family": a.family, "given": a.given, "orcid": a.orcid}
                for a in self.authors
            ],
            "year": self.year,
            "venue": self.venue,
            "volume": self.volume,
            "issue": self.issue,
            "pages": self.pages,
            "publisher": self.publisher,
            "entry_type": self.entry_type,
            "citation_count": self.citation_count,
            "is_retracted": self.is_retracted,
            "retraction_details": self.retraction_details,
            "has_errata": self.has_errata,
            "errata_details": self.errata_details,
            "source_registry": self.source_registry,
            "discrepancies": [d.to_dict() for d in self.discrepancies],
            "bibtex": self.to_bibtex(),
            "apa": self.to_apa(),
        }

    def summary_markdown(self) -> str:
        """Generate a concise Markdown card summarizing verification results."""
        badge = {
            VerificationStatus.VERIFIED: "🟢 **VERIFIED**",
            VerificationStatus.RETRACTED: "🚨 **RETRACTED (CRITICAL WARNING)**",
            VerificationStatus.ERRATA_EXISTS: "⚠️ **ERRATA / UPDATE PUBLISHED**",
            VerificationStatus.MISMATCH: "🟠 **METADATA MISMATCH DETECTED**",
            VerificationStatus.UNRESOLVED: "❌ **UNRESOLVED / NOT FOUND**",
        }.get(self.status, str(self.status))

        lines = [f"### Citation Verification: {badge}\n"]

        if self.is_retracted:
            lines.append(
                f"> 🚨 **RETRACTION NOTICE**: This work has been formally retracted! "
                f"{self.retraction_details or 'Check the publisher notice before citing.'}\n"
            )

        if self.has_errata:
            lines.append(
                f"> ⚠️ **ERRATA NOTICE**: Official corrections or errata exist for this publication: "
                f"{self.errata_details or 'Review updates before citing.'}\n"
            )

        lines.append(f"- **Title**: {self.title or 'Unknown'}")
        author_names = ", ".join([a.name for a in self.authors]) or "Unknown"
        lines.append(f"- **Authors**: {author_names}")
        lines.append(f"- **Year**: {self.year or 'n.d.'}")
        if self.venue:
            lines.append(f"- **Venue**: {self.venue}")
        if self.canonical_doi:
            lines.append(f"- **DOI**: [{self.canonical_doi}](https://doi.org/{self.canonical_doi})")
        if self.canonical_url and not self.canonical_doi:
            lines.append(f"- **URL**: {self.canonical_url}")
        if self.citation_count is not None:
            lines.append(f"- **Citations**: {self.citation_count:,}")
        lines.append(f"- **Source Registry**: {self.source_registry}")

        if self.discrepancies:
            lines.append("\n#### Discrepancies vs Claimed Citation:")
            for d in self.discrepancies:
                icon = "❌" if d.severity == Severity.ERROR else ("⚠️" if d.severity == Severity.WARNING else "ℹ️")
                lines.append(f"- {icon} **{d.field}**: {d.message} (Claimed: `{d.claimed}` vs Verified: `{d.verified}`)")

        lines.append("\n#### Formatted Citations:")
        lines.append("**APA (7th edition):**\n")
        lines.append(f"> {self.to_apa()}\n")
        lines.append("**Standard BibTeX:**\n")
        lines.append("```bibtex")
        lines.append(self.to_bibtex())
        lines.append("```")

        return "\n".join(lines)


@dataclass
class BibAuditReport:
    file_path: Optional[str] = None
    total_entries: int = 0
    verified_count: int = 0
    retracted_count: int = 0
    errata_count: int = 0
    mismatch_count: int = 0
    unresolved_count: int = 0
    entries: List[CitationMetadata] = field(default_factory=list)

    def summary_markdown(self) -> str:
        lines = [
            f"# BibTeX Audit Report",
            f"**File**: `{self.file_path or 'In-Memory Stream'}`",
            f"- **Total Citations**: {self.total_entries}",
            f"- 🟢 **Verified & Clean**: {self.verified_count}",
            f"- 🚨 **Retracted Papers**: {self.retracted_count}",
            f"- ⚠️ **Errata / Updates**: {self.errata_count}",
            f"- 🟠 **Metadata Mismatches**: {self.mismatch_count}",
            f"- ❌ **Unresolved Identifiers**: {self.unresolved_count}\n",
        ]

        if self.retracted_count > 0:
            lines.append("## 🚨 Critical Warnings: Retracted Citations")
            for e in self.entries:
                if e.is_retracted:
                    lines.append(
                        f"- **Key**: `{e.generate_cite_key()}` | **DOI**: {e.canonical_doi or 'N/A'}\n"
                        f"  - **Title**: {e.title}\n"
                        f"  - **Notice**: {e.retraction_details or 'Paper retracted by publisher/authors.'}"
                    )
            lines.append("")

        if self.mismatch_count > 0:
            lines.append("## 🟠 Discrepancies & Typo Alerts")
            for e in self.entries:
                if e.discrepancies:
                    lines.append(f"- **Key**: `{e.generate_cite_key()}` ({e.title})")
                    for d in e.discrepancies:
                        lines.append(f"  - [{d.severity.value}] **{d.field}**: Claimed `{d.claimed}` vs Verified `{d.verified}`")
            lines.append("")

        if self.unresolved_count > 0:
            lines.append("## ❌ Unresolved Citations")
            for e in self.entries:
                if e.status == VerificationStatus.UNRESOLVED:
                    lines.append(f"- **Identifier/Query**: `{e.identifier_value}` (Type: {e.identifier_type})")
            lines.append("")

        return "\n".join(lines)
