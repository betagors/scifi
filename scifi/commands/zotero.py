"""
Zotero Subcommand Handler (`sf zotero`).
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path


def cmd_zotero(args: argparse.Namespace) -> int:
    """Manage local Zotero library, synchronization, and audit notes."""
    from scifi.env import auto_detect_zotero_dir, is_zotero_port_open
    from scifi.literature.zotero.reader import ZoteroLocalReader
    from scifi.literature.zotero.sync import (
        MultiProjectZoteroSyncer,
        ZoteroAutoSyncer,
        discover_zotero_projects,
        load_zotero_project_config,
        register_zotero_project,
        save_zotero_collection,
        sync_zotero_project,
    )
    from scifi.literature.zotero.writer import ZoteroLocalWriter

    action = getattr(args, "zotero_action", None) or "status"

    if action == "status":
        z_dir = auto_detect_zotero_dir()
        port_open = is_zotero_port_open()
        cfg = load_zotero_project_config()
        writer = ZoteroLocalWriter()
        pending = writer.pending_count()
        print("=== SciFi Zotero Status ===")
        if not z_dir:
            print("Zotero Local Database: Not detected (checked standard paths)")
            print("Run 'sf doctor --env' for diagnostics.")
            return 0

        print(f"Zotero Data Directory: {z_dir}")
        print(f"Local Server (Port 23119): {'ONLINE' if port_open else 'OFFLINE (Desktop app closed)'}")
        if cfg.collection:
            print(f"Project Collection: {cfg.collection}")
            print(f"Auto-Sync: {'ENABLED' if cfg.auto_sync else 'DISABLED'} (bib: {cfg.sync_bib or 'none'})")
        watched = discover_zotero_projects()
        print(f"Watched Projects: {len(watched)}")
        for wp in watched:
            print(f"  - {wp}")
        print(f"Pending Staged Writes: {pending}")
        try:
            reader = ZoteroLocalReader(data_dir=z_dir)
            cols = reader.get_collections()
            col_entries: list[tuple[str, str]] = [(c.name, f"ID: {c.collection_id}") for c in cols]
            if port_open:
                seen_names = {c.name.strip().lower() for c in cols}
                for lc in writer.list_collections_live():
                    if lc["name"].strip().lower() not in seen_names:
                        col_entries.append((lc["name"], f"key: {lc['key']}, live"))
                        seen_names.add(lc["name"].strip().lower())
            col_entries.sort(key=lambda x: x[0].lower())
            print(f"Collections Found: {len(col_entries)}")
            for name, meta in col_entries[:20]:
                print(f"  - {name} ({meta})")
            if len(col_entries) > 20:
                print(f"  ... and {len(col_entries) - 20} more")
        except Exception as e:
            print(f"Failed to read collections: {e}")
        return 0

    elif action == "sync":
        col_name = getattr(args, "collection", None)
        res = sync_zotero_project(collection=col_name)
        if res.get("status") == "SKIPPED":
            print(f"[ERROR] {res.get('reason', 'Sync skipped')}. Pass --collection <name>.", file=sys.stderr)
            return 1
        if col_name and save_zotero_collection(None, col_name, only_if_empty=True):
            print(f'[INFO] Saved collection = "{col_name}" to .scifi/config.toml')
        if load_zotero_project_config().enabled:
            try:
                register_zotero_project()
            except Exception:
                pass

        print(f"[SUCCESS] Synced collection '{res['collection']}' ({res['collection_count']} papers).")
        if res.get("bib_added"):
            print(f"  -> Added {res['bib_added']} entries to {res['bib_path']}")
        if res.get("zotero_linked"):
            print(f"  -> Linked {res['zotero_linked']} existing library items to collection")
        if res.get("zotero_created"):
            print(f"  -> Created {res['zotero_created']} new items in Zotero")
        if res.get("zotero_staged"):
            print(f"  -> Staged {res['zotero_staged']} Zotero updates (Zotero offline)")
        if res.get("flushed"):
            print(f"  -> Flushed {res['flushed']} staged writes to Zotero")
        if res.get("staged_remaining"):
            print(f"  -> {res['staged_remaining']} staged writes pending (start Zotero to flush)")
        return 0

    elif action == "watch":
        col_name = getattr(args, "collection", None)
        watch_all = bool(getattr(args, "all", False))
        interval = max(1.0, float(getattr(args, "interval", 5.0) or 5.0))
        cfg = load_zotero_project_config()
        target_col = col_name or cfg.collection

        if watch_all or not target_col:
            projects = discover_zotero_projects()
            if not projects and not watch_all:
                print(
                    "[ERROR] No collection configured and no Zotero-enabled projects found. "
                    "Pass --collection <name> or configure .scifi/config.toml.",
                    file=sys.stderr,
                )
                return 1
            print(
                f"Watching {len(projects)} Zotero-enabled project(s) (interval: {interval:.1f}s). Press Ctrl+C to stop."
            )
            for p in projects:
                print(f"  - {p}")
            multi_syncer = MultiProjectZoteroSyncer()
            first = True
            try:
                while True:
                    results = multi_syncer.sync_all_if_needed(force=first)
                    first = False
                    for res in results:
                        if (
                            res.get("bib_added")
                            or res.get("zotero_linked")
                            or res.get("zotero_created")
                            or res.get("flushed")
                            or res.get("zotero_staged")
                        ):
                            ts = datetime.now().strftime("%H:%M:%S")
                            proj_name = Path(res["project_root"]).name
                            print(
                                f"[{ts}] [{proj_name}] Synced '{res['collection']}': "
                                f"+{res.get('bib_added', 0)} bib, "
                                f"+{res.get('zotero_linked', 0)} linked, "
                                f"+{res.get('zotero_created', 0)} created, "
                                f"{res.get('flushed', 0)} flushed"
                            )
                    time.sleep(interval)
            except KeyboardInterrupt:
                print("\nStopped Zotero multi-project watcher.")
                return 0

        print(f"Watching Zotero collection '{target_col}' (interval: {interval:.1f}s). Press Ctrl+C to stop.")
        syncer = ZoteroAutoSyncer()
        first = True
        try:
            while True:
                res = sync_zotero_project(collection=target_col) if first else syncer.sync_if_needed(force=False)
                first = False
                if res and (
                    res.get("bib_added")
                    or res.get("zotero_linked")
                    or res.get("zotero_created")
                    or res.get("flushed")
                    or res.get("zotero_staged")
                ):
                    ts = datetime.now().strftime("%H:%M:%S")
                    print(
                        f"[{ts}] Synced '{res['collection']}': "
                        f"+{res.get('bib_added', 0)} bib, "
                        f"+{res.get('zotero_linked', 0)} linked, "
                        f"+{res.get('zotero_created', 0)} created, "
                        f"{res.get('flushed', 0)} flushed"
                    )
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nStopped Zotero watcher.")
            return 0

    elif action in ("create-collection", "create", "link"):
        col_name = getattr(args, "name", None)
        if not col_name:
            print("[ERROR] Collection name required.", file=sys.stderr)
            return 1
        writer = ZoteroLocalWriter()
        res = writer.create_collection(col_name)
        status = res.get("status")
        if status == "CREATED":
            print(f"[SUCCESS] Created Zotero collection '{col_name}'.")
        elif status == "EXISTS":
            print(f"[OK] Zotero collection '{col_name}' already exists (key: {res.get('collection_key')}).")
        else:
            print(f"[STAGED] Zotero offline; queued creation of collection '{col_name}'.")
        if not getattr(args, "no_save", False) and save_zotero_collection(None, col_name):
            print(f'  -> Linked collection = "{col_name}" in .scifi/config.toml')
            try:
                register_zotero_project()
            except Exception:
                pass
        return 0

    elif action == "flush":
        writer = ZoteroLocalWriter()
        flushed = writer.flush_staged_writes()
        print(f"Flushed {len(flushed)} staged mutations to Zotero.")
        return 0

    elif action == "annotations":
        key = getattr(args, "key", None)
        if not key:
            print("[ERROR] Item key required. Use --key <KEY>.", file=sys.stderr)
            return 1
        reader = ZoteroLocalReader()
        annos = reader.get_user_annotations(key)
        print(f"Annotations for item {key} ({len(annos)} found):")
        for a in annos:
            print(f'  - Page {a.page_label or "?"}: "{a.text or ""}" (Comment: {a.comment or "None"})')
        return 0

    return 0
