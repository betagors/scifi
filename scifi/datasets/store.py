"""
Local dataset storage, manifest tracking, and safe archive extraction.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tarfile
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scifi.datasets.models import LocalDatasetRecord


def sanitize_dataset_slug(identifier: str) -> str:
    """Convert a dataset identifier (e.g. 'owner/slug' or URL) into a safe folder name."""
    cleaned = identifier.strip().replace("\\", "/")
    cleaned = re.sub(r"^https?://", "", cleaned)
    cleaned = cleaned.replace("/", "__")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", cleaned).strip("._")
    return cleaned or "dataset"


def safe_extract_archive(archive_path: Path, dest_dir: Path, remove_archive: bool = False) -> list[str]:
    """
    Safely extract a .zip, .tar, .tar.gz, or .tgz archive into `dest_dir`,
    guarding against path traversal (zip-slip). Returns relative extracted file paths.
    """
    dest_resolved = dest_dir.resolve()
    dest_resolved.mkdir(parents=True, exist_ok=True)
    extracted: list[str] = []
    lower_name = archive_path.name.lower()

    if lower_name.endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as zf:
            for member in zf.infolist():
                target = (dest_resolved / member.filename).resolve()
                if target != dest_resolved and not str(target).startswith(str(dest_resolved) + os.sep):
                    raise ValueError(f"Unsafe archive member path detected: {member.filename}")
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member, "r") as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    extracted.append(str(target.relative_to(dest_resolved)).replace("\\", "/"))
    elif lower_name.endswith((".tar.gz", ".tgz", ".tar")):
        mode = "r:gz" if lower_name.endswith((".tar.gz", ".tgz")) else "r:"
        with tarfile.open(archive_path, mode) as tf:
            for member in tf.getmembers():
                target = (dest_resolved / member.name).resolve()
                if target != dest_resolved and not str(target).startswith(str(dest_resolved) + os.sep):
                    raise ValueError(f"Unsafe archive member path detected: {member.name}")
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    src = tf.extractfile(member)
                    if src is not None:
                        with src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        extracted.append(str(target.relative_to(dest_resolved)).replace("\\", "/"))
    else:
        return []

    if remove_archive and archive_path.exists():
        archive_path.unlink()

    return extracted


def collect_directory_stats(root: Path) -> tuple[list[str], int]:
    """Return (sorted relative file paths, total_bytes) for all files under `root`."""
    if not root.is_dir():
        return [], 0
    files: list[str] = []
    total_bytes = 0
    for item in sorted(root.rglob("*")):
        if item.is_file():
            files.append(str(item.relative_to(root)).replace("\\", "/"))
            try:
                total_bytes += item.stat().st_size
            except OSError:
                pass
    return files, total_bytes


class DatasetManifestStore:
    """Manages `<datasets_dir>/manifest.json` for tracking locally downloaded datasets."""

    def __init__(self, datasets_dir: Path | str) -> None:
        self.datasets_dir = Path(datasets_dir).expanduser().resolve()
        self.manifest_path = self.datasets_dir / "manifest.json"

    def _load_raw(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            return {"version": 1, "datasets": {}}
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("datasets"), dict):
                return data
        except Exception:
            pass
        return {"version": 1, "datasets": {}}

    def _save_raw(self, payload: dict[str, Any]) -> None:
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        formatted = json.dumps(payload, indent=2) + "\n"
        tmp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.datasets_dir, delete=False) as tf:
                tf.write(formatted)
                tmp_name = tf.name
            os.replace(tmp_name, self.manifest_path)
        except Exception:
            if tmp_name and os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass
            raise

    @staticmethod
    def make_key(provider: str, identifier: str) -> str:
        return f"{provider.lower().strip()}:{identifier.strip()}"

    def register(
        self,
        provider: str,
        identifier: str,
        local_path: Path | str,
        title: str = "",
        url: str | None = None,
    ) -> LocalDatasetRecord:
        path = Path(local_path).resolve()
        files, total_bytes = collect_directory_stats(path)
        record = LocalDatasetRecord(
            provider=provider.lower().strip(),
            identifier=identifier.strip(),
            local_path=str(path),
            downloaded_at=datetime.now(UTC).isoformat(),
            title=title or identifier,
            files=files,
            total_bytes=total_bytes,
            url=url,
        )
        data = self._load_raw()
        key = self.make_key(provider, identifier)
        data["datasets"][key] = record.to_dict()
        self._save_raw(data)
        return record

    def list_local(self) -> list[LocalDatasetRecord]:
        data = self._load_raw()
        records: list[LocalDatasetRecord] = []
        for entry in data.get("datasets", {}).values():
            if isinstance(entry, dict):
                records.append(
                    LocalDatasetRecord(
                        provider=str(entry.get("provider", "")),
                        identifier=str(entry.get("identifier", "")),
                        local_path=str(entry.get("local_path", "")),
                        downloaded_at=str(entry.get("downloaded_at", "")),
                        title=str(entry.get("title", "")),
                        files=list(entry.get("files", [])),
                        total_bytes=int(entry.get("total_bytes", 0)),
                        url=entry.get("url"),
                    )
                )
        return records

    def get_local(self, identifier_or_key: str) -> LocalDatasetRecord | None:
        data = self._load_raw()
        datasets = data.get("datasets", {})
        if identifier_or_key in datasets:
            entry = datasets[identifier_or_key]
            return LocalDatasetRecord(**entry)
        for entry in datasets.values():
            if isinstance(entry, dict) and entry.get("identifier") == identifier_or_key:
                return LocalDatasetRecord(**entry)
        return None

    def remove(self, identifier_or_key: str, delete_files: bool = False) -> bool:
        data = self._load_raw()
        datasets = data.get("datasets", {})
        target_key: str | None = None
        if identifier_or_key in datasets:
            target_key = identifier_or_key
        else:
            for k, entry in datasets.items():
                if isinstance(entry, dict) and entry.get("identifier") == identifier_or_key:
                    target_key = k
                    break
        if target_key is None:
            return False

        entry = datasets.pop(target_key)
        self._save_raw(data)
        if delete_files and isinstance(entry, dict) and entry.get("local_path"):
            p = Path(entry["local_path"])
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
        return True
