"""
Data models for Zotero integration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any


@dataclass
class ZoteroAnnotation:
    id: int
    parent_item_key: str
    type: int  # 1: highlight, 2: note, 3: image
    text: str | None = None
    comment: str | None = None
    color: str | None = None
    page_label: str | None = None


@dataclass
class ZoteroNote:
    note_id: int
    key: str
    parent_item_key: str | None
    title: str | None
    text: str
    raw_html: str
    tags: list[str] = field(default_factory=list)
    is_scifi_card: bool = False
    date_modified: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "note_id": self.note_id,
            "key": self.key,
            "parent_item_key": self.parent_item_key,
            "title": self.title,
            "text": self.text,
            "raw_html": self.raw_html,
            "tags": list(self.tags),
            "is_scifi_card": self.is_scifi_card,
            "date_modified": self.date_modified,
        }


@dataclass
class ZoteroCollection:
    collection_id: int
    name: str
    parent_collection_id: int | None = None


@dataclass
class ZoteroItem:
    item_id: int
    key: str
    title: str
    doi: str | None = None
    arxiv_id: str | None = None
    year: int | None = None
    abstract: str | None = None
    publication_title: str | None = None
    pdf_path: Path | None = None
    annotations: list[ZoteroAnnotation] = field(default_factory=list)
    notes: list[ZoteroNote] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    item_type: str | None = None
    url: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    date_modified: str | None = None
    attachment_hash: str | None = None


@dataclass
class ZoteroAuditCard:
    item_key: str
    contribution: str
    assumptions_flagged: list[str] = field(default_factory=list)
    benchmarks_extracted: list[dict[str, Any]] = field(default_factory=list)
    math_verified: bool = False
    retraction_status: str = "OK"
    summary: str | None = None
    pdf_source: str | None = None
    reprint_status: str | None = None
    citation_verified: bool | None = None
    claims_checked: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    relevance_notes: str | None = None
    authors_info: list[dict[str, Any]] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    claims: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    kg_digested_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any], item_key: str | None = None) -> ZoteroAuditCard:
        valid_names = {f.name for f in fields(cls)}
        filtered: dict[str, Any] = {k: v for k, v in (data or {}).items() if k in valid_names}
        if not filtered.get("item_key"):
            filtered["item_key"] = item_key or ""
        filtered.setdefault("contribution", "")
        return cls(**filtered)


@dataclass
class ZoteroConfig:
    enabled: bool = True
    data_dir: str | None = None
    collection: str | None = None
    port: int = 23119
    api_key: str | None = None
    auto_tag: bool = True
    sync_bib: str | None = "references.bib"
    auto_sync: bool = True
    sync_interval: float = 10.0
