"""
FastMCP Router: Local Zotero SQLite Integration Tools.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scifi.env import auto_detect_zotero_dir, is_zotero_port_open
from scifi.literature.zotero.models import ZoteroAuditCard
from scifi.literature.zotero.reader import ZoteroLocalReader
from scifi.literature.zotero.sync import (
    discover_zotero_projects,
    load_zotero_project_config,
    register_zotero_project,
    resolve_bib_path,
    run_auto_sync_once,
    save_zotero_collection,
    sync_zotero_project,
)
from scifi.literature.zotero.writer import ZoteroLocalWriter
from scifi.logging import get_logger
from scifi.server.app import mcp

logger = get_logger(__name__)


@mcp.tool()
def scifi_zotero_status(project_dir: str | None = None) -> dict[str, Any]:
    """
    Check the status of the local Zotero library, data directory, and port 23119 server.
    """
    proj_root = Path(project_dir).resolve() if project_dir else None
    effective_root = proj_root or Path.cwd().resolve()

    z_dir = auto_detect_zotero_dir()
    port_open = is_zotero_port_open()
    cfg = load_zotero_project_config(proj_root)
    if port_open and cfg.enabled and cfg.auto_sync:
        run_auto_sync_once(root=proj_root)

    writer = (
        ZoteroLocalWriter(stage_file=proj_root / ".scifi" / "zotero_write_queue.json")
        if proj_root
        else ZoteroLocalWriter()
    )
    collections: list[dict[str, Any]] = []
    if z_dir:
        try:
            reader = ZoteroLocalReader(data_dir=z_dir)
            cols = reader.get_collections()
            collections = [{"id": c.collection_id, "name": c.name} for c in cols]
        except Exception as e:
            logger.debug("Failed getting Zotero collections: %s", e)

    if port_open:
        live_cols = writer.list_collections_live()
        by_name = {c["name"].strip().lower(): c for c in collections}
        for lc in live_cols:
            norm = lc["name"].strip().lower()
            if norm in by_name:
                by_name[norm]["key"] = lc["key"]
            else:
                entry = {"id": None, "key": lc["key"], "name": lc["name"]}
                collections.append(entry)
                by_name[norm] = entry
        collections.sort(key=lambda c: c["name"].lower())

    return {
        "status": "RUNNING" if port_open else ("INSTALLED_OFFLINE" if z_dir else "NOT_FOUND"),
        "detected": z_dir is not None,
        "data_dir": str(z_dir) if z_dir else None,
        "port_23119_open": port_open,
        "project_root": str(effective_root),
        "bib_path": str(resolve_bib_path(effective_root, cfg.sync_bib)),
        "auto_sync": cfg.auto_sync,
        "configured_collection": cfg.collection,
        "watched_projects": [str(p) for p in discover_zotero_projects()],
        "staged_writes_pending": writer.pending_count(),
        "collections": collections,
    }


@mcp.tool()
def scifi_zotero_sync(collection: str | None = None, project_dir: str | None = None) -> dict[str, Any]:
    """
    Run bi-directional synchronization between the configured Zotero collection,
    project references.bib, and any offline staged writes.
    """
    proj_root = Path(project_dir).resolve() if project_dir else None
    res = sync_zotero_project(root=proj_root, collection=collection)
    if res.get("status") != "SKIPPED":
        if collection:
            save_zotero_collection(proj_root, collection, only_if_empty=True)
        if load_zotero_project_config(proj_root).enabled:
            try:
                register_zotero_project(proj_root)
            except Exception:
                pass
    return res


@mcp.tool()
def scifi_zotero_get_collection_papers(
    collection: str | None = None,
    project_dir: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve papers belonging to a Zotero collection with their local PDF file paths.
    """
    proj_root = Path(project_dir).resolve() if project_dir else None
    run_auto_sync_once(root=proj_root)
    reader = ZoteroLocalReader()
    col = collection or load_zotero_project_config(proj_root).collection
    if not col:
        cfg = (proj_root or Path(".")) / ".scifi" / "config.toml"
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
def scifi_zotero_search(
    query: str = "",
    collection: str | None = None,
    has_pdf: bool | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Search the local Zotero library (or a specific collection) by keyword, title, author, DOI, arXiv ID, or tag.
    Returns compact metadata with local PDF paths so large collections do not overflow context.
    """
    reader = ZoteroLocalReader()
    items = reader.search_items(query=query, collection=collection, has_pdf=has_pdf, limit=limit)
    return [
        {
            "key": it.key,
            "title": it.title,
            "authors": it.authors[:5],
            "year": it.year,
            "doi": it.doi,
            "arxiv_id": it.arxiv_id,
            "publication_title": it.publication_title,
            "has_pdf": it.pdf_path is not None,
            "pdf_path": str(it.pdf_path) if it.pdf_path else None,
            "tags": it.tags,
            "abstract_snippet": (it.abstract[:400] + "...") if it.abstract and len(it.abstract) > 400 else it.abstract,
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
def scifi_zotero_push_audit_note(
    item_key: str,
    audit_data: dict[str, Any],
    project_dir: str | None = None,
) -> dict[str, Any]:
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
    writer = (
        ZoteroLocalWriter(stage_file=Path(project_dir).resolve() / ".scifi" / "zotero_write_queue.json")
        if project_dir
        else ZoteroLocalWriter()
    )
    res = writer.push_audit_card_note(item_key, card)
    if res.get("status") in ("CREATED", "UPDATED", "SUCCESS", "STAGED"):
        tags = ["#scifi-audited"]
        if card.assumptions_flagged:
            tags.append("#unstated-assumption")
        if card.math_verified and not card.assumptions_flagged:
            tags.append("#scifi-verified")
        writer.apply_tags(item_key, tags)
    return res
