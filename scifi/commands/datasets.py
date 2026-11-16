"""
Dataset & Kaggle Subcommand Handlers (`sf datasets`, `sf kaggle`).
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from scifi.config import get_datasets_dir
from scifi.datasets import DatasetManager, KaggleAPIError, KaggleAuthError, KaggleClient


def _format_bytes(num_bytes: int | None) -> str:
    if num_bytes is None:
        return "?"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{num_bytes} B"


def cmd_datasets(args: argparse.Namespace) -> int:
    """Manage default datasets folder, search, download, and list local datasets."""
    action = getattr(args, "datasets_action", None) or "list"
    custom_dir = getattr(args, "dir", None)
    mgr = DatasetManager(datasets_dir=custom_dir)

    if action == "dir":
        set_path = getattr(args, "set_path", None)
        if set_path:
            resolved = mgr.set_default_dir(set_path)
            print(f"[SUCCESS] Default datasets directory set to: {resolved}")
            return 0
        print(f"Default datasets directory: {get_datasets_dir()}")
        return 0

    if action == "list":
        records = mgr.list_local()
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {"datasets_dir": str(mgr.datasets_dir), "datasets": [r.to_dict() for r in records]}, indent=2
                )
            )
            return 0
        print(f"Datasets folder: {mgr.datasets_dir}")
        if not records:
            print(
                "No datasets downloaded yet. Use `sf datasets search <query>` or `sf datasets download <provider> <id>`."
            )
            return 0
        for rec in records:
            print(f"  - [{rec.provider}] {rec.identifier} ({len(rec.files)} files, {_format_bytes(rec.total_bytes)})")
            print(f"    Path: {rec.local_path}")
        return 0

    if action == "search":
        res = mgr.search(
            query=args.query,
            provider=getattr(args, "provider", "all"),
            limit=getattr(args, "limit", 15),
        )
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
            return 0
        print(f"Search results for {args.query!r} ({res['count']} found):")
        for item in res["results"]:
            size_str = _format_bytes(item.get("size_bytes"))
            print(f"  - [{item['provider']}] {item['identifier']} | {item['title']} ({size_str})")
            if item.get("url"):
                print(f"    URL: {item['url']}")
        for prov, err in res.get("errors", {}).items():
            print(f"  [WARN] {prov}: {err}", file=sys.stderr)
        return 0

    if action == "download":
        source = getattr(args, "source", "auto")
        identifier = args.identifier
        unzip = not getattr(args, "no_unzip", False)
        file_name = getattr(args, "file", None)
        try:
            res = mgr.download(
                source=source,
                identifier=identifier,
                dest_dir=custom_dir,
                unzip=unzip,
                file_name=file_name,
            )
        except (KaggleAuthError, KaggleAPIError, ValueError, FileNotFoundError) as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"[ERROR] Download failed: {exc}", file=sys.stderr)
            return 1

        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
            return 0
        print(f"[SUCCESS] Downloaded [{res.provider}] {res.identifier}")
        print(f"  Path: {res.local_path}")
        print(f"  Files: {len(res.files)} ({_format_bytes(res.total_bytes)})")
        return 0

    if action == "remove":
        deleted = mgr.remove_local(args.identifier, delete_files=getattr(args, "delete", False))
        if not deleted:
            print(f"[ERROR] Dataset {args.identifier!r} not found in manifest.", file=sys.stderr)
            return 1
        print(f"[SUCCESS] Removed {args.identifier!r} from local dataset manifest.")
        return 0

    if action == "inspect":
        try:
            info = mgr.inspect(
                args.target,
                max_rows=getattr(args, "rows", 5),
                max_chars=getattr(args, "max_chars", 80),
                max_columns=getattr(args, "max_columns", 30),
                max_files=getattr(args, "max_files", 20),
            )
        except FileNotFoundError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 1
        if getattr(args, "json", False):
            print(json.dumps(info, indent=2))
            return 0
        print(f"Dataset Inspection: {info['path']} ({info.get('kind', 'file')})")
        if info.get("kind") == "directory":
            print(f"  Files: {info['total_files']} ({info['total_human']})")
            for ext_entry in info.get("by_extension", []):
                print(f"    {ext_entry['extension']}: {ext_entry['count']} files ({ext_entry['total_human']})")
            if info.get("primary_file"):
                print(f"  Primary file: {info['primary_file']}")
                prim = info.get("primary_file_inspection", {})
                if "row_count" in prim:
                    est = "~" if prim.get("row_count_estimated") else ""
                    print(f"    Rows: {est}{prim['row_count']} | Columns: {prim.get('column_count', '?')}")
        else:
            print(f"  Format: {info.get('format')} | Size: {info.get('size_human')}")
            if "row_count" in info:
                est = "~" if info.get("row_count_estimated") else ""
                print(f"  Rows: {est}{info['row_count']} | Columns: {info.get('column_count', '?')}")
            for col in info.get("columns", []):
                print(f"    - {col['name']} ({col['type']})")
            if info.get("sample_rows"):
                print("  Sample rows:")
                for row in info["sample_rows"]:
                    print(f"    {json.dumps(row, ensure_ascii=False)}")
        return 0

    return 0


def cmd_kaggle(args: argparse.Namespace) -> int:
    """Control Kaggle datasets, competitions, and kernels/notebooks."""
    client = KaggleClient()
    section = getattr(args, "kaggle_section", None) or "status"

    try:
        if section == "status":
            st = client.status()
            if getattr(args, "json", False):
                print(json.dumps(st, indent=2))
                return 0
            print("=== SciFi Kaggle Status ===")
            print(f"Authenticated: {'YES' if st['authenticated'] else 'NO'}")
            print(f"Auth Mode: {st['auth_mode']}")
            print(f"Username: {st['username'] or 'N/A'}")
            print(f"Credential Source: {st['credential_source'] or 'None'}")
            print(f"Default Datasets Folder: {st['default_datasets_dir']}")
            if not st["authenticated"]:
                print("Hint: Run `sf kaggle login` or place kaggle.json in ~/.kaggle/kaggle.json.")
            return 0

        if section == "login":
            from_file = getattr(args, "from_file", None)
            uname = getattr(args, "username", None)
            ukey = getattr(args, "key", None)
            verify = not getattr(args, "no_verify", False)
            target = "scifi_config" if getattr(args, "scifi_config", False) else "kaggle_json"

            if from_file:
                fpath = Path(from_file).expanduser().resolve()
                if not fpath.is_file():
                    print(f"[ERROR] File not found: {fpath}", file=sys.stderr)
                    return 1
                data = json.loads(fpath.read_text(encoding="utf-8"))
                uname = str(data.get("username", "")).strip()
                ukey = str(data.get("key", "")).strip()
            else:
                if not uname:
                    uname = input("Kaggle username: ").strip()
                if not ukey:
                    ukey = getpass.getpass("Kaggle API key: ").strip()

            res = client.login(uname, ukey, verify=verify, target=target)
            if getattr(args, "json", False):
                print(json.dumps(res, indent=2))
                return 0
            print(f"[SUCCESS] Kaggle authenticated as {res['username']}.")
            print(f"  Saved credentials to: {res['saved_to']}")
            return 0

        if section == "datasets":
            sub = getattr(args, "kaggle_ds_action", None) or "search"
            if sub == "search":
                items = client.search_datasets(
                    query=getattr(args, "query", "") or "",
                    sort_by=getattr(args, "sort_by", "hottest"),
                    page=getattr(args, "page", 1),
                    max_results=getattr(args, "limit", 20),
                )
                if getattr(args, "json", False):
                    print(json.dumps([i.to_dict() for i in items], indent=2))
                    return 0
                for i in items:
                    print(f"  - {i.identifier} | {i.title} ({_format_bytes(i.size_bytes)})")
                return 0
            if sub == "files":
                files = client.list_dataset_files(args.dataset)
                if getattr(args, "json", False):
                    print(json.dumps([f.to_dict() for f in files], indent=2))
                    return 0
                for f in files:
                    print(f"  - {f.name} ({_format_bytes(f.size_bytes)})")
                return 0
            if sub == "download":
                mgr = DatasetManager(datasets_dir=getattr(args, "dir", None))
                res = mgr.download(
                    source="kaggle",
                    identifier=args.dataset,
                    dest_dir=getattr(args, "dir", None),
                    unzip=not getattr(args, "no_unzip", False),
                    file_name=getattr(args, "file", None),
                )
                print(f"[SUCCESS] Downloaded {res.identifier} -> {res.local_path} ({len(res.files)} files)")
                return 0
            if sub == "push":
                res = client.push_dataset(
                    folder=args.folder,
                    title=getattr(args, "title", None),
                    slug=getattr(args, "slug", None),
                    is_private=not getattr(args, "public", False),
                    version_notes=getattr(args, "notes", "Uploaded via SciFi"),
                    create_new=getattr(args, "create", False),
                )
                print(json.dumps(res, indent=2))
                return 0

        if section == "competitions":
            sub = getattr(args, "kaggle_comp_action", None) or "list"
            if sub == "list":
                comps = client.list_competitions(
                    search=getattr(args, "search", None),
                    category=getattr(args, "category", None),
                    page=getattr(args, "page", 1),
                )
                if getattr(args, "json", False):
                    print(json.dumps([c.to_dict() for c in comps], indent=2))
                    return 0
                for c in comps:
                    print(f"  - {c.ref} | {c.title} | Reward: {c.reward} | Deadline: {c.deadline}")
                return 0
            if sub == "files":
                files = client.list_competition_files(args.competition)
                for f in files:
                    print(f"  - {f.name} ({_format_bytes(f.size_bytes)})")
                return 0
            if sub == "download":
                res = client.download_competition(
                    competition=args.competition,
                    dest_dir=getattr(args, "dir", None),
                    file_name=getattr(args, "file", None),
                    unzip=not getattr(args, "no_unzip", False),
                )
                print(f"[SUCCESS] Downloaded competition data -> {res.local_path} ({len(res.files)} files)")
                return 0
            if sub == "submissions":
                subs = client.list_submissions(args.competition)
                if getattr(args, "json", False):
                    print(json.dumps([s.to_dict() for s in subs], indent=2))
                    return 0
                for s in subs:
                    print(f"  - {s.date} | {s.file_name} | Status: {s.status} | Public: {s.public_score}")
                return 0
            if sub == "submit":
                res = client.submit_competition(
                    competition=args.competition,
                    file_path=args.file,
                    message=getattr(args, "message", "Submitted via SciFi"),
                )
                print(json.dumps(res, indent=2))
                return 0

        if section == "kernels":
            sub = getattr(args, "kaggle_kernel_action", None) or "list"
            if sub == "list":
                kernels = client.list_kernels(
                    search=getattr(args, "search", None),
                    user=getattr(args, "user", None),
                    page=getattr(args, "page", 1),
                )
                if getattr(args, "json", False):
                    print(json.dumps([k.to_dict() for k in kernels], indent=2))
                    return 0
                for k in kernels:
                    print(f"  - {k.ref} | {k.title} [{k.language}/{k.kernel_type}]")
                return 0
            if sub == "pull":
                res = client.pull_kernel(args.kernel, dest_dir=getattr(args, "dir", None))
                print(json.dumps(res, indent=2))
                return 0
            if sub == "push":
                res = client.push_kernel(args.folder)
                print(json.dumps(res, indent=2))
                return 0
            if sub == "status":
                res = client.kernel_status(args.kernel)
                print(json.dumps(res, indent=2))
                return 0
            if sub == "output":
                res = client.kernel_output(args.kernel, dest_dir=getattr(args, "dir", None))
                print(json.dumps(res, indent=2))
                return 0

    except (KaggleAuthError, KaggleAPIError, ValueError, FileNotFoundError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    return 0
