"""
Zotero Subcommand Handler (`sf zotero`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_zotero(args: argparse.Namespace) -> int:
    """Manage local Zotero library, synchronization, and audit notes."""
    from scifi.env import auto_detect_zotero_dir, is_zotero_port_open
    from scifi.literature.zotero.reader import ZoteroLocalReader
    from scifi.literature.zotero.writer import ZoteroLocalWriter

    action = getattr(args, "zotero_action", None) or "status"

    if action == "status":
        z_dir = auto_detect_zotero_dir()
        port_open = is_zotero_port_open()
        print("=== SciFi Zotero Status ===")
        if not z_dir:
            print("Zotero Local Database: Not detected (checked standard paths)")
            print("Run 'sf doctor --env' for diagnostics.")
            return 0

        print(f"Zotero Data Directory: {z_dir}")
        print(f"Local Server (Port 23119): {'ONLINE' if port_open else 'OFFLINE (Desktop app closed)'}")
        try:
            reader = ZoteroLocalReader(data_dir=z_dir)
            cols = reader.get_collections()
            print(f"Collections Found: {len(cols)}")
            for c in cols[:5]:
                print(f"  - {c.name} (ID: {c.collection_id})")
            if len(cols) > 5:
                print(f"  ... and {len(cols) - 5} more")
        except Exception as e:
            print(f"Failed to read collections: {e}")
        return 0

    elif action == "sync":
        z_dir = auto_detect_zotero_dir()
        if not z_dir:
            print("[ERROR] Zotero data directory not found.", file=sys.stderr)
            return 1
        reader = ZoteroLocalReader(data_dir=z_dir)
        writer = ZoteroLocalWriter()
        col_name = getattr(args, "collection", None)
        if not col_name:
            cfg_path = Path(".scifi/config.toml")
            if cfg_path.is_file():
                for line in cfg_path.read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith("collection ="):
                        col_name = line.split("=")[1].strip().strip('"').strip("'")
                        break
        if not col_name:
            print("[ERROR] No collection specified. Pass --collection <name>.", file=sys.stderr)
            return 1

        items = reader.get_collection_items(col_name)
        print(f"[SUCCESS] Scanned collection '{col_name}': {len(items)} papers found.")

        flushed = writer.flush_staged_writes()
        if flushed:
            print(f"[SUCCESS] Flushed {len(flushed)} staged writes to Zotero.")
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
