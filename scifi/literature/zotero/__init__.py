"""
Zotero Local Integration Module.
"""

from scifi.literature.zotero.models import (
    ZoteroAnnotation,
    ZoteroAuditCard,
    ZoteroCollection,
    ZoteroConfig,
    ZoteroItem,
    ZoteroNote,
)
from scifi.literature.zotero.notes import (
    filter_items_by_tags,
    get_collection_notes,
    get_item_notes,
    strip_zotero_note_html,
)
from scifi.literature.zotero.reader import ZoteroLocalReader
from scifi.literature.zotero.sync import (
    MultiProjectZoteroSyncer,
    ZoteroAutoSyncer,
    discover_zotero_projects,
    load_zotero_project_config,
    register_zotero_project,
    run_auto_sync_once,
    start_background_sync,
    stop_background_sync,
    sync_zotero_project,
)
from scifi.literature.zotero.writer import ZoteroLocalWriter

__all__ = [
    "MultiProjectZoteroSyncer",
    "ZoteroAnnotation",
    "ZoteroAuditCard",
    "ZoteroAutoSyncer",
    "ZoteroCollection",
    "ZoteroConfig",
    "ZoteroItem",
    "ZoteroLocalReader",
    "ZoteroLocalWriter",
    "ZoteroNote",
    "discover_zotero_projects",
    "filter_items_by_tags",
    "get_collection_notes",
    "get_item_notes",
    "load_zotero_project_config",
    "register_zotero_project",
    "run_auto_sync_once",
    "start_background_sync",
    "stop_background_sync",
    "strip_zotero_note_html",
    "sync_zotero_project",
]
