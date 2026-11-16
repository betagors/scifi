"""
Additional Dataset Providers for SciFi: Hugging Face Hub, Zenodo, and Direct URL.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import requests

from scifi.config import get_datasets_dir, resolve_config
from scifi.datasets.http import get_with_retry, stream_to_file
from scifi.datasets.models import DatasetFile, DatasetInfo, DownloadResult
from scifi.datasets.store import (
    collect_directory_stats,
    safe_extract_archive,
    sanitize_dataset_slug,
)

HF_API_BASE = "https://huggingface.co/api"
HF_WEB_BASE = "https://huggingface.co"
ZENODO_API_BASE = "https://zenodo.org/api/records"


class HuggingFaceClient:
    """Client for searching and downloading datasets from Hugging Face Hub."""

    def __init__(
        self,
        token: str | None = None,
        workspace_dir: Path | str | None = None,
        timeout: int = 60,
        session: requests.Session | None = None,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.timeout = timeout
        self.session = session or requests.Session()
        cfg = resolve_config(workspace_dir=workspace_dir)
        self.token = token or os.environ.get("HF_TOKEN") or cfg.hf_token

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def search_datasets(self, query: str, limit: int = 20) -> list[DatasetInfo]:
        """Search Hugging Face Hub datasets."""
        resp = self.session.get(
            f"{HF_API_BASE}/datasets",
            params={"search": query, "limit": limit},
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        items = resp.json()
        if not isinstance(items, list):
            return []

        results: list[DatasetInfo] = []
        for item in items[:limit]:
            repo_id = str(item.get("id") or "")
            owner = item.get("author") or (repo_id.split("/")[0] if "/" in repo_id else None)
            results.append(
                DatasetInfo(
                    provider="huggingface",
                    identifier=repo_id,
                    title=repo_id,
                    description=str(item.get("description") or "")[:300],
                    owner=str(owner) if owner else None,
                    url=f"{HF_WEB_BASE}/datasets/{repo_id}" if repo_id else None,
                    downloads=item.get("downloads"),
                    likes_or_votes=item.get("likes"),
                    last_updated=item.get("lastModified"),
                    tags=[str(t) for t in item.get("tags", []) if isinstance(t, str)],
                )
            )
        return results

    def list_files(self, repo_id: str, revision: str = "main") -> list[DatasetFile]:
        """List files in a Hugging Face dataset repository."""
        resp = self.session.get(
            f"{HF_API_BASE}/datasets/{repo_id.strip()}/tree/{quote(revision, safe='')}",
            params={"recursive": "true"},
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        items = resp.json()
        if not isinstance(items, list):
            return []
        files: list[DatasetFile] = []
        for item in items:
            if isinstance(item, dict) and item.get("type") == "file":
                path = str(item.get("path", ""))
                files.append(
                    DatasetFile(
                        name=path,
                        size_bytes=item.get("size"),
                        url=f"{HF_WEB_BASE}/datasets/{repo_id.strip()}/resolve/{revision}/{path}",
                    )
                )
        return files

    def download_dataset(
        self,
        repo_id: str,
        dest_dir: Path | str | None = None,
        files: list[str] | None = None,
        revision: str = "main",
        unzip: bool = True,
    ) -> DownloadResult:
        """Download files from a Hugging Face dataset repository."""
        repo = repo_id.strip()
        target_dir = (
            Path(dest_dir).expanduser().resolve()
            if dest_dir
            else (get_datasets_dir(workspace_dir=self.workspace_dir) / "huggingface" / sanitize_dataset_slug(repo))
        )
        target_dir.mkdir(parents=True, exist_ok=True)

        if files:
            to_download = [
                DatasetFile(
                    name=f,
                    url=f"{HF_WEB_BASE}/datasets/{repo}/resolve/{revision}/{f.lstrip('/')}",
                )
                for f in files
            ]
        else:
            to_download = self.list_files(repo, revision=revision)

        for df in to_download:
            if not df.url:
                continue
            rel = Path(df.name)
            # Guard against traversal
            out_path = (target_dir / rel).resolve()
            if out_path != target_dir and not str(out_path).startswith(str(target_dir) + os.sep):
                raise ValueError(f"Unsafe file path from Hugging Face: {df.name}")
            out_path.parent.mkdir(parents=True, exist_ok=True)

            resp = get_with_retry(self.session, df.url, headers=self._headers(), stream=True, timeout=self.timeout)
            resp.raise_for_status()
            stream_to_file(resp, out_path)
            if unzip and out_path.name.lower().endswith((".zip", ".tar.gz", ".tgz", ".tar")):
                safe_extract_archive(out_path, out_path.parent, remove_archive=False)

        local_files, total_bytes = collect_directory_stats(target_dir)
        return DownloadResult(
            provider="huggingface",
            identifier=repo,
            local_path=str(target_dir),
            files=local_files,
            total_bytes=total_bytes,
            extracted=unzip,
        )


class ZenodoClient:
    """Client for searching and downloading scientific datasets from Zenodo."""

    def __init__(
        self,
        token: str | None = None,
        workspace_dir: Path | str | None = None,
        timeout: int = 60,
        session: requests.Session | None = None,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.timeout = timeout
        self.session = session or requests.Session()
        cfg = resolve_config(workspace_dir=workspace_dir)
        self.token = token or os.environ.get("ZENODO_TOKEN") or cfg.zenodo_token

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    @staticmethod
    def _extract_record_id(record_id_or_doi: str) -> str:
        raw = record_id_or_doi.strip()
        m = re.search(r"zenodo\.(\d+)", raw, re.IGNORECASE)
        if m:
            return m.group(1)
        m2 = re.search(r"/records/(\d+)", raw)
        if m2:
            return m2.group(1)
        if raw.isdigit():
            return raw
        raise ValueError(f"Could not extract Zenodo record ID from: {record_id_or_doi!r}")

    def search_datasets(self, query: str, limit: int = 20) -> list[DatasetInfo]:
        """Search Zenodo dataset records."""
        resp = self.session.get(
            ZENODO_API_BASE,
            params={"q": query, "type": "dataset", "size": limit},
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        hits = payload.get("hits", {}).get("hits", []) if isinstance(payload, dict) else []
        results: list[DatasetInfo] = []
        for hit in hits[:limit]:
            rec_id = str(hit.get("id", ""))
            meta = hit.get("metadata", {}) if isinstance(hit.get("metadata"), dict) else {}
            creators = meta.get("creators", [])
            owner = creators[0].get("name") if creators and isinstance(creators[0], dict) else None
            lic = meta.get("license", {}).get("id") if isinstance(meta.get("license"), dict) else None
            files = [
                DatasetFile(
                    name=str(f.get("key", "")),
                    size_bytes=f.get("size"),
                    url=(f.get("links") or {}).get("self"),
                    checksum=f.get("checksum"),
                )
                for f in hit.get("files", [])
                if isinstance(f, dict)
            ]
            results.append(
                DatasetInfo(
                    provider="zenodo",
                    identifier=rec_id,
                    title=str(meta.get("title") or f"Zenodo {rec_id}"),
                    description=re.sub(r"<[^>]+>", "", str(meta.get("description") or ""))[:300],
                    owner=str(owner) if owner else None,
                    url=hit.get("links", {}).get("self_html") or f"https://zenodo.org/records/{rec_id}",
                    license_name=str(lic) if lic else None,
                    last_updated=hit.get("updated"),
                    tags=[str(k) for k in meta.get("keywords", []) if isinstance(k, str)],
                    files=files,
                )
            )
        return results

    def get_record(self, record_id_or_doi: str) -> DatasetInfo:
        """Fetch metadata and file list for a specific Zenodo record or DOI."""
        rec_id = self._extract_record_id(record_id_or_doi)
        resp = self.session.get(
            f"{ZENODO_API_BASE}/{rec_id}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        hit = resp.json()
        meta = hit.get("metadata", {}) if isinstance(hit.get("metadata"), dict) else {}
        creators = meta.get("creators", [])
        owner = creators[0].get("name") if creators and isinstance(creators[0], dict) else None
        files = [
            DatasetFile(
                name=str(f.get("key", "")),
                size_bytes=f.get("size"),
                url=(f.get("links") or {}).get("self"),
                checksum=f.get("checksum"),
            )
            for f in hit.get("files", [])
            if isinstance(f, dict)
        ]
        return DatasetInfo(
            provider="zenodo",
            identifier=rec_id,
            title=str(meta.get("title") or f"Zenodo {rec_id}"),
            description=re.sub(r"<[^>]+>", "", str(meta.get("description") or ""))[:500],
            owner=str(owner) if owner else None,
            url=f"https://zenodo.org/records/{rec_id}",
            files=files,
        )

    def download_dataset(
        self,
        record_id_or_doi: str,
        dest_dir: Path | str | None = None,
        files: list[str] | None = None,
        unzip: bool = True,
    ) -> DownloadResult:
        """Download files from a Zenodo dataset record."""
        info = self.get_record(record_id_or_doi)
        rec_id = info.identifier
        target_dir = (
            Path(dest_dir).expanduser().resolve()
            if dest_dir
            else (get_datasets_dir(workspace_dir=self.workspace_dir) / "zenodo" / f"zenodo_{rec_id}")
        )
        target_dir.mkdir(parents=True, exist_ok=True)

        selected = info.files
        if files:
            want = set(files)
            selected = [f for f in info.files if f.name in want]

        for df in selected:
            if not df.url:
                continue
            out_path = (target_dir / Path(df.name).name).resolve()
            resp = get_with_retry(
                self.session,
                df.url,
                headers=self._headers(),
                stream=True,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            stream_to_file(resp, out_path)
            if unzip and out_path.name.lower().endswith((".zip", ".tar.gz", ".tgz", ".tar")):
                safe_extract_archive(out_path, target_dir, remove_archive=False)

        local_files, total_bytes = collect_directory_stats(target_dir)
        return DownloadResult(
            provider="zenodo",
            identifier=rec_id,
            local_path=str(target_dir),
            files=local_files,
            total_bytes=total_bytes,
            extracted=unzip,
        )


class DirectURLDownloader:
    """Download datasets from arbitrary HTTP(S) URLs into the default datasets folder."""

    def __init__(
        self,
        workspace_dir: Path | str | None = None,
        timeout: int = 120,
        session: requests.Session | None = None,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.timeout = timeout
        self.session = session or requests.Session()

    def download_url(
        self,
        url: str,
        dest_dir: Path | str | None = None,
        filename: str | None = None,
        unzip: bool = True,
    ) -> DownloadResult:
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r}")

        inferred_name = filename or Path(unquote(parsed.path)).name or "dataset_download"
        slug = sanitize_dataset_slug(inferred_name.rsplit(".", 1)[0] if "." in inferred_name else inferred_name)
        target_dir = (
            Path(dest_dir).expanduser().resolve()
            if dest_dir
            else (get_datasets_dir(workspace_dir=self.workspace_dir) / "url" / slug)
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        out_file = target_dir / Path(inferred_name).name

        resp = get_with_retry(self.session, url.strip(), stream=True, timeout=self.timeout)
        resp.raise_for_status()
        stream_to_file(resp, out_file)

        extracted = False
        if unzip and out_file.name.lower().endswith((".zip", ".tar.gz", ".tgz", ".tar")):
            safe_extract_archive(out_file, target_dir, remove_archive=True)
            extracted = True

        local_files, total_bytes = collect_directory_stats(target_dir)
        return DownloadResult(
            provider="url",
            identifier=url.strip(),
            local_path=str(target_dir),
            files=local_files,
            total_bytes=total_bytes,
            extracted=extracted,
        )
