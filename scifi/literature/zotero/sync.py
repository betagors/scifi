"""
Automatic Bi-Directional Zotero Synchronization Engine.

Keeps the local Zotero collection, project `references.bib`, and staged offline
write queue (`.scifi/zotero_write_queue.json`) synchronized automatically.
"""

from __future__ import annotations

import os
import re
import threading
import tomllib
from pathlib import Path
from typing import Any

from scifi.argus.patcher import append_bibtex_entry
from scifi.env import auto_detect_zotero_dir, is_zotero_port_open
from scifi.literature.zotero.models import ZoteroConfig, ZoteroItem
from scifi.literature.zotero.reader import ZoteroLocalReader
from scifi.literature.zotero.writer import ZoteroLocalWriter
from scifi.logging import get_logger

logger = get_logger(__name__)

_BIB_TO_ZOTERO_TYPE: dict[str, tuple[str, str | None]] = {
    "article": ("journalArticle", "publicationTitle"),
    "inproceedings": ("conferencePaper", "proceedingsTitle"),
    "conference": ("conferencePaper", "proceedingsTitle"),
    "book": ("book", None),
    "incollection": ("bookSection", "bookTitle"),
    "phdthesis": ("thesis", None),
    "mastersthesis": ("thesis", None),
    "techreport": ("report", None),
    "misc": ("document", None),
}

_ZOTERO_TO_BIB_TYPE: dict[str, str] = {
    "journalArticle": "article",
    "conferencePaper": "inproceedings",
    "book": "book",
    "bookSection": "incollection",
    "thesis": "phdthesis",
    "report": "techreport",
    "preprint": "misc",
    "document": "misc",
}

_STOPWORDS = {"a", "an", "the", "of", "on", "in", "for", "to", "and", "with", "via", "by", "from", "using"}
_LOCKS_GUARD = threading.Lock()
_PROJECT_SYNC_LOCKS: dict[Path, threading.RLock] = {}


def _get_project_lock(root: Path) -> threading.RLock:
    resolved = root.resolve()
    with _LOCKS_GUARD:
        lock = _PROJECT_SYNC_LOCKS.get(resolved)
        if lock is None:
            lock = threading.RLock()
            _PROJECT_SYNC_LOCKS[resolved] = lock
        return lock


def _clean_tex(s: str) -> str:
    s = re.sub(r"\\([&%_#$])", r"\1", s)
    s = re.sub(r"\{\\['`\"^~]\{?(\w)\}?\}", r"\1", s)
    s = re.sub(r"\\['`\"^~](\w)", r"\1", s)
    return re.sub(r"[{}]", "", s).strip()


def _norm_doi(doi: str | None) -> str:
    if not doi:
        return ""
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", doi.strip(), flags=re.IGNORECASE).lower()


def _norm_arxiv(arxiv_id: str | None) -> str:
    if not arxiv_id:
        return ""
    return re.sub(r"^arxiv:", "", arxiv_id.strip(), flags=re.IGNORECASE).lower()


def _norm_title(title: str | None) -> str:
    if not title:
        return ""
    return re.sub(r"[^a-z0-9]", "", title.lower())


def bib_entries_to_zotero_items(bib_paths: list[Path], keys: set[str]) -> list[dict[str, Any]]:
    """Convert selected BibTeX entries to Zotero item JSON payloads."""
    import bibtexparser

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for p in bib_paths:
        if not p.is_file():
            continue
        lib = bibtexparser.parse_string(p.read_text(encoding="utf-8", errors="ignore"))
        for e in lib.entries:
            if e.key not in keys or e.key in seen:
                continue
            seen.add(e.key)
            f = {k.lower(): _clean_tex(v.value) for k, v in e.fields_dict.items()}
            item_type, venue_field = _BIB_TO_ZOTERO_TYPE.get(e.entry_type.lower(), ("document", None))
            item: dict[str, Any] = {"itemType": item_type, "title": f.get("title", e.key)}
            creators = []
            for a in re.split(r"\s+and\s+", f.get("author", "")):
                if "," in a:
                    last, first = [x.strip() for x in a.split(",", 1)]
                    creators.append({"creatorType": "author", "firstName": first, "lastName": last})
                elif a.strip():
                    creators.append({"creatorType": "author", "name": a.strip()})
            item["creators"] = creators
            if f.get("year"):
                item["date"] = f["year"]
            if f.get("doi"):
                item["DOI"] = f["doi"]
            if f.get("url"):
                item["url"] = f["url"]
            if f.get("volume"):
                item["volume"] = f["volume"]
            if f.get("number") and item_type == "journalArticle":
                item["issue"] = f["number"]
            if f.get("pages"):
                item["pages"] = f["pages"].replace("--", "–")
            if f.get("publisher") and item_type in ("book", "bookSection"):
                item["publisher"] = f["publisher"]
            venue = f.get("journal") or f.get("booktitle")
            if venue_field and venue:
                item[venue_field] = venue
            items.append(item)
    return items


def _generate_cite_key(item: ZoteroItem, existing_keys: set[str] | None = None) -> str:
    """Generate a deterministic [Author][Year][Word] BibTeX key."""
    author_part = "Unknown"
    if item.authors:
        first_author = item.authors[0].strip()
        if "," in first_author:
            last = first_author.split(",", 1)[0].strip()
        else:
            last = first_author.split()[-1].strip() if first_author.split() else "Unknown"
        cleaned = re.sub(r"[^a-zA-Z]", "", last)
        if cleaned:
            author_part = cleaned.capitalize()

    year_part = str(item.year) if item.year else "nd"

    title_part = ""
    words = re.findall(r"[a-zA-Z0-9]+", item.title or "")
    for w in words:
        if w.lower() not in _STOPWORDS and len(w) > 2:
            title_part = w.capitalize()
            break
    if not title_part and words:
        title_part = words[0].capitalize()
    if not title_part:
        title_part = item.key

    base = f"{author_part}{year_part}{title_part}"
    if not existing_keys or base not in existing_keys:
        return base

    for suffix_ord in range(ord("a"), ord("z") + 1):
        cand = f"{base}{chr(suffix_ord)}"
        if cand not in existing_keys:
            return cand
    return f"{base}_{item.key}"


def zotero_item_to_bibtex(item: ZoteroItem, existing_keys: set[str] | None = None) -> tuple[str, str]:
    """Format a ZoteroItem as a standardized BibTeX entry, returning (cite_key, bibtex_str)."""
    cite_key = _generate_cite_key(item, existing_keys)
    entry_type = _ZOTERO_TO_BIB_TYPE.get(item.item_type or "", "article" if item.publication_title else "misc")

    lines = [f"@{entry_type}{{{cite_key},"]
    if item.title:
        clean_title = item.title.replace("{", "").replace("}", "")
        lines.append(f"  title = {{{clean_title}}},")
    if item.authors:
        lines.append(f"  author = {{{' and '.join(item.authors)}}},")
    if item.year:
        lines.append(f"  year = {{{item.year}}},")
    if item.publication_title:
        field = "booktitle" if entry_type in ("inproceedings", "incollection") else "journal"
        lines.append(f"  {field} = {{{item.publication_title}}},")
    if item.volume:
        lines.append(f"  volume = {{{item.volume}}},")
    if item.issue:
        lines.append(f"  number = {{{item.issue}}},")
    if item.pages:
        lines.append(f"  pages = {{{item.pages}}},")
    if item.doi:
        lines.append(f"  doi = {{{item.doi}}},")
    if item.arxiv_id:
        lines.append(f"  eprint = {{{item.arxiv_id}}},")
        lines.append("  archivePrefix = {arXiv},")
    if item.url and not item.doi:
        lines.append(f"  url = {{{item.url}}},")

    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.append("}")
    return cite_key, "\n".join(lines)


def load_zotero_project_config(root: Path | None = None) -> ZoteroConfig:
    """Load [zotero] configuration from `.scifi/config.toml`."""
    base = Path(root).resolve() if root else Path.cwd().resolve()
    cfg_path = base / ".scifi" / "config.toml"
    if not cfg_path.is_file():
        return ZoteroConfig(enabled=False)

    try:
        raw = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return ZoteroConfig(enabled=False)

    z_sec = raw.get("zotero")
    if not isinstance(z_sec, dict):
        return ZoteroConfig(enabled=False)

    manuscript_sec = raw.get("manuscript", {})
    default_bib = (
        manuscript_sec.get("bib_file", "references.bib") if isinstance(manuscript_sec, dict) else "references.bib"
    )

    data_dir = z_sec.get("data_dir") or None
    if not data_dir:
        detected = auto_detect_zotero_dir()
        data_dir = str(detected) if detected else None

    return ZoteroConfig(
        enabled=bool(z_sec.get("enabled", True)),
        data_dir=data_dir,
        collection=z_sec.get("collection") or None,
        port=int(z_sec.get("port", 23119)),
        auto_tag=bool(z_sec.get("auto_tag", True)),
        sync_bib=z_sec.get("sync_bib", default_bib),
        auto_sync=bool(z_sec.get("auto_sync", True)),
        sync_interval=float(z_sec.get("sync_interval", 10.0)),
    )


def save_zotero_collection(root: Path | None, collection: str, only_if_empty: bool = False) -> bool:
    """Persist `[zotero].collection` in `.scifi/config.toml` if the config file exists."""
    clean = collection.strip()
    if not clean:
        return False
    base = Path(root).resolve() if root else Path.cwd().resolve()
    cfg_path = base / ".scifi" / "config.toml"
    if not cfg_path.is_file():
        return False
    if only_if_empty and load_zotero_project_config(base).collection:
        return False

    text = cfg_path.read_text(encoding="utf-8")
    escaped = clean.replace("\\", "\\\\").replace('"', '\\"')
    new_line = f'collection = "{escaped}"'

    lines = text.splitlines()
    in_zotero = False
    zotero_idx: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_zotero:
                # End of [zotero] without an existing collection key: insert before next section
                lines.insert(i, new_line)
                cfg_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return True
            in_zotero = stripped == "[zotero]"
            if in_zotero:
                zotero_idx = i
            continue
        if in_zotero and re.match(r"^collection\s*=", stripped):
            lines[i] = new_line
            cfg_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True

    if zotero_idx is not None:
        lines.append(new_line)
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(["[zotero]", new_line])
    cfg_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def resolve_bib_path(root: Path, sync_bib: str | None = "references.bib") -> Path:
    """Resolve the target BibTeX file path within a SciFi project."""
    bib_name = sync_bib or "references.bib"
    direct = root / bib_name
    paper_rel = root / "paper" / bib_name
    if paper_rel.is_file():
        return paper_rel
    if direct.is_file():
        return direct
    if (root / "paper").is_dir():
        return paper_rel
    return direct


def _parse_bib_entries(bib_path: Path) -> list[dict[str, str]]:
    """Parse entries from a .bib file using bibtexparser."""
    if not bib_path.is_file():
        return []
    import bibtexparser

    content = bib_path.read_text(encoding="utf-8", errors="ignore")
    if not content.strip():
        return []
    lib = bibtexparser.parse_string(content)
    parsed: list[dict[str, str]] = []
    for e in lib.entries:
        f = {k.lower(): _clean_tex(v.value) for k, v in e.fields_dict.items()}
        parsed.append(
            {
                "key": e.key,
                "title": f.get("title", ""),
                "doi": f.get("doi", ""),
                "arxiv_id": f.get("eprint", "") or f.get("arxivid", "") or f.get("arxiv", ""),
            }
        )
    return parsed


def sync_zotero_project(
    root: Path | None = None,
    collection: str | None = None,
    bib_path: Path | None = None,
    data_dir: str | Path | None = None,
    port: int | None = None,
    stage_file: Path | None = None,
    create_collection_if_missing: bool = True,
    stage_if_offline: bool = True,
) -> dict[str, Any]:
    """
    Execute a bi-directional sync between the configured Zotero collection,
    project `references.bib`, and `.scifi/zotero_write_queue.json`.
    """
    base = Path(root).resolve() if root else Path.cwd().resolve()
    with _get_project_lock(base):
        return _sync_zotero_project_unlocked(
            root=base,
            collection=collection,
            data_dir=data_dir,
            bib_path=bib_path,
            port=port,
            stage_file=stage_file,
            create_collection_if_missing=create_collection_if_missing,
            stage_if_offline=stage_if_offline,
        )


def _sync_zotero_project_unlocked(
    root: Path,
    collection: str | None = None,
    data_dir: str | Path | None = None,
    bib_path: Path | None = None,
    port: int | None = None,
    stage_file: Path | None = None,
    create_collection_if_missing: bool = True,
    stage_if_offline: bool = True,
) -> dict[str, Any]:
    base = root
    cfg = load_zotero_project_config(base)

    eff_collection = collection or cfg.collection
    eff_data_dir = Path(data_dir) if data_dir else (Path(cfg.data_dir) if cfg.data_dir else auto_detect_zotero_dir())
    eff_port = port if port is not None else cfg.port
    eff_stage = stage_file or (base / ".scifi" / "zotero_write_queue.json")
    eff_bib = bib_path or resolve_bib_path(base, cfg.sync_bib)

    writer = ZoteroLocalWriter(port=eff_port, stage_file=eff_stage)
    server_online = writer.is_server_available()

    flushed_results: list[dict[str, Any]] = []
    if server_online:
        flushed_results = writer.flush_staged_writes()

    if not eff_data_dir or not (eff_data_dir / "zotero.sqlite").is_file():
        return {
            "status": "SKIPPED",
            "reason": "Zotero database not detected",
            "collection": eff_collection,
            "server_online": server_online,
            "flushed": len(flushed_results),
            "staged_remaining": writer.pending_count(),
            "collection_count": 0,
            "bib_added": 0,
            "zotero_linked": 0,
            "zotero_created": 0,
        }

    if not eff_collection:
        return {
            "status": "SKIPPED",
            "reason": "No Zotero collection configured",
            "collection": None,
            "server_online": server_online,
            "flushed": len(flushed_results),
            "staged_remaining": writer.pending_count(),
            "collection_count": 0,
            "bib_added": 0,
            "zotero_linked": 0,
            "zotero_created": 0,
        }

    reader = ZoteroLocalReader(data_dir=eff_data_dir)
    existing_col = reader.get_collection_by_name(eff_collection)
    col_key = writer.get_collection_key(eff_collection) if server_online else None
    if not existing_col and create_collection_if_missing and not col_key:
        writer.create_collection(eff_collection)
        if server_online:
            col_key = writer.get_collection_key(eff_collection)

    z_items = reader.get_collection_items(eff_collection)
    bib_entries = _parse_bib_entries(eff_bib)

    # Build lookup sets for matching
    bib_dois = {_norm_doi(e["doi"]) for e in bib_entries if _norm_doi(e["doi"])}
    bib_arxivs = {_norm_arxiv(e["arxiv_id"]) for e in bib_entries if _norm_arxiv(e["arxiv_id"])}
    bib_titles = {_norm_title(e["title"]) for e in bib_entries if len(_norm_title(e["title"])) >= 6}
    existing_bib_keys = {e["key"] for e in bib_entries}

    z_dois = {_norm_doi(it.doi) for it in z_items if _norm_doi(it.doi)}
    z_arxivs = {_norm_arxiv(it.arxiv_id) for it in z_items if _norm_arxiv(it.arxiv_id)}
    z_titles = {_norm_title(it.title) for it in z_items if len(_norm_title(it.title)) >= 6}

    # SQLite immutable=1 ignores zotero.sqlite-wal; merge live HTTP API items so
    # uncheckpointed items in the collection are not recreated on subsequent syncs.
    if server_online and col_key:
        for live in writer.get_collection_items_live(col_key):
            d = _norm_doi(live.get("DOI", ""))
            if d:
                z_dois.add(d)
            for cand in (live.get("extra", ""), live.get("url", "")):
                a = _norm_arxiv(cand)
                if a:
                    z_arxivs.add(a)
            t = _norm_title(live.get("title", ""))
            if len(t) >= 6:
                z_titles.add(t)

    # 1. Zotero -> references.bib
    bib_added = 0
    if cfg.sync_bib is not None or bib_path is not None:
        for it in z_items:
            d = _norm_doi(it.doi)
            a = _norm_arxiv(it.arxiv_id)
            t = _norm_title(it.title)
            if (d and d in bib_dois) or (a and a in bib_arxivs) or (len(t) >= 6 and t in bib_titles):
                continue
            cite_key, bib_str = zotero_item_to_bibtex(it, existing_bib_keys)
            if append_bibtex_entry(eff_bib, bib_str, cite_key):
                bib_added += 1
                existing_bib_keys.add(cite_key)
                if d:
                    bib_dois.add(d)
                if a:
                    bib_arxivs.add(a)
                if len(t) >= 6:
                    bib_titles.add(t)

    # 2. references.bib -> Zotero collection
    missing_from_col: list[dict[str, str]] = []
    for e in bib_entries:
        d = _norm_doi(e["doi"])
        a = _norm_arxiv(e["arxiv_id"])
        t = _norm_title(e["title"])
        if (d and d in z_dois) or (a and a in z_arxivs) or (len(t) >= 6 and t in z_titles):
            continue
        missing_from_col.append(e)

    keys_to_link: list[str] = []
    keys_to_create: set[str] = set()
    for e in missing_from_col:
        found: ZoteroItem | None = None
        if e["doi"]:
            found = reader.get_item_by_doi(e["doi"])
        if not found and e["arxiv_id"]:
            found = reader.get_item_by_arxiv(e["arxiv_id"])
        if not found and e["title"]:
            found = reader.get_item_by_title(e["title"])
        if found:
            keys_to_link.append(found.key)
        else:
            keys_to_create.add(e["key"])

    zotero_linked = 0
    zotero_created = 0
    zotero_staged = 0

    if keys_to_link:
        if server_online:
            col_key = writer.get_collection_key(eff_collection)
            if col_key:
                zotero_linked = writer.add_items_to_collection(col_key, keys_to_link)
            elif stage_if_offline:
                pending_keys = {
                    k
                    for m in writer._load_staged_queue()
                    if m.get("type") == "add_to_collection"
                    and (m.get("collection_name") or "").strip().lower() == eff_collection.strip().lower()
                    for k in (m.get("item_keys") or [])
                }
                new_keys = [k for k in keys_to_link if k not in pending_keys]
                if new_keys:
                    writer._stage_write(
                        {"type": "add_to_collection", "collection_name": eff_collection, "item_keys": new_keys}
                    )
                    zotero_staged += len(new_keys)
        elif stage_if_offline:
            pending_keys = {
                k
                for m in writer._load_staged_queue()
                if m.get("type") == "add_to_collection"
                and (m.get("collection_name") or "").strip().lower() == eff_collection.strip().lower()
                for k in (m.get("item_keys") or [])
            }
            new_keys = [k for k in keys_to_link if k not in pending_keys]
            if new_keys:
                writer._stage_write(
                    {"type": "add_to_collection", "collection_name": eff_collection, "item_keys": new_keys}
                )
                zotero_staged += len(new_keys)

    if keys_to_create and eff_bib.is_file():
        payloads = bib_entries_to_zotero_items([eff_bib], keys_to_create)
        if payloads:
            if server_online:
                col_key = writer.get_collection_key(eff_collection)
                if col_key:
                    zotero_created = writer.create_items(payloads, col_key)
                elif stage_if_offline:
                    staged_dois = {
                        _norm_doi(it.get("DOI"))
                        for m in writer._load_staged_queue()
                        if m.get("type") == "create_items"
                        and (m.get("collection_name") or "").strip().lower() == eff_collection.strip().lower()
                        for it in (m.get("items") or [])
                        if _norm_doi(it.get("DOI"))
                    }
                    staged_titles = {
                        _norm_title(it.get("title"))
                        for m in writer._load_staged_queue()
                        if m.get("type") == "create_items"
                        and (m.get("collection_name") or "").strip().lower() == eff_collection.strip().lower()
                        for it in (m.get("items") or [])
                        if len(_norm_title(it.get("title"))) >= 6
                    }
                    new_payloads = [
                        p
                        for p in payloads
                        if not (
                            (_norm_doi(p.get("DOI")) and _norm_doi(p.get("DOI")) in staged_dois)
                            or (len(_norm_title(p.get("title"))) >= 6 and _norm_title(p.get("title")) in staged_titles)
                        )
                    ]
                    if new_payloads:
                        writer._stage_write(
                            {"type": "create_items", "collection_name": eff_collection, "items": new_payloads}
                        )
                        zotero_staged += len(new_payloads)
            elif stage_if_offline:
                staged_dois = {
                    _norm_doi(it.get("DOI"))
                    for m in writer._load_staged_queue()
                    if m.get("type") == "create_items"
                    and (m.get("collection_name") or "").strip().lower() == eff_collection.strip().lower()
                    for it in (m.get("items") or [])
                    if _norm_doi(it.get("DOI"))
                }
                staged_titles = {
                    _norm_title(it.get("title"))
                    for m in writer._load_staged_queue()
                    if m.get("type") == "create_items"
                    and (m.get("collection_name") or "").strip().lower() == eff_collection.strip().lower()
                    for it in (m.get("items") or [])
                    if len(_norm_title(it.get("title"))) >= 6
                }
                new_payloads = [
                    p
                    for p in payloads
                    if not (
                        (_norm_doi(p.get("DOI")) and _norm_doi(p.get("DOI")) in staged_dois)
                        or (len(_norm_title(p.get("title"))) >= 6 and _norm_title(p.get("title")) in staged_titles)
                    )
                ]
                if new_payloads:
                    writer._stage_write(
                        {"type": "create_items", "collection_name": eff_collection, "items": new_payloads}
                    )
                    zotero_staged += len(new_payloads)

    return {
        "status": "SUCCESS" if server_online else "OFFLINE",
        "collection": eff_collection,
        "bib_path": str(eff_bib),
        "server_online": server_online,
        "collection_count": len(z_items),
        "bib_added": bib_added,
        "zotero_linked": zotero_linked,
        "zotero_created": zotero_created,
        "zotero_staged": zotero_staged,
        "flushed": len(flushed_results),
        "staged_remaining": writer.pending_count(),
    }


def _stat_sig(path: Path) -> tuple[bool, int, int]:
    try:
        st = path.stat()
        return (True, st.st_mtime_ns, st.st_size)
    except OSError:
        return (False, 0, 0)


class ZoteroAutoSyncer:
    """
    Thread-safe, change-detecting Zotero auto-sync coordinator.
    Only executes sync when SQLite, `references.bib`, write queue, or Zotero port state changes.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root).resolve() if root else Path.cwd().resolve()
        self._lock = _get_project_lock(self.root)
        self._last_fingerprint: tuple[Any, ...] | None = None

    def _compute_fingerprint(self, cfg: ZoteroConfig) -> tuple[Any, ...]:
        z_dir = Path(cfg.data_dir) if cfg.data_dir else auto_detect_zotero_dir()
        sqlite_sig = _stat_sig(z_dir / "zotero.sqlite") if z_dir else (False, 0, 0)
        wal_sig = _stat_sig(z_dir / "zotero.sqlite-wal") if z_dir else (False, 0, 0)
        bib_sig = _stat_sig(resolve_bib_path(self.root, cfg.sync_bib))
        queue_sig = _stat_sig(self.root / ".scifi" / "zotero_write_queue.json")
        port_open = is_zotero_port_open(port=cfg.port, timeout=0.2)
        return (cfg.enabled, cfg.collection, sqlite_sig, wal_sig, bib_sig, queue_sig, port_open)

    def sync_if_needed(self, force: bool = False) -> dict[str, Any] | None:
        """Run sync only if underlying files or Zotero availability changed (or force=True)."""
        if not self._lock.acquire(blocking=False):
            return None
        try:
            cfg = load_zotero_project_config(self.root)
            if not cfg.enabled or (not force and not cfg.auto_sync):
                return None

            fp = self._compute_fingerprint(cfg)
            if not force and fp == self._last_fingerprint:
                return None

            res = sync_zotero_project(root=self.root)
            # Recompute fingerprint after our own edits so we don't re-trigger immediately
            self._last_fingerprint = self._compute_fingerprint(cfg)
            return res
        except Exception as e:
            logger.debug("Auto-sync skipped due to error: %s", e)
            return None
        finally:
            self._lock.release()


def register_zotero_project(root: Path | None = None) -> Path:
    """Register a Zotero-enabled project root in global config (~/.scifi/config.json) for multi-project watch."""
    from scifi.config import load_global_config, set_global_config_value

    base = (Path(root) if root else Path.cwd()).resolve()
    g_cfg = load_global_config()
    existing = g_cfg.get("zotero_projects") or []
    if not isinstance(existing, list):
        existing = []
    norm_existing = [str(Path(p).resolve()) for p in existing if isinstance(p, str) and p.strip()]
    base_str = str(base)
    if base_str not in norm_existing:
        norm_existing.append(base_str)
        set_global_config_value("zotero_projects", norm_existing)
    return base


def discover_zotero_projects(extra_roots: list[Path] | None = None) -> list[Path]:
    """
    Discover all Zotero-enabled, auto-syncable project roots across:
    1. Explicit `extra_roots` and `Path.cwd()`
    2. Global config `zotero_projects` in `~/.scifi/config.json`
    3. Registered projects in `LiteratureStore` (`~/.scifi/literature.db`)
    """
    candidates: list[Path] = []
    if extra_roots:
        candidates.extend(extra_roots)
    candidates.append(Path.cwd())

    try:
        from scifi.config import load_global_config

        g_cfg = load_global_config()
        for raw_p in g_cfg.get("zotero_projects") or []:
            if isinstance(raw_p, str) and raw_p.strip():
                candidates.append(Path(raw_p))
    except Exception as e:
        logger.debug("Failed loading zotero_projects from global config: %s", e)

    try:
        from scifi.literature.store import LiteratureStore
        from scifi.server.app import DEFAULT_CENTRAL_STORE_PATH

        if DEFAULT_CENTRAL_STORE_PATH.is_file():
            store = LiteratureStore(DEFAULT_CENTRAL_STORE_PATH)
            for proj in store.list_projects():
                if proj.workspace_path:
                    candidates.append(Path(proj.workspace_path))
    except Exception as e:
        logger.debug("Failed loading projects from LiteratureStore: %s", e)

    discovered: list[Path] = []
    seen: set[Path] = set()
    for cand in candidates:
        try:
            resolved = cand.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        cfg = load_zotero_project_config(resolved)
        if cfg.enabled and cfg.auto_sync and cfg.collection:
            discovered.append(resolved)
    return discovered


class MultiProjectZoteroSyncer:
    """
    Coordinates change-detecting Zotero auto-sync across all discovered SciFi projects.
    """

    def __init__(self, extra_roots: list[Path] | None = None) -> None:
        self.extra_roots = list(extra_roots) if extra_roots else []
        self._syncers: dict[Path, ZoteroAutoSyncer] = {}

    def refresh_projects(self) -> list[Path]:
        projects = discover_zotero_projects(self.extra_roots)
        active = set(projects)
        for stale in [p for p in self._syncers if p not in active]:
            del self._syncers[stale]
        for proj in projects:
            if proj not in self._syncers:
                self._syncers[proj] = ZoteroAutoSyncer(root=proj)
        return projects

    def sync_all_if_needed(self, force: bool = False) -> list[dict[str, Any]]:
        projects = self.refresh_projects()
        results: list[dict[str, Any]] = []
        for proj in projects:
            res = self._syncers[proj].sync_if_needed(force=force)
            if res:
                res["project_root"] = str(proj)
                results.append(res)
        return results


_bg_stop_event = threading.Event()
_bg_thread: threading.Thread | None = None
_bg_lock = threading.Lock()


def start_background_sync(
    root: Path | None = None,
    interval: float | None = None,
    all_projects: bool = True,
) -> bool:
    """
    Start an idempotent background daemon thread that keeps Zotero in sync.
    When `all_projects=True` (default), watches all discovered Zotero-enabled projects.
    Returns True if a new thread was started, False if already running or disabled.
    """
    if os.environ.get("SCIFI_ZOTERO_AUTO_SYNC", "1") == "0":
        return False

    base = Path(root).resolve() if root else Path.cwd().resolve()
    cfg = load_zotero_project_config(base)
    if not all_projects and (not cfg.enabled or not cfg.auto_sync):
        return False

    poll_interval = max(1.0, interval if interval is not None else cfg.sync_interval)

    with _bg_lock:
        global _bg_thread
        if _bg_thread is not None and _bg_thread.is_alive():
            return False

        _bg_stop_event.clear()
        if all_projects:
            multi_syncer = MultiProjectZoteroSyncer(extra_roots=[base] if root else None)

            def _loop() -> None:
                while not _bg_stop_event.is_set():
                    multi_syncer.sync_all_if_needed(force=False)
                    _bg_stop_event.wait(poll_interval)
        else:
            syncer = ZoteroAutoSyncer(root=base)

            def _loop() -> None:
                while not _bg_stop_event.is_set():
                    syncer.sync_if_needed(force=False)
                    _bg_stop_event.wait(poll_interval)

        _bg_thread = threading.Thread(target=_loop, name="scifi-zotero-autosync", daemon=True)
        _bg_thread.start()
        return True


def stop_background_sync() -> None:
    """Stop the background Zotero auto-sync daemon thread if running."""
    with _bg_lock:
        global _bg_thread
        _bg_stop_event.set()
        if _bg_thread is not None and _bg_thread.is_alive():
            _bg_thread.join(timeout=2.0)
        _bg_thread = None


def run_auto_sync_once(root: Path | None = None) -> dict[str, Any] | None:
    """
    Lightweight one-shot auto-sync hook for CLI commands and MCP tool invocations.
    Safe to call anywhere; never raises.
    """
    if os.environ.get("SCIFI_ZOTERO_AUTO_SYNC", "1") == "0":
        return None
    try:
        syncer = ZoteroAutoSyncer(root=root)
        return syncer.sync_if_needed(force=False)
    except Exception:
        return None
