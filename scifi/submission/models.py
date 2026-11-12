"""Data models for academic paper submission suite."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AuthorInfo:
    """Author metadata for unblinded title pages and cover letters."""
    name: str
    affiliation: str
    email: str
    orcid: str | None = None
    is_corresponding: bool = False
    credit_role: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "affiliation": self.affiliation,
            "email": self.email,
            "orcid": self.orcid,
            "is_corresponding": self.is_corresponding,
            "credit_role": self.credit_role,
        }


def normalize_authors(authors: Sequence[AuthorInfo | dict[str, Any] | str] | str | None) -> list[AuthorInfo]:
    """Normalize authors from strings, dicts, or AuthorInfo objects."""
    if not authors:
        return []
    if isinstance(authors, str):
        parsed: list[AuthorInfo] = []
        for name in authors.split(","):
            n = name.strip()
            if n:
                email_handle = n.lower().replace(" ", ".")
                parsed.append(
                    AuthorInfo(
                        name=n,
                        affiliation="University/Institution",
                        email=f"{email_handle}@institution.edu",
                        is_corresponding=(len(parsed) == 0),
                    )
                )
        return parsed
    res = []
    for a in authors:
        if isinstance(a, AuthorInfo):
            res.append(a)
        elif isinstance(a, dict):
            res.append(
                AuthorInfo(
                    name=a.get("name", "Author"),
                    affiliation=a.get("affiliation", "University/Institution"),
                    email=a.get("email", "author@institution.edu"),
                    orcid=a.get("orcid"),
                    is_corresponding=a.get("is_corresponding", False),
                    credit_role=a.get("credit_role"),
                )
            )
    return res


@dataclass
class PublisherProfile:
    """Venue-specific rules and requirements."""
    venue_id: str
    name: str
    max_highlight_chars: int = 100
    min_highlights: int = 3
    max_highlights: int = 5
    require_credit_statement: bool = False
    require_conference_extension_clause: bool = False
    require_ethics_declaration: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "venue_id": self.venue_id,
            "name": self.name,
            "max_highlight_chars": self.max_highlight_chars,
            "min_highlights": self.min_highlights,
            "max_highlights": self.max_highlights,
            "require_credit_statement": self.require_credit_statement,
            "require_conference_extension_clause": self.require_conference_extension_clause,
            "require_ethics_declaration": self.require_ethics_declaration,
        }


@dataclass
class HighlightItem:
    """Single bullet point highlight evaluation."""
    text: str
    char_count: int
    max_allowed: int
    is_valid: bool
    issue: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "char_count": self.char_count,
            "max_allowed": self.max_allowed,
            "is_valid": self.is_valid,
            "issue": self.issue,
        }


@dataclass
class HighlightsResult:
    """Result of highlights generation and auditing."""
    status: str
    venue: str
    max_chars: int
    all_valid: bool
    highlights: list[HighlightItem]
    markdown_text: str
    latex_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "venue": self.venue,
            "max_chars": self.max_chars,
            "all_valid": self.all_valid,
            "highlights": [h.to_dict() for h in self.highlights],
            "markdown_text": self.markdown_text,
            "latex_text": self.latex_text,
        }


@dataclass
class TitlePageResult:
    """Result of standalone unblinded title page generation."""
    status: str
    title: str
    venue: str
    authors_count: int
    latex_text: str
    markdown_text: str
    output_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "title": self.title,
            "venue": self.venue,
            "authors_count": self.authors_count,
            "latex_text": self.latex_text,
            "markdown_text": self.markdown_text,
            "output_path": self.output_path,
        }


@dataclass
class CoverLetterResult:
    """Result of editorial cover letter generation."""
    status: str
    journal_name: str
    venue: str
    markdown_text: str
    latex_text: str
    output_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "journal_name": self.journal_name,
            "venue": self.venue,
            "markdown_text": self.markdown_text,
            "latex_text": self.latex_text,
            "output_path": self.output_path,
        }


@dataclass
class CodePackagerResult:
    """Result of anonymous code packaging."""
    status: str
    zip_path: str | None
    files_included: int
    files_excluded: int
    scrubbed_leaks: list[str] = field(default_factory=list)
    audit_passed: bool = True
    audit_report: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "zip_path": self.zip_path,
            "files_included": self.files_included,
            "files_excluded": self.files_excluded,
            "scrubbed_leaks": self.scrubbed_leaks,
            "audit_passed": self.audit_passed,
            "audit_report": self.audit_report,
        }


@dataclass
class SubmissionBundleResult:
    """Result of preparing a complete submission package."""
    status: str
    output_dir: str
    venue: str
    cover_letter_path: str | None = None
    highlights_path: str | None = None
    title_page_path: str | None = None
    code_zip_path: str | None = None
    manifest_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "output_dir": self.output_dir,
            "venue": self.venue,
            "cover_letter_path": self.cover_letter_path,
            "highlights_path": self.highlights_path,
            "title_page_path": self.title_page_path,
            "code_zip_path": self.code_zip_path,
            "manifest_path": self.manifest_path,
        }
