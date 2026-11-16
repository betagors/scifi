"""
Kaggle REST API v1 Client for SciFi.

Supports datasets (search, list files, download, push), competitions (list,
files, download, submit, submissions), and kernels/notebooks (list, pull,
push/run, status, output) using `requests` with zero mandatory third-party SDKs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from scifi.config import get_datasets_dir, resolve_config, set_global_config_value
from scifi.datasets.http import request_with_retry, stream_to_file
from scifi.datasets.models import (
    DatasetFile,
    DatasetInfo,
    DownloadResult,
    KaggleCompetition,
    KaggleKernel,
    KaggleSubmission,
)
from scifi.datasets.store import (
    collect_directory_stats,
    safe_extract_archive,
    sanitize_dataset_slug,
)

KAGGLE_API_BASE = "https://www.kaggle.com/api/v1"


class KaggleAuthError(RuntimeError):
    """Raised when Kaggle credentials are missing or invalid."""


class KaggleAPIError(RuntimeError):
    """Raised when Kaggle API returns an error response."""


def _parse_ref(ref: str) -> tuple[str, str]:
    """Split an 'owner/slug' reference into (owner, slug)."""
    cleaned = ref.strip().strip("/")
    if "/" not in cleaned:
        raise ValueError(f"Expected 'owner/slug' format, got: {ref!r}")
    owner, slug = cleaned.split("/", 1)
    if not owner or not slug:
        raise ValueError(f"Invalid Kaggle reference: {ref!r}")
    return owner, slug


def resolve_kaggle_credentials(
    username: str | None = None,
    key: str | None = None,
    token: str | None = None,
    workspace_dir: Path | str | None = None,
) -> dict[str, str | None]:
    """
    Resolve Kaggle credentials from:
    1. Explicit arguments
    2. Environment variables (`KAGGLE_API_TOKEN`, `KAGGLE_USERNAME` + `KAGGLE_KEY`)
    3. `kaggle.json` in `KAGGLE_CONFIG_DIR` or `~/.kaggle/kaggle.json`
    4. SciFi config (`kaggle_username`, `kaggle_key`)
    """
    if token:
        return {"mode": "bearer", "token": token.strip(), "username": username, "key": None, "source": "argument"}
    if username and key:
        return {"mode": "basic", "username": username.strip(), "key": key.strip(), "token": None, "source": "argument"}

    env_token = os.environ.get("KAGGLE_API_TOKEN")
    if env_token and env_token.strip():
        return {
            "mode": "bearer",
            "token": env_token.strip(),
            "username": os.environ.get("KAGGLE_USERNAME"),
            "key": None,
            "source": "env:KAGGLE_API_TOKEN",
        }

    env_user = os.environ.get("KAGGLE_USERNAME")
    env_key = os.environ.get("KAGGLE_KEY")
    if env_user and env_key:
        return {
            "mode": "basic",
            "username": env_user.strip(),
            "key": env_key.strip(),
            "token": None,
            "source": "env:KAGGLE_USERNAME/KAGGLE_KEY",
        }

    kaggle_dir = Path(os.environ.get("KAGGLE_CONFIG_DIR") or (Path.home() / ".kaggle"))
    kaggle_json = kaggle_dir / "kaggle.json"
    if kaggle_json.is_file():
        try:
            data = json.loads(kaggle_json.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("username") and data.get("key"):
                return {
                    "mode": "basic",
                    "username": str(data["username"]).strip(),
                    "key": str(data["key"]).strip(),
                    "token": None,
                    "source": str(kaggle_json),
                }
        except Exception:
            pass

    cfg = resolve_config(workspace_dir=workspace_dir)
    if cfg.kaggle_username and cfg.kaggle_key:
        return {
            "mode": "basic",
            "username": cfg.kaggle_username,
            "key": cfg.kaggle_key,
            "token": None,
            "source": "scifi_config",
        }

    # Self-recovery: if user downloaded kaggle.json to ~/Downloads, install it to ~/.kaggle/kaggle.json
    if not os.environ.get("KAGGLE_CONFIG_DIR"):
        downloads_json = Path.home() / "Downloads" / "kaggle.json"
        if downloads_json.is_file():
            try:
                data = json.loads(downloads_json.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("username") and data.get("key"):
                    uname = str(data["username"]).strip()
                    ukey = str(data["key"]).strip()
                    save_kaggle_credentials(uname, ukey, target="kaggle_json")
                    return {
                        "mode": "basic",
                        "username": uname,
                        "key": ukey,
                        "token": None,
                        "source": f"recovered_from_downloads:{downloads_json}",
                    }
            except Exception:
                pass

    return {"mode": "none", "username": None, "key": None, "token": None, "source": None}


def save_kaggle_credentials(
    username: str,
    key: str,
    target: str = "kaggle_json",
    kaggle_dir: Path | str | None = None,
) -> Path:
    """
    Persist Kaggle credentials to `~/.kaggle/kaggle.json` (default) or `~/.scifi/config.json`.
    """
    uname = username.strip()
    ukey = key.strip()
    if not uname or not ukey:
        raise ValueError("Both Kaggle username and API key are required.")

    if target == "scifi_config":
        set_global_config_value("kaggle_username", uname)
        return set_global_config_value("kaggle_key", ukey)

    dest_dir = (
        Path(kaggle_dir) if kaggle_dir else Path(os.environ.get("KAGGLE_CONFIG_DIR") or (Path.home() / ".kaggle"))
    )
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / "kaggle.json"
    dest_file.write_text(json.dumps({"username": uname, "key": ukey}, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(dest_file, 0o600)
    except OSError:
        pass
    return dest_file


class KaggleClient:
    """Client for Kaggle REST API v1."""

    def __init__(
        self,
        username: str | None = None,
        key: str | None = None,
        token: str | None = None,
        workspace_dir: Path | str | None = None,
        timeout: int = 60,
        session: requests.Session | None = None,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.timeout = timeout
        self.creds = resolve_kaggle_credentials(
            username=username,
            key=key,
            token=token,
            workspace_dir=workspace_dir,
        )
        self.session = session or requests.Session()

    @property
    def is_authenticated(self) -> bool:
        return self.creds.get("mode") in ("basic", "bearer")

    def status(self) -> dict[str, Any]:
        """Return authentication and configuration status (never exposing the raw key)."""
        return {
            "authenticated": self.is_authenticated,
            "auth_mode": self.creds.get("mode"),
            "username": self.creds.get("username"),
            "credential_source": self.creds.get("source"),
            "default_datasets_dir": str(get_datasets_dir(workspace_dir=self.workspace_dir)),
        }

    def login(
        self,
        username: str,
        key: str,
        *,
        verify: bool = True,
        target: str = "kaggle_json",
    ) -> dict[str, Any]:
        """
        Configure and optionally verify Kaggle credentials, persisting them
        to `~/.kaggle/kaggle.json` (default) or `~/.scifi/config.json`.
        """
        self.creds = {
            "mode": "basic",
            "username": username.strip(),
            "key": key.strip(),
            "token": None,
            "source": "login",
        }
        if verify:
            self._request("GET", "datasets/list", params={"page": 1}, require_auth=True)
        saved_path = save_kaggle_credentials(username, key, target=target)
        self.creds["source"] = str(saved_path)
        return {
            "authenticated": True,
            "username": username.strip(),
            "saved_to": str(saved_path),
            "verified": verify,
        }

    def _require_auth(self) -> None:
        if not self.is_authenticated:
            raise KaggleAuthError(
                "Kaggle credentials not found. Place kaggle.json in ~/.kaggle/kaggle.json, "
                "set KAGGLE_USERNAME & KAGGLE_KEY (or KAGGLE_API_TOKEN), or run: "
                "`sf config set kaggle_username <user>` and `sf config set kaggle_key <key>`."
            )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        data: Any = None,
        stream: bool = False,
        require_auth: bool = True,
    ) -> requests.Response:
        if require_auth:
            self._require_auth()

        url = f"{KAGGLE_API_BASE}/{path.lstrip('/')}"
        headers: dict[str, str] = {"Accept": "application/json"}
        auth: tuple[str, str] | None = None

        if self.creds.get("mode") == "bearer" and self.creds.get("token"):
            headers["Authorization"] = f"Bearer {self.creds['token']}"
        elif self.creds.get("mode") == "basic" and self.creds.get("username") and self.creds.get("key"):
            auth = (str(self.creds["username"]), str(self.creds["key"]))

        resp = request_with_retry(
            self.session,
            method.upper(),
            url,
            params=params,
            json=json_body,
            data=data,
            headers=headers,
            auth=auth,
            timeout=self.timeout,
            stream=stream,
        )
        if resp.status_code in (401, 403):
            raise KaggleAuthError(
                f"Kaggle authentication/permission error ({resp.status_code}) on {path}: {resp.text[:300]}"
            )
        if resp.status_code >= 400:
            raise KaggleAPIError(f"Kaggle API error ({resp.status_code}) on {path}: {resp.text[:400]}")
        return resp

    def _download_stream(self, resp: requests.Response, target_file: Path) -> int:
        return stream_to_file(resp, target_file)

    # ------------------------------------------------------------------
    # Datasets
    # ------------------------------------------------------------------

    def search_datasets(
        self,
        query: str = "",
        sort_by: str = "hottest",
        file_type: str | None = None,
        license_name: str | None = None,
        page: int = 1,
        max_results: int = 20,
    ) -> list[DatasetInfo]:
        """Search Kaggle datasets."""
        params: dict[str, Any] = {
            "search": query,
            "sortBy": sort_by,
            "page": page,
        }
        if file_type:
            params["filetype"] = file_type
        if license_name:
            params["license"] = license_name

        resp = self._request("GET", "datasets/list", params=params, require_auth=True)
        items = resp.json()
        if not isinstance(items, list):
            return []

        results: list[DatasetInfo] = []
        for item in items[:max_results]:
            ref = str(item.get("ref", ""))
            owner = ref.split("/")[0] if "/" in ref else item.get("ownerName")
            results.append(
                DatasetInfo(
                    provider="kaggle",
                    identifier=ref,
                    title=str(item.get("title") or ref),
                    description=str(item.get("subtitle") or ""),
                    owner=str(owner) if owner else None,
                    url=f"https://www.kaggle.com/datasets/{ref}" if ref else None,
                    license_name=item.get("licenseName"),
                    downloads=item.get("downloadCount"),
                    likes_or_votes=item.get("voteCount"),
                    size_bytes=item.get("totalBytes"),
                    last_updated=item.get("lastUpdated"),
                    tags=[str(t.get("name", "")) for t in item.get("tags", []) if isinstance(t, dict)],
                )
            )
        return results

    def list_dataset_files(self, dataset_ref: str) -> list[DatasetFile]:
        """List files inside a Kaggle dataset (`owner/slug`)."""
        owner, slug = _parse_ref(dataset_ref)
        resp = self._request("GET", f"datasets/list/{owner}/{slug}", require_auth=True)
        payload = resp.json()
        raw_files = payload.get("datasetFiles", []) if isinstance(payload, dict) else []
        files: list[DatasetFile] = []
        for f in raw_files:
            if isinstance(f, dict):
                files.append(
                    DatasetFile(
                        name=str(f.get("name", "")),
                        size_bytes=f.get("totalBytes"),
                        url=f.get("url"),
                    )
                )
        return files

    def download_dataset(
        self,
        dataset_ref: str,
        dest_dir: Path | str | None = None,
        file_name: str | None = None,
        unzip: bool = True,
    ) -> DownloadResult:
        """Download a Kaggle dataset (or a single file) into `dest_dir` (or default datasets_dir)."""
        owner, slug = _parse_ref(dataset_ref)
        base_dir = (
            Path(dest_dir).expanduser().resolve()
            if dest_dir
            else (get_datasets_dir(workspace_dir=self.workspace_dir) / "kaggle" / sanitize_dataset_slug(dataset_ref))
        )
        base_dir.mkdir(parents=True, exist_ok=True)

        if file_name:
            path = f"datasets/download/{owner}/{slug}/{quote(file_name, safe='')}"
            resp = self._request("GET", path, stream=True, require_auth=True)
            out_file = base_dir / Path(file_name).name
            self._download_stream(resp, out_file)
            extracted = False
            if unzip and out_file.suffix.lower() == ".zip":
                safe_extract_archive(out_file, base_dir, remove_archive=True)
                extracted = True
        else:
            path = f"datasets/download/{owner}/{slug}"
            resp = self._request("GET", path, stream=True, require_auth=True)
            zip_path = base_dir / f"{slug}.zip"
            self._download_stream(resp, zip_path)
            extracted = False
            if unzip:
                safe_extract_archive(zip_path, base_dir, remove_archive=True)
                extracted = True

        files, total_bytes = collect_directory_stats(base_dir)
        return DownloadResult(
            provider="kaggle",
            identifier=f"{owner}/{slug}",
            local_path=str(base_dir),
            files=files,
            total_bytes=total_bytes,
            extracted=extracted,
        )

    def _upload_blob(self, file_path: Path, blob_type: str = "dataset") -> str:
        """Upload a file to Kaggle's signed blob endpoint and return the upload token."""
        size = file_path.stat().st_size
        mtime = int(file_path.stat().st_mtime)
        if blob_type == "dataset":
            init_path = f"datasets/upload/file/{size}/{mtime}"
        elif blob_type == "submission":
            init_path = f"competitions/submissions/url/{size}/{mtime}"
        else:
            raise ValueError(f"Unsupported blob_type: {blob_type}")

        resp = self._request("POST", init_path, json_body={"fileName": file_path.name}, require_auth=True)
        info = resp.json()
        create_url = info.get("createUrl")
        token = info.get("token")
        if not create_url or not token:
            raise KaggleAPIError(f"Unexpected upload initialization response: {info}")

        with open(file_path, "rb") as f:
            up_resp = self.session.put(create_url, data=f, timeout=max(self.timeout, 300))
        if up_resp.status_code >= 400:
            raise KaggleAPIError(f"Blob upload failed ({up_resp.status_code}): {up_resp.text[:300]}")
        return str(token)

    def push_dataset(
        self,
        folder: Path | str,
        title: str | None = None,
        slug: str | None = None,
        owner: str | None = None,
        is_private: bool = True,
        version_notes: str = "Uploaded via SciFi",
        create_new: bool = False,
    ) -> dict[str, Any]:
        """
        Create a new Kaggle dataset or push a new version from a local folder.
        Reads `dataset-metadata.json` in `folder` if present, or uses provided metadata.
        """
        self._require_auth()
        src_dir = Path(folder).expanduser().resolve()
        if not src_dir.is_dir():
            raise FileNotFoundError(f"Dataset folder not found: {src_dir}")

        meta_file = src_dir / "dataset-metadata.json"
        meta: dict[str, Any] = {}
        if meta_file.is_file():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))

        dataset_id = meta.get("id")
        if not dataset_id:
            resolved_owner = owner or self.creds.get("username")
            resolved_slug = slug or sanitize_dataset_slug(src_dir.name).replace("_", "-")
            if not resolved_owner:
                raise KaggleAPIError("Owner username is required to push a dataset.")
            dataset_id = f"{resolved_owner}/{resolved_slug}"

        owner_part, slug_part = _parse_ref(dataset_id)
        resolved_title = title or meta.get("title") or slug_part

        uploaded_files: list[dict[str, str]] = []
        for item in sorted(src_dir.iterdir()):
            if item.is_file() and item.name != "dataset-metadata.json":
                token = self._upload_blob(item, blob_type="dataset")
                uploaded_files.append({"token": token})

        if not uploaded_files:
            raise ValueError(f"No data files found in {src_dir} to upload.")

        if create_new:
            body = {
                "title": resolved_title,
                "slug": slug_part,
                "ownerSlug": owner_part,
                "isPrivate": is_private,
                "licenseName": meta.get("licenses", [{}])[0].get("name", "CC0-1.0")
                if isinstance(meta.get("licenses"), list) and meta.get("licenses")
                else "CC0-1.0",
                "files": uploaded_files,
            }
            resp = self._request("POST", "datasets/create/new", json_body=body, require_auth=True)
        else:
            body = {
                "versionNotes": version_notes,
                "files": uploaded_files,
                "deleteOldVersions": False,
            }
            resp = self._request(
                "POST", f"datasets/create/version/{owner_part}/{slug_part}", json_body=body, require_auth=True
            )
        return resp.json()

    # ------------------------------------------------------------------
    # Competitions
    # ------------------------------------------------------------------

    def list_competitions(
        self,
        search: str | None = None,
        category: str | None = None,
        sort_by: str = "latestDeadline",
        page: int = 1,
        max_results: int = 20,
    ) -> list[KaggleCompetition]:
        """List Kaggle competitions."""
        params: dict[str, Any] = {"sortBy": sort_by, "page": page}
        if search:
            params["search"] = search
        if category:
            params["category"] = category

        resp = self._request("GET", "competitions/list", params=params, require_auth=True)
        items = resp.json()
        if not isinstance(items, list):
            return []

        out: list[KaggleCompetition] = []
        for item in items[:max_results]:
            ref = str(item.get("ref", ""))
            out.append(
                KaggleCompetition(
                    ref=ref,
                    title=str(item.get("title") or ref),
                    url=str(item.get("url") or f"https://www.kaggle.com/competitions/{ref}"),
                    category=str(item.get("category") or ""),
                    reward=str(item.get("reward") or ""),
                    deadline=str(item.get("deadline") or ""),
                    team_count=item.get("teamCount"),
                    user_has_entered=bool(item.get("userHasEntered", False)),
                )
            )
        return out

    def list_competition_files(self, competition: str) -> list[DatasetFile]:
        """List data files for a Kaggle competition."""
        resp = self._request("GET", f"competitions/data/list/{competition.strip()}", require_auth=True)
        items = resp.json()
        if not isinstance(items, list):
            return []
        return [
            DatasetFile(
                name=str(f.get("name", "")),
                size_bytes=f.get("totalBytes"),
                url=f.get("url"),
            )
            for f in items
            if isinstance(f, dict)
        ]

    def download_competition(
        self,
        competition: str,
        dest_dir: Path | str | None = None,
        file_name: str | None = None,
        unzip: bool = True,
    ) -> DownloadResult:
        """Download competition data into `dest_dir` or `<datasets_dir>/kaggle/competitions/<competition>`."""
        comp = competition.strip()
        base_dir = (
            Path(dest_dir).expanduser().resolve()
            if dest_dir
            else (
                get_datasets_dir(workspace_dir=self.workspace_dir)
                / "kaggle"
                / "competitions"
                / sanitize_dataset_slug(comp)
            )
        )
        base_dir.mkdir(parents=True, exist_ok=True)

        if file_name:
            path = f"competitions/data/download/{comp}/{quote(file_name, safe='')}"
            resp = self._request("GET", path, stream=True, require_auth=True)
            out_file = base_dir / Path(file_name).name
            self._download_stream(resp, out_file)
            extracted = False
            if unzip and out_file.suffix.lower() == ".zip":
                safe_extract_archive(out_file, base_dir, remove_archive=True)
                extracted = True
        else:
            path = f"competitions/data/download-all/{comp}"
            resp = self._request("GET", path, stream=True, require_auth=True)
            zip_path = base_dir / f"{comp}.zip"
            self._download_stream(resp, zip_path)
            extracted = False
            if unzip:
                safe_extract_archive(zip_path, base_dir, remove_archive=True)
                extracted = True

        files, total_bytes = collect_directory_stats(base_dir)
        return DownloadResult(
            provider="kaggle",
            identifier=f"competition:{comp}",
            local_path=str(base_dir),
            files=files,
            total_bytes=total_bytes,
            extracted=extracted,
        )

    def list_submissions(self, competition: str) -> list[KaggleSubmission]:
        """List your submissions for a Kaggle competition."""
        resp = self._request("GET", f"competitions/submissions/list/{competition.strip()}", require_auth=True)
        items = resp.json()
        if not isinstance(items, list):
            return []
        return [
            KaggleSubmission(
                ref=str(s.get("ref", "")),
                file_name=str(s.get("fileName", "")),
                date=str(s.get("date", "")),
                description=str(s.get("description", "")),
                status=str(s.get("status", "")),
                public_score=s.get("publicScore"),
                private_score=s.get("privateScore"),
            )
            for s in items
            if isinstance(s, dict)
        ]

    def submit_competition(
        self,
        competition: str,
        file_path: Path | str,
        message: str = "Submitted via SciFi",
    ) -> dict[str, Any]:
        """Submit a prediction file to a Kaggle competition."""
        sub_file = Path(file_path).expanduser().resolve()
        if not sub_file.is_file():
            raise FileNotFoundError(f"Submission file not found: {sub_file}")
        token = self._upload_blob(sub_file, blob_type="submission")
        resp = self._request(
            "POST",
            f"competitions/submissions/submit/{competition.strip()}",
            json_body={"blobFileTokens": token, "submissionDescription": message},
            require_auth=True,
        )
        return resp.json()

    # ------------------------------------------------------------------
    # Kernels / Notebooks
    # ------------------------------------------------------------------

    def list_kernels(
        self,
        search: str | None = None,
        user: str | None = None,
        dataset: str | None = None,
        competition: str | None = None,
        sort_by: str = "hotness",
        page: int = 1,
        page_size: int = 20,
    ) -> list[KaggleKernel]:
        """List Kaggle kernels/notebooks."""
        params: dict[str, Any] = {
            "sortBy": sort_by,
            "page": page,
            "pageSize": page_size,
        }
        if search:
            params["search"] = search
        if user:
            params["user"] = user
        if dataset:
            params["dataset"] = dataset
        if competition:
            params["competition"] = competition

        resp = self._request("GET", "kernels/list", params=params, require_auth=True)
        items = resp.json()
        if not isinstance(items, list):
            return []
        return [
            KaggleKernel(
                ref=str(k.get("ref", "")),
                title=str(k.get("title") or k.get("ref") or ""),
                author=str(k.get("author") or ""),
                language=str(k.get("language") or ""),
                kernel_type=str(k.get("kernelType") or ""),
                last_run_time=str(k.get("lastRunTime") or ""),
                total_votes=k.get("totalVotes"),
                url=f"https://www.kaggle.com/code/{k.get('ref')}" if k.get("ref") else "",
            )
            for k in items
            if isinstance(k, dict)
        ]

    def pull_kernel(self, kernel_ref: str, dest_dir: Path | str | None = None) -> dict[str, Any]:
        """Pull a Kaggle kernel's source code and metadata into `dest_dir`."""
        owner, slug = _parse_ref(kernel_ref)
        resp = self._request(
            "GET",
            "kernels/pull",
            params={"userName": owner, "kernelSlug": slug},
            require_auth=True,
        )
        payload = resp.json()
        target_dir = (
            Path(dest_dir).expanduser().resolve()
            if dest_dir
            else (
                get_datasets_dir(workspace_dir=self.workspace_dir)
                / "kaggle"
                / "kernels"
                / sanitize_dataset_slug(kernel_ref)
            )
        )
        target_dir.mkdir(parents=True, exist_ok=True)

        blob = payload.get("blob", {}) if isinstance(payload, dict) else {}
        meta = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        source = blob.get("source", "")
        kernel_type = str(meta.get("kernelType") or blob.get("kernelType") or "script").lower()
        language = str(meta.get("language") or blob.get("language") or "python").lower()

        ext = ".ipynb" if kernel_type == "notebook" else (".r" if language == "r" else ".py")
        code_file = target_dir / f"{slug}{ext}"
        code_file.write_text(source, encoding="utf-8")

        meta_out = {
            "id": f"{owner}/{slug}",
            "title": meta.get("title", slug),
            "code_file": code_file.name,
            "language": language,
            "kernel_type": kernel_type,
            "is_private": meta.get("isPrivate", True),
            "enable_gpu": meta.get("enableGpu", False),
            "enable_internet": meta.get("enableInternet", True),
            "dataset_sources": meta.get("datasetDataSources", []),
            "competition_sources": meta.get("competitionDataSources", []),
            "kernel_sources": meta.get("kernelDataSources", []),
        }
        (target_dir / "kernel-metadata.json").write_text(json.dumps(meta_out, indent=2) + "\n", encoding="utf-8")

        return {
            "kernel_ref": f"{owner}/{slug}",
            "local_dir": str(target_dir),
            "code_file": str(code_file),
            "metadata_file": str(target_dir / "kernel-metadata.json"),
        }

    def push_kernel(self, folder: Path | str) -> dict[str, Any]:
        """Push a local kernel folder (containing `kernel-metadata.json`) to Kaggle and trigger execution."""
        src_dir = Path(folder).expanduser().resolve()
        meta_path = src_dir / "kernel-metadata.json"
        if not meta_path.is_file():
            raise FileNotFoundError(f"kernel-metadata.json not found in {src_dir}")

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        code_file_name = meta.get("code_file")
        if not code_file_name:
            raise ValueError("kernel-metadata.json must specify 'code_file'.")
        code_path = src_dir / code_file_name
        if not code_path.is_file():
            raise FileNotFoundError(f"Kernel code file not found: {code_path}")

        kernel_id = str(meta.get("id", ""))
        owner, slug = _parse_ref(kernel_id) if "/" in kernel_id else (str(self.creds.get("username") or ""), kernel_id)
        if not owner or not slug:
            raise ValueError("kernel-metadata.json must specify 'id' as 'owner/slug'.")

        body = {
            "id": f"{owner}/{slug}",
            "slug": f"{owner}/{slug}",
            "newTitle": meta.get("title", slug),
            "text": code_path.read_text(encoding="utf-8"),
            "language": meta.get("language", "python"),
            "kernelType": meta.get("kernel_type", "notebook" if code_path.suffix == ".ipynb" else "script"),
            "isPrivate": bool(meta.get("is_private", True)),
            "enableGpu": bool(meta.get("enable_gpu", False)),
            "enableTpu": bool(meta.get("enable_tpu", False)),
            "enableInternet": bool(meta.get("enable_internet", True)),
            "datasetDataSources": meta.get("dataset_sources", []),
            "competitionDataSources": meta.get("competition_sources", []),
            "kernelDataSources": meta.get("kernel_sources", []),
        }
        resp = self._request("POST", "kernels/push", json_body=body, require_auth=True)
        return resp.json()

    def kernel_status(self, kernel_ref: str) -> dict[str, Any]:
        """Check the execution status of a Kaggle kernel."""
        owner, slug = _parse_ref(kernel_ref)
        resp = self._request(
            "GET",
            "kernels/status",
            params={"userName": owner, "kernelSlug": slug},
            require_auth=True,
        )
        return resp.json()

    def kernel_output(self, kernel_ref: str, dest_dir: Path | str | None = None) -> dict[str, Any]:
        """Download output files and logs of a completed Kaggle kernel."""
        owner, slug = _parse_ref(kernel_ref)
        resp = self._request(
            "GET",
            "kernels/output",
            params={"userName": owner, "kernelSlug": slug},
            require_auth=True,
        )
        payload = resp.json()
        target_dir = (
            Path(dest_dir).expanduser().resolve()
            if dest_dir
            else (
                get_datasets_dir(workspace_dir=self.workspace_dir)
                / "kaggle"
                / "kernel_outputs"
                / sanitize_dataset_slug(kernel_ref)
            )
        )
        target_dir.mkdir(parents=True, exist_ok=True)

        downloaded: list[str] = []
        log_text = payload.get("log")
        if log_text:
            log_path = target_dir / "kernel.log"
            log_path.write_text(str(log_text), encoding="utf-8")
            downloaded.append("kernel.log")

        for f in payload.get("files", []):
            if isinstance(f, dict) and f.get("url") and f.get("fileName"):
                file_resp = self.session.get(f["url"], stream=True, timeout=self.timeout)
                if file_resp.status_code < 400:
                    out_path = target_dir / Path(f["fileName"]).name
                    self._download_stream(file_resp, out_path)
                    downloaded.append(out_path.name)

        return {
            "kernel_ref": f"{owner}/{slug}",
            "output_dir": str(target_dir),
            "files": downloaded,
        }
