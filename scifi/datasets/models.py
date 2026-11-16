"""
Data models for SciFi dataset management and Kaggle integration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DatasetFile:
    """Represents a single file inside a remote or local dataset."""

    name: str
    size_bytes: int | None = None
    url: str | None = None
    checksum: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DatasetInfo:
    """Metadata for a dataset discovered on a remote provider."""

    provider: str  # "kaggle", "huggingface", "zenodo", "url"
    identifier: str  # e.g. "owner/slug", "repo_id", "1234567", or URL
    title: str
    description: str = ""
    owner: str | None = None
    url: str | None = None
    license_name: str | None = None
    downloads: int | None = None
    likes_or_votes: int | None = None
    size_bytes: int | None = None
    last_updated: str | None = None
    tags: list[str] = field(default_factory=list)
    files: list[DatasetFile] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LocalDatasetRecord:
    """Record stored in `<datasets_dir>/manifest.json` for a downloaded dataset."""

    provider: str
    identifier: str
    local_path: str
    downloaded_at: str
    title: str = ""
    files: list[str] = field(default_factory=list)
    total_bytes: int = 0
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DownloadResult:
    """Result of a dataset download operation."""

    provider: str
    identifier: str
    local_path: str
    files: list[str] = field(default_factory=list)
    total_bytes: int = 0
    extracted: bool = False
    already_existed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KaggleCompetition:
    """Metadata for a Kaggle competition."""

    ref: str
    title: str
    url: str = ""
    category: str = ""
    reward: str = ""
    deadline: str = ""
    team_count: int | None = None
    user_has_entered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KaggleKernel:
    """Metadata for a Kaggle Kernel / Notebook."""

    ref: str
    title: str
    author: str = ""
    language: str = ""
    kernel_type: str = ""
    last_run_time: str = ""
    total_votes: int | None = None
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KaggleSubmission:
    """Metadata for a Kaggle competition submission."""

    ref: str
    file_name: str
    date: str = ""
    description: str = ""
    status: str = ""
    public_score: str | None = None
    private_score: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
