"""
Data models for Zotero integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ZoteroAnnotation:
    id: int
    parent_item_key: str
    type: int  # 1: highlight, 2: note, 3: image
    text: Optional[str] = None
    comment: Optional[str] = None
    color: Optional[str] = None
    page_label: Optional[str] = None


@dataclass
class ZoteroCollection:
    collection_id: int
    name: str
    parent_collection_id: Optional[int] = None


@dataclass
class ZoteroItem:
    item_id: int
    key: str
    title: str
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    year: Optional[int] = None
    abstract: Optional[str] = None
    publication_title: Optional[str] = None
    pdf_path: Optional[Path] = None
    annotations: List[ZoteroAnnotation] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


@dataclass
class ZoteroAuditCard:
    item_key: str
    contribution: str
    assumptions_flagged: List[str] = field(default_factory=list)
    benchmarks_extracted: List[Dict[str, Any]] = field(default_factory=list)
    math_verified: bool = False
    retraction_status: str = "OK"


@dataclass
class ZoteroConfig:
    enabled: bool = True
    data_dir: Optional[str] = None
    collection: Optional[str] = None
    port: int = 23119
    api_key: Optional[str] = None
    auto_tag: bool = True
    sync_bib: Optional[str] = "references.bib"
