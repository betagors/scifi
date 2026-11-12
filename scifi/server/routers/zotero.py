"""
FastMCP Router: Local Zotero SQLite Integration Tools.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scifi.env import auto_detect_zotero_dir, is_zotero_port_open
from scifi.literature.zotero.models import ZoteroAuditCard
from scifi.literature.zotero.reader import ZoteroLocalReader
from scifi.literature.zotero.writer import ZoteroLocalWriter
from scifi.logging import get_logger
from scifi.server.app import mcp

logger = get_logger(__name__)


@mcp.tool()
def scifi_zotero_status() -> dict[str, Any]:
    """
    Check the status of the local Zotero library, data directory, and port 23119 server.
    """
    z_dir = auto_detect_zotero_dir()
    port_open = is_zotero_port_open()
    collections: list[dict[str, Any]] = []
    if z_dir:
        try:
            reader = ZoteroLocalReader(data_dir=z_dir)
            cols = reader.get_collections()
            collections = [{"id": c.collection_id, "name": c.name} for c in cols]
        except Exception as e:
            logger.debug("Failed getting Zotero collections: %s", e)

    return {
        "status": "RUNNING" if port_open else ("INSTALLED_OFFLINE" if z_dir else "NOT_FOUND"),
        "detected": z_dir is not None,
        "data_dir": str(z_dir) if z_dir else None,
        "port_23119_open": port_open,
        "collections": collections,
    }


@mcp.tool()
def scifi_zotero_get_collection_papers(collection: str | None = None) -> list[dict[str, Any]]:
    """
    Retrieve papers belonging to a Zotero collection with their local PDF file paths.
    """
    reader = ZoteroLocalReader()
    col = collection
    if not col:
        cfg = Path(".scifi/config.toml")
        if cfg.is_file():
            for line in cfg.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("collection ="):
                    col = line.split("=")[1].strip().strip('"').strip("'")
                    break

    items = reader.get_collection_items(col) if col else []
    return [
        {
            "key": it.key,
            "title": it.title,
            "doi": it.doi,
            "arxiv_id": it.arxiv_id,
            "year": it.year,
            "abstract": it.abstract,
            "pdf_path": str(it.pdf_path) if it.pdf_path else None,
            "tags": it.tags,
        }
        for it in items
    ]


@mcp.tool()
def scifi_zotero_get_annotations(item_key: str) -> list[dict[str, Any]]:
    """
    Retrieve user PDF highlights, notes, and comments for a Zotero paper.
    """
    reader = ZoteroLocalReader()
    annos = reader.get_user_annotations(item_key)
    return [
        {
            "id": a.id,
            "type": a.type,
            "text": a.text,
            "comment": a.comment,
            "color": a.color,
            "page_label": a.page_label,
        }
        for a in annos
    ]


@mcp.tool()
def scifi_zotero_push_audit_note(item_key: str, audit_data: dict[str, Any]) -> dict[str, Any]:
    """
    Push or in-place upsert a SciFi audit card child note to a paper in Zotero.
    """
    card = ZoteroAuditCard(
        item_key=item_key,
        contribution=audit_data.get("contribution", "Scientific Contribution"),
        assumptions_flagged=audit_data.get("assumptions_flagged", []),
        benchmarks_extracted=audit_data.get("benchmarks_extracted", []),
        math_verified=audit_data.get("math_verified", False),
        retraction_status=audit_data.get("retraction_status", "OK"),
    )
    writer = ZoteroLocalWriter()
    res = writer.push_audit_card_note(item_key, card)
    if res.get("status") in ("CREATED", "UPDATED", "SUCCESS", "STAGED"):
        tags = ["#scifi-audited"]
        if card.assumptions_flagged:
            tags.append("#unstated-assumption")
        if card.math_verified and not card.assumptions_flagged:
            tags.append("#scifi-verified")
        writer.apply_tags(item_key, tags)
    return res
