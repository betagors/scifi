"""
Zotero Local Integration Module.
"""

from scifi.literature.zotero.models import (
    ZoteroAnnotation,
    ZoteroAuditCard,
    ZoteroCollection,
    ZoteroConfig,
    ZoteroItem,
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
    "discover_zotero_projects",
    "load_zotero_project_config",
    "register_zotero_project",
    "run_auto_sync_once",
    "start_background_sync",
    "stop_background_sync",
    "sync_zotero_project",
]
