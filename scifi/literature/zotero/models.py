"""
Data models for Zotero integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    tags: list[str] = field(default_factory=list)


@dataclass
class ZoteroAuditCard:
    item_key: str
    contribution: str
    assumptions_flagged: list[str] = field(default_factory=list)
    benchmarks_extracted: list[dict[str, Any]] = field(default_factory=list)
    math_verified: bool = False
    retraction_status: str = "OK"


@dataclass
class ZoteroConfig:
    enabled: bool = True
    data_dir: str | None = None
    collection: str | None = None
    port: int = 23119
    api_key: str | None = None
    auto_tag: bool = True
    sync_bib: str | None = "references.bib"
