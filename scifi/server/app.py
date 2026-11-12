"""
FastMCP Server Application Core and Shared Context.
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from scifi.argus.searcher import DEFAULT_USER_AGENT
from scifi.cache import RegistryCache
from scifi.literature.models import ProjectRecord
from scifi.literature.store import DEFAULT_CENTRAL_STORE_PATH, LiteratureStore
from scifi.logging import get_logger

__all__ = [
    "mcp",
    "get_cache",
    "get_literature_store",
    "_resolve_project",
    "DEFAULT_LITERATURE_DB_PATH",
    "DEFAULT_USER_AGENT",
]

logger = get_logger(__name__)

mcp = FastMCP("scifi", instructions="Scientific Research & Academic Writing Toolkit")

_cache_instance: RegistryCache | None = None
DEFAULT_LITERATURE_DB_PATH = DEFAULT_CENTRAL_STORE_PATH


def get_cache() -> RegistryCache:
    """Return the active RegistryCache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = RegistryCache()
    return _cache_instance


def get_literature_store(db_path: Path | str | None = None) -> LiteratureStore:
    """Return a LiteratureStore instance for literature intelligence."""
    path = db_path or DEFAULT_CENTRAL_STORE_PATH
    return LiteratureStore(path)


def _resolve_project(
    store: LiteratureStore,
    project_name_or_path: str | Path | None = None,
) -> ProjectRecord | None:
    """
    Resolve a ProjectRecord from an ID, name, workspace path, or current working directory.
    If project_name_or_path is omitted, auto-discovers from Path.cwd().
    """
    if project_name_or_path:
        target_str = str(project_name_or_path).strip()
        if target_str.lower() == "all":
            return None
        # 1. Exact ID match
        proj = store.get_project(target_str)
        if proj is not None:
            return proj

        # 2. Canonical workspace path match
        target_path = Path(target_str).resolve()
        proj = store.get_project_by_workspace(target_path)
        if proj is not None:
            return proj

        # 3. Match by name or directory name
        all_projects = store.list_projects()
        for p in all_projects:
            if p.name.lower() == target_str.lower():
                return p
            if Path(p.workspace_path).name.lower() == target_str.lower():
                return p
            try:
                if Path(p.workspace_path).resolve() == target_path:
                    return p
            except Exception as e:
                logger.debug("Failed checking workspace equality for project %s: %s", p.id, e)
        return None

    # Omitted or None: auto-discover from Path.cwd()
    cwd = Path.cwd().resolve()
    proj = store.get_project_by_workspace(cwd)
    if proj is not None:
        return proj
    for p in store.list_projects():
        try:
            if Path(p.workspace_path).resolve() == cwd:
                return p
        except Exception as e:
            logger.debug("Failed matching cwd to project %s: %s", p.id, e)
    if (cwd / ".scifi").is_dir():
        manifest_file = cwd / ".scifi" / "literature_manifest.json"
        if manifest_file.exists():
            try:
                from scifi.literature.manifest import sync_workspace

                proj = sync_workspace(store, cwd)
            except Exception as e:
                logger.debug("Failed syncing workspace %s: %s", cwd, e)
                proj = store.register_project(name=cwd.name, workspace_path=cwd)
        else:
            proj = store.register_project(name=cwd.name, workspace_path=cwd)
        if proj is not None:
            return proj

    # Walk up parent directories to find containing project
    for parent in cwd.parents:
        proj = store.get_project_by_workspace(parent)
        if proj is not None:
            return proj
        for p in store.list_projects():
            try:
                if Path(p.workspace_path).resolve() == parent:
                    return p
            except Exception as e:
                logger.debug("Failed matching parent to project: %s", e)
        if (parent / ".scifi").is_dir():
            proj = store.get_project_by_workspace(parent)
            if proj is None:
                manifest_file = parent / ".scifi" / "literature_manifest.json"
                if manifest_file.exists():
                    try:
                        from scifi.literature.manifest import sync_workspace

                        proj = sync_workspace(store, parent)
                    except Exception as e:
                        logger.debug("Failed syncing parent workspace %s: %s", parent, e)
                        proj = store.register_project(name=parent.name, workspace_path=parent)
                else:
                    proj = store.register_project(name=parent.name, workspace_path=parent)
            if proj is not None:
                return proj
    return None
