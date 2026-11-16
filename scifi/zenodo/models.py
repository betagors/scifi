"""
Data models for SciFi Zenodo deposit integration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ZenodoFile:
    """Represents a file attached to a Zenodo deposition."""

    filename: str
    filesize: int | None = None
    id: str | None = None
    checksum: str | None = None
    download_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ZenodoDeposition:
    """Represents a Zenodo deposition (draft or published record)."""

    id: int
    title: str
    state: str = "unsubmitted"
    submitted: bool = False
    doi: str | None = None
    prereserved_doi: str | None = None
    conceptrecid: str | None = None
    created: str | None = None
    modified: str | None = None
    html_url: str | None = None
    bucket_url: str | None = None
    upload_type: str | None = None
    description: str | None = None
    creators: list[dict[str, Any]] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    license: str | None = None
    files: list[ZenodoFile] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "state": self.state,
            "submitted": self.submitted,
            "doi": self.doi,
            "prereserved_doi": self.prereserved_doi,
            "conceptrecid": self.conceptrecid,
            "created": self.created,
            "modified": self.modified,
            "html_url": self.html_url,
            "bucket_url": self.bucket_url,
            "upload_type": self.upload_type,
            "description": self.description,
            "creators": self.creators,
            "keywords": self.keywords,
            "license": self.license,
            "files": [f.to_dict() for f in self.files],
        }


@dataclass
class ZenodoPushResult:
    """Result of pushing submission artifacts to a Zenodo deposition."""

    deposition_id: int
    title: str
    html_url: str | None = None
    prereserved_doi: str | None = None
    doi: str | None = None
    published: bool = False
    uploaded_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
