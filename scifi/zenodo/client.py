"""
Authenticated Zenodo Deposit & Record API Client for SciFi.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

from scifi.config import resolve_config
from scifi.zenodo.models import ZenodoDeposition, ZenodoFile, ZenodoPushResult

ZENODO_PROD_API = "https://zenodo.org/api"
ZENODO_SANDBOX_API = "https://sandbox.zenodo.org/api"


def _parse_deposition(payload: dict[str, Any]) -> ZenodoDeposition:
    """Normalize a Zenodo API deposition JSON payload into ZenodoDeposition."""
    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    links = payload.get("links") if isinstance(payload.get("links"), dict) else {}
    prereserved = meta.get("prereserve_doi")
    prereserved_doi = str(prereserved.get("doi")) if isinstance(prereserved, dict) and prereserved.get("doi") else None

    raw_files = payload.get("files") if isinstance(payload.get("files"), list) else []
    files = [
        ZenodoFile(
            id=str(f.get("id")) if f.get("id") is not None else None,
            filename=str(f.get("filename") or f.get("key") or ""),
            filesize=f.get("filesize") if f.get("filesize") is not None else f.get("size"),
            checksum=str(f.get("checksum")) if f.get("checksum") else None,
            download_url=(
                str((f.get("links") or {}).get("download") or (f.get("links") or {}).get("self"))
                if isinstance(f.get("links"), dict)
                and ((f.get("links") or {}).get("download") or (f.get("links") or {}).get("self"))
                else None
            ),
        )
        for f in raw_files
        if isinstance(f, dict)
    ]

    creators = [c for c in (meta.get("creators") or []) if isinstance(c, dict)]
    keywords = [str(k) for k in (meta.get("keywords") or []) if isinstance(k, str)]
    lic = meta.get("license")
    if isinstance(lic, dict):
        lic = lic.get("id")

    return ZenodoDeposition(
        id=int(payload.get("id", 0)),
        title=str(meta.get("title") or payload.get("title") or f"Deposition {payload.get('id', '')}"),
        state=str(payload.get("state") or "unsubmitted"),
        submitted=bool(payload.get("submitted", False)),
        doi=str(payload["doi"]) if payload.get("doi") else None,
        prereserved_doi=prereserved_doi,
        conceptrecid=str(payload["conceptrecid"]) if payload.get("conceptrecid") else None,
        created=str(payload["created"]) if payload.get("created") else None,
        modified=str(payload["modified"]) if payload.get("modified") else None,
        html_url=str(links["html"]) if links.get("html") else None,
        bucket_url=str(links["bucket"]) if links.get("bucket") else None,
        upload_type=str(meta["upload_type"]) if meta.get("upload_type") else None,
        description=str(meta["description"]) if meta.get("description") else None,
        creators=creators,
        keywords=keywords,
        license=str(lic) if lic else None,
        files=files,
    )


def normalize_creators(creators: list[str | dict[str, Any]] | str | None) -> list[dict[str, Any]]:
    """Convert creator names or dicts into Zenodo metadata creator objects."""
    if not creators:
        return []
    if isinstance(creators, str):
        items: list[str | dict[str, Any]] = [c.strip() for c in creators.split(";") if c.strip()]
        if (
            len(items) == 1
            and "," in creators
            and not any(part.strip().count(" ") == 0 for part in creators.split(","))
        ):
            items = [c.strip() for c in creators.split(",") if c.strip()]
    else:
        items = list(creators)

    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            if item.get("name"):
                out.append(dict(item))
        elif isinstance(item, str) and item.strip():
            out.append({"name": item.strip()})
    return out


class ZenodoDepositClient:
    """Client for managing authenticated Zenodo depositions, files, and DOIs."""

    def __init__(
        self,
        token: str | None = None,
        sandbox: bool = False,
        workspace_dir: Path | str | None = None,
        timeout: int = 60,
        session: requests.Session | None = None,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.sandbox = sandbox
        self.api_base = ZENODO_SANDBOX_API if sandbox else ZENODO_PROD_API
        self.timeout = timeout
        self.session = session or requests.Session()
        cfg = resolve_config(workspace_dir=workspace_dir)
        self.token = token or os.environ.get("ZENODO_TOKEN") or cfg.zenodo_token

    def _headers(self, json_content: bool = True) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if json_content:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _require_token(self) -> str:
        if not self.token:
            raise RuntimeError(
                "Zenodo API token is not configured. "
                "Set it with `sf config set zenodo-token <TOKEN>` or the ZENODO_TOKEN environment variable."
            )
        return self.token

    @staticmethod
    def _raise_for_status(resp: requests.Response) -> None:
        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            detail = ""
            try:
                body = resp.json()
                if isinstance(body, dict) and body.get("message"):
                    detail = f" ({body['message']})"
            except Exception:
                pass
            raise requests.HTTPError(f"{exc}{detail}", response=resp) from exc

    def status(self) -> dict[str, Any]:
        """Check Zenodo token configuration and verify API connectivity."""
        configured = bool(self.token)
        info: dict[str, Any] = {
            "configured": configured,
            "connected": False,
            "sandbox": self.sandbox,
            "api_base": self.api_base,
            "deposition_count_sample": 0,
        }
        if not configured:
            info["error"] = "No Zenodo token configured. Run `sf config set zenodo-token <TOKEN>` or set ZENODO_TOKEN."
            return info

        try:
            resp = self.session.get(
                f"{self.api_base}/deposit/depositions",
                params={"size": 1},
                headers=self._headers(json_content=False),
                timeout=self.timeout,
            )
            self._raise_for_status(resp)
            data = resp.json()
            info["connected"] = True
            info["deposition_count_sample"] = len(data) if isinstance(data, list) else 0
        except Exception as exc:
            info["error"] = str(exc)
        return info

    def list_depositions(
        self,
        status: str | None = None,
        size: int = 20,
        query: str | None = None,
    ) -> list[ZenodoDeposition]:
        """List depositions belonging to the authenticated Zenodo account."""
        self._require_token()
        params: dict[str, Any] = {"size": size}
        if status:
            params["status"] = status
        if query:
            params["q"] = query

        resp = self.session.get(
            f"{self.api_base}/deposit/depositions",
            params=params,
            headers=self._headers(json_content=False),
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        items = resp.json()
        if not isinstance(items, list):
            return []
        return [_parse_deposition(item) for item in items if isinstance(item, dict)]

    def get_deposition(self, deposition_id: int | str) -> ZenodoDeposition:
        """Fetch a single deposition by ID."""
        self._require_token()
        resp = self.session.get(
            f"{self.api_base}/deposit/depositions/{deposition_id}",
            headers=self._headers(json_content=False),
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return _parse_deposition(resp.json())

    def create_deposition(
        self,
        title: str | None = None,
        upload_type: str = "software",
        description: str | None = None,
        creators: list[str | dict[str, Any]] | str | None = None,
        keywords: list[str] | None = None,
        license_id: str | None = None,
        prereserve_doi: bool = True,
        extra_metadata: dict[str, Any] | None = None,
    ) -> ZenodoDeposition:
        """Create a new Zenodo draft deposition."""
        self._require_token()
        metadata: dict[str, Any] = {}
        if title:
            metadata["title"] = title
        if upload_type:
            metadata["upload_type"] = upload_type
        if description:
            metadata["description"] = description
        parsed_creators = normalize_creators(creators)
        if parsed_creators:
            metadata["creators"] = parsed_creators
        if keywords:
            metadata["keywords"] = [str(k).strip() for k in keywords if str(k).strip()]
        if license_id:
            metadata["license"] = license_id
        if prereserve_doi:
            metadata["prereserve_doi"] = True
        if extra_metadata:
            metadata.update(extra_metadata)

        body: dict[str, Any] = {"metadata": metadata} if metadata else {}
        resp = self.session.post(
            f"{self.api_base}/deposit/depositions",
            json=body,
            headers=self._headers(),
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return _parse_deposition(resp.json())

    def update_metadata(
        self,
        deposition_id: int | str,
        metadata: dict[str, Any],
        merge_existing: bool = True,
    ) -> ZenodoDeposition:
        """Update metadata on an existing draft deposition."""
        self._require_token()
        merged = dict(metadata)
        if merge_existing:
            current = self.get_deposition(deposition_id)
            base: dict[str, Any] = {}
            if current.title:
                base["title"] = current.title
            if current.upload_type:
                base["upload_type"] = current.upload_type
            if current.description:
                base["description"] = current.description
            if current.creators:
                base["creators"] = current.creators
            if current.keywords:
                base["keywords"] = current.keywords
            if current.license:
                base["license"] = current.license
            base.update(merged)
            merged = base

        resp = self.session.put(
            f"{self.api_base}/deposit/depositions/{deposition_id}",
            json={"metadata": merged},
            headers=self._headers(),
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return _parse_deposition(resp.json())

    def upload_file(
        self,
        deposition_id: int | str,
        file_path: Path | str,
        remote_name: str | None = None,
    ) -> ZenodoFile:
        """Upload a local file to a draft Zenodo deposition (via bucket API or files endpoint)."""
        self._require_token()
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"File not found for Zenodo upload: {path}")

        target_name = remote_name or path.name
        dep = self.get_deposition(deposition_id)

        if dep.bucket_url:
            with path.open("rb") as fh:
                resp = self.session.put(
                    f"{dep.bucket_url.rstrip('/')}/{target_name}",
                    data=fh,
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=max(self.timeout, 300),
                )
            self._raise_for_status(resp)
            data = resp.json()
            return ZenodoFile(
                id=str(data.get("version_id") or data.get("id") or "") or None,
                filename=str(data.get("key") or target_name),
                filesize=data.get("size"),
                checksum=str(data.get("checksum")) if data.get("checksum") else None,
                download_url=(data.get("links") or {}).get("self") if isinstance(data.get("links"), dict) else None,
            )

        with path.open("rb") as fh:
            resp = self.session.post(
                f"{self.api_base}/deposit/depositions/{deposition_id}/files",
                data={"name": target_name},
                files={"file": (target_name, fh)},
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=max(self.timeout, 300),
            )
        self._raise_for_status(resp)
        data = resp.json()
        return ZenodoFile(
            id=str(data.get("id")) if data.get("id") is not None else None,
            filename=str(data.get("filename") or target_name),
            filesize=data.get("filesize"),
            checksum=str(data.get("checksum")) if data.get("checksum") else None,
            download_url=(data.get("links") or {}).get("download") if isinstance(data.get("links"), dict) else None,
        )

    def delete_file(self, deposition_id: int | str, file_id: str) -> bool:
        """Delete a file from an unsubmitted draft deposition."""
        self._require_token()
        resp = self.session.delete(
            f"{self.api_base}/deposit/depositions/{deposition_id}/files/{file_id}",
            headers=self._headers(json_content=False),
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return True

    def reserve_doi(self, deposition_id: int | str) -> dict[str, Any]:
        """Pre-reserve a DOI on a draft deposition and return DOI details."""
        dep = self.get_deposition(deposition_id)
        if dep.prereserved_doi or dep.doi:
            return {
                "deposition_id": dep.id,
                "prereserved_doi": dep.prereserved_doi,
                "doi": dep.doi,
            }
        updated = self.update_metadata(deposition_id, {"prereserve_doi": True}, merge_existing=True)
        return {
            "deposition_id": updated.id,
            "prereserved_doi": updated.prereserved_doi,
            "doi": updated.doi,
        }

    def publish(self, deposition_id: int | str) -> ZenodoDeposition:
        """Publish a draft deposition, minting a permanent DOI."""
        self._require_token()
        resp = self.session.post(
            f"{self.api_base}/deposit/depositions/{deposition_id}/actions/publish",
            headers=self._headers(json_content=False),
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return _parse_deposition(resp.json())

    def new_version(self, deposition_id: int | str) -> ZenodoDeposition:
        """Create a new draft version of an existing published deposition."""
        self._require_token()
        resp = self.session.post(
            f"{self.api_base}/deposit/depositions/{deposition_id}/actions/newversion",
            headers=self._headers(json_content=False),
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return _parse_deposition(resp.json())

    def push_submission_artifacts(
        self,
        files: list[Path | str],
        deposition_id: int | str | None = None,
        title: str | None = None,
        description: str | None = None,
        creators: list[str | dict[str, Any]] | str | None = None,
        upload_type: str = "software",
        keywords: list[str] | None = None,
        license_id: str | None = None,
        publish: bool = False,
    ) -> ZenodoPushResult:
        """
        Upload SciFi submission artifacts (e.g., anonymous code ZIP, bundle files)
        to an existing or newly created Zenodo deposition.
        """
        self._require_token()
        if deposition_id is not None:
            dep = self.get_deposition(deposition_id)
        else:
            dep = self.create_deposition(
                title=title or "SciFi Submission Artifacts",
                upload_type=upload_type,
                description=description or "Supplementary code and submission artifacts packaged by SciFi.",
                creators=creators,
                keywords=keywords,
                license_id=license_id,
                prereserve_doi=True,
            )

        uploaded: list[str] = []
        for f in files:
            zf = self.upload_file(dep.id, f)
            uploaded.append(zf.filename)

        if publish:
            dep = self.publish(dep.id)
        else:
            dep = self.get_deposition(dep.id)

        return ZenodoPushResult(
            deposition_id=dep.id,
            title=dep.title,
            html_url=dep.html_url,
            prereserved_doi=dep.prereserved_doi,
            doi=dep.doi,
            published=dep.submitted,
            uploaded_files=uploaded,
        )
