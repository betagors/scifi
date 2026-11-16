"""
Local HTTP Note and Tag Dispatcher for Zotero.
Communicates with Zotero local API on port 23119 with in-place deduplicating
upserts (PATCH) and persistent offline staging.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import requests

from scifi.env import is_zotero_port_open
from scifi.literature.zotero.models import ZoteroAuditCard

_AUTH_LOCK = threading.Lock()
_LAST_AUTH_FAILURE_TS: float = 0.0
_AUTH_RETRY_COOLDOWN_S: float = 30.0

SCIFI_STATUS_TAGS = {
    "#scifi-audited",
    "#scifi-verified",
    "#unstated-assumption",
    "#retraction-or-concern",
    "#benchmark-sota",
}


class ZoteroLocalWriter:
    """
    Dispatcher for child notes, tags, and smart searches to local Zotero server.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 23119,
        api_key: str | None = None,
        stage_file: str | Path | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.api_key = api_key
        self.base_url = f"http://{host}:{port}/api/users/0"
        self.stage_file = Path(stage_file) if stage_file else Path(".scifi/zotero_write_queue.json")
        self._server_id: str | None = None

    def is_server_available(self) -> bool:
        """Check if Zotero local server is responding."""
        return is_zotero_port_open(self.host, self.port, timeout=0.5)

    def _ensure_session(self, require_auth: bool = True) -> None:
        """Ensure Zotero-Server-ID and local API key are discovered and initialized."""
        global _LAST_AUTH_FAILURE_TS
        if not self.is_server_available():
            return

        if not self._server_id:
            try:
                resp = requests.get(f"{self.base_url}/collections", timeout=2)
                self._server_id = resp.headers.get("Zotero-Server-ID")
            except Exception:
                self._server_id = None

        if self.api_key:
            return

        try:
            from scifi.config import load_global_config, set_global_config_value

            g_cfg = load_global_config()
            cached_key = g_cfg.get("zotero_local_api_key")
            if cached_key:
                self.api_key = cached_key
                return

            if not require_auth:
                return

            with _AUTH_LOCK:
                # Re-check config inside lock in case another thread just completed authorization.
                cached_key = load_global_config().get("zotero_local_api_key")
                if cached_key:
                    self.api_key = cached_key
                    return

                if time.monotonic() - _LAST_AUTH_FAILURE_TS < _AUTH_RETRY_COOLDOWN_S:
                    return

                auth_headers = {"Content-Type": "application/json"}
                if self._server_id:
                    auth_headers["Zotero-Server-ID"] = self._server_id
                auth_resp = requests.post(
                    f"http://{self.host}:{self.port}/api/local/authorize",
                    headers=auth_headers,
                    json={"appName": "SciFi", "purpose": "Manage project literature collections"},
                    timeout=60,
                )
                if auth_resp.status_code == 200:
                    key = auth_resp.json().get("key")
                    if key:
                        self.api_key = key
                        try:
                            set_global_config_value("zotero_local_api_key", key)
                        except Exception:
                            pass
                        return
                _LAST_AUTH_FAILURE_TS = time.monotonic()
        except Exception:
            _LAST_AUTH_FAILURE_TS = time.monotonic()

    def _headers(self, version: int | None = None, require_auth: bool = False) -> dict[str, str]:
        self._ensure_session(require_auth=require_auth)
        headers = {
            "Content-Type": "application/json",
            "Zotero-API-Version": "3",
        }
        if self._server_id:
            headers["Zotero-Server-ID"] = self._server_id
        if self.api_key:
            headers["Zotero-API-Key"] = self.api_key
        if version is not None:
            headers["If-Unmodified-Since-Version"] = str(version)
        return headers

    def _load_staged_queue(self) -> list[dict[str, Any]]:
        """Read the offline write queue safely."""
        if not self.stage_file.is_file():
            return []
        try:
            data = json.loads(self.stage_file.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _stage_write(self, mutation: dict[str, Any]) -> None:
        """Persist an unwritten mutation to the offline queue."""
        self.stage_file.parent.mkdir(parents=True, exist_ok=True)
        queue = self._load_staged_queue()
        if mutation not in queue:
            queue.append(mutation)
            self.stage_file.write_text(json.dumps(queue, indent=2), encoding="utf-8")

    def pending_count(self) -> int:
        """Return the number of staged mutations waiting to be flushed."""
        if not self.stage_file.is_file():
            return 0
        try:
            queue = json.loads(self.stage_file.read_text(encoding="utf-8"))
            return len(queue) if isinstance(queue, list) else 0
        except Exception:
            return 0

    def format_audit_card_html(self, card: ZoteroAuditCard) -> str:
        """Generate formatted HTML for a SciFi audit card child note."""
        lines = [
            '<div class="scifi-audit-card" data-scifi-version="1.0">',
            "<h3>SciFi Scientific Audit Card</h3>",
            f"<p><strong>Primary Contribution:</strong> {card.contribution}</p>",
        ]

        if card.assumptions_flagged:
            lines.append(
                f"<details open><summary><strong>Flagged Assumptions ({len(card.assumptions_flagged)})</strong></summary><ul>"
            )
            for a in card.assumptions_flagged:
                lines.append(f"<li>⚠️ {a}</li>")
            lines.append("</ul></details>")
        else:
            lines.append("<p><em>No unstated assumptions flagged.</em></p>")

        if card.benchmarks_extracted:
            lines.append(
                f"<details open><summary><strong>Extracted SOTA Benchmarks ({len(card.benchmarks_extracted)})</strong></summary><ul>"
            )
            for b in card.benchmarks_extracted:
                metric = b.get("metric", "Metric")
                val = b.get("value", "")
                lines.append(f"<li>📊 <strong>{metric}:</strong> {val}</li>")
            lines.append("</ul></details>")

        math_status = "✅ Verified" if card.math_verified else "⚪ Unaudited / Not applicable"
        lines.append(f"<p><strong>Symbolic Math Verification:</strong> {math_status}</p>")
        lines.append(f"<p><strong>Integrity & Retraction Check:</strong> {card.retraction_status}</p>")
        lines.append("<p><small>Audited autonomously by SciFi.</small></p>")
        lines.append("</div>")
        return "\n".join(lines)

    def push_audit_card_note(self, item_key: str, card: ZoteroAuditCard) -> dict[str, Any]:
        """
        Push or in-place upsert a SciFi audit card child note under a parent item.
        """
        html_content = self.format_audit_card_html(card)

        if not self.is_server_available():
            self._stage_write(
                {
                    "type": "audit_note",
                    "item_key": item_key,
                    "card": {
                        "contribution": card.contribution,
                        "assumptions_flagged": card.assumptions_flagged,
                        "benchmarks_extracted": card.benchmarks_extracted,
                        "math_verified": card.math_verified,
                        "retraction_status": card.retraction_status,
                    },
                }
            )
            return {"status": "STAGED", "message": "Zotero is offline; audit note staged in local queue."}

        # Check existing child notes
        try:
            resp = requests.get(f"{self.base_url}/items/{item_key}/children", headers=self._headers(), timeout=3)
            if resp.status_code == 200:
                children = resp.json()
                for child in children:
                    c_data = child.get("data", child)
                    if c_data.get("itemType") == "note" and "scifi-audit-card" in c_data.get("note", ""):
                        note_key = child.get("key", c_data.get("key"))
                        ver = child.get("version", c_data.get("version"))
                        patch_payload = {"note": html_content}
                        patch_resp = requests.patch(
                            f"{self.base_url}/items/{note_key}",
                            headers=self._headers(version=ver, require_auth=True),
                            json=patch_payload,
                            timeout=3,
                        )
                        if patch_resp.status_code in (200, 204):
                            return {"status": "UPDATED", "note_key": note_key}

            # Create new child note
            post_payload: list[dict[str, Any]] = [
                {
                    "itemType": "note",
                    "parentItem": item_key,
                    "note": html_content,
                    "tags": [{"tag": "#scifi-audited"}],
                }
            ]
            post_resp = requests.post(
                f"{self.base_url}/items",
                headers=self._headers(require_auth=True),
                json=post_payload,
                timeout=3,
            )
            if post_resp.status_code in (200, 201):
                return {"status": "CREATED", "response": post_resp.json() if post_resp.text else {}}
            return {"status": "ERROR", "code": post_resp.status_code, "body": post_resp.text}
        except Exception as e:
            self._stage_write(
                {
                    "type": "audit_note",
                    "item_key": item_key,
                    "card": {
                        "contribution": card.contribution,
                        "assumptions_flagged": card.assumptions_flagged,
                        "benchmarks_extracted": card.benchmarks_extracted,
                        "math_verified": card.math_verified,
                        "retraction_status": card.retraction_status,
                    },
                }
            )
            return {"status": "STAGED", "error": str(e)}

    def apply_tags(self, item_key: str, tags: list[str], replace_scifi_tags: bool = True) -> dict[str, Any]:
        """
        Apply tags to parent item while preserving user-authored tags.
        """
        if not self.is_server_available():
            self._stage_write(
                {
                    "type": "tags",
                    "item_key": item_key,
                    "tags": tags,
                    "replace_scifi_tags": replace_scifi_tags,
                }
            )
            return {"status": "STAGED", "message": "Zotero is offline; tag mutation staged in local queue."}

        try:
            get_resp = requests.get(f"{self.base_url}/items/{item_key}", headers=self._headers(), timeout=3)
            if get_resp.status_code != 200:
                return {"status": "ERROR", "code": get_resp.status_code}

            item_json = get_resp.json()
            data = item_json.get("data", item_json)
            version = item_json.get("version", data.get("version"))
            existing_tags = data.get("tags", [])

            # Filter tags
            merged_tags: list[dict[str, str]] = []
            for t_obj in existing_tags:
                tag_name = t_obj.get("tag", "")
                if replace_scifi_tags and tag_name in SCIFI_STATUS_TAGS:
                    continue
                merged_tags.append(t_obj)

            # Add new tags
            existing_names = {t.get("tag") for t in merged_tags}
            for new_t in tags:
                if new_t not in existing_names:
                    merged_tags.append({"tag": new_t})

            patch_resp = requests.patch(
                f"{self.base_url}/items/{item_key}",
                headers=self._headers(version=version, require_auth=True),
                json={"tags": merged_tags},
                timeout=3,
            )
            if patch_resp.status_code in (200, 204):
                return {"status": "SUCCESS", "tags": [t["tag"] for t in merged_tags]}
            return {"status": "ERROR", "code": patch_resp.status_code}
        except Exception as e:
            self._stage_write(
                {
                    "type": "tags",
                    "item_key": item_key,
                    "tags": tags,
                    "replace_scifi_tags": replace_scifi_tags,
                }
            )
            return {"status": "STAGED", "error": str(e)}

    def create_collection(self, name: str, parent_key: str | None = None) -> dict[str, Any]:
        """
        Create a new collection in Zotero (via local HTTP API or offline queue).
        """
        if not self.is_server_available():
            self._stage_write(
                {
                    "type": "create_collection",
                    "name": name,
                    "parent_key": parent_key,
                }
            )
            return {"status": "STAGED", "message": f"Zotero is offline; collection '{name}' creation staged in queue."}

        try:
            existing_key = self.get_collection_key(name)
            if existing_key:
                return {"status": "EXISTS", "collection_key": existing_key}
            payload = [{"name": name}]
            if parent_key:
                payload[0]["parentCollection"] = parent_key
            resp = requests.post(
                f"{self.base_url}/collections",
                headers=self._headers(require_auth=True),
                json=payload,
                timeout=3,
            )
            if resp.status_code in (200, 201):
                return {"status": "CREATED", "response": resp.json() if resp.text else {}}
            self._stage_write(
                {
                    "type": "create_collection",
                    "name": name,
                    "parent_key": parent_key,
                }
            )
            return {"status": "STAGED", "code": resp.status_code, "body": resp.text}
        except Exception as e:
            self._stage_write(
                {
                    "type": "create_collection",
                    "name": name,
                    "parent_key": parent_key,
                }
            )
            return {"status": "STAGED", "error": str(e)}

    def list_collections_live(self) -> list[dict[str, str]]:
        """List collections from Zotero's live local HTTP API (includes uncheckpointed WAL writes)."""
        try:
            resp = requests.get(f"{self.base_url}/collections?limit=500", headers=self._headers(), timeout=5)
            if resp.status_code == 200:
                out: list[dict[str, str]] = []
                for c in resp.json():
                    data = c.get("data", {})
                    name = data.get("name", "")
                    key = data.get("key", "")
                    if name and key:
                        out.append({"key": key, "name": name})
                return out
        except Exception:
            pass
        return []

    def get_collection_key(self, name: str) -> str | None:
        """Resolve a collection key by name (case-insensitive) via the local API."""
        clean_name = name.strip().lower()
        for col in self.list_collections_live():
            if col["name"].strip().lower() == clean_name:
                return col["key"]
        return None

    def get_collection_items_live(self, collection_key: str) -> list[dict[str, Any]]:
        """Retrieve item data dicts in a collection via the live local HTTP API."""
        try:
            resp = requests.get(
                f"{self.base_url}/collections/{collection_key}/items?limit=500",
                headers=self._headers(),
                timeout=5,
            )
            if resp.status_code == 200:
                items = []
                for entry in resp.json():
                    data = entry.get("data", {})
                    if data.get("itemType") not in ("attachment", "note", "annotation"):
                        items.append(data)
                return items
        except Exception:
            pass
        return []

    def add_items_to_collection(self, collection_key: str, item_keys: list[str]) -> int:
        """Add existing library items to a collection (PATCH preserving other memberships)."""
        added = 0
        for key in item_keys:
            try:
                g = requests.get(f"{self.base_url}/items/{key}", headers=self._headers(), timeout=5)
                if g.status_code != 200:
                    continue
                data = g.json().get("data", {})
                cols = list(data.get("collections", []))
                if collection_key in cols:
                    added += 1
                    continue
                cols.append(collection_key)
                p = requests.patch(
                    f"{self.base_url}/items/{key}",
                    headers=self._headers(version=data.get("version"), require_auth=True),
                    json={"collections": cols},
                    timeout=5,
                )
                if p.status_code in (200, 204):
                    added += 1
            except Exception:
                continue
        return added

    def _normalize_doi(self, v: str | None) -> str:
        import re

        return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", (v or "").strip(), flags=re.IGNORECASE).lower()

    def _normalize_title(self, v: str | None) -> str:
        import re

        return re.sub(r"[^a-z0-9]", "", (v or "").lower())

    def find_item_key_by_doi_or_title(
        self,
        doi: str | None = None,
        title: str | None = None,
        collection_key: str | None = None,
    ) -> str | None:
        """Find an existing top-level Zotero item key by DOI or normalized title."""
        if not self.is_server_available():
            return None
        target_doi = self._normalize_doi(doi)
        target_title = self._normalize_title(title)
        if not target_doi and len(target_title) < 6:
            return None

        if collection_key:
            items = self.get_collection_items_live(collection_key)
        else:
            try:
                resp = requests.get(
                    f"{self.base_url}/items/top?limit=200",
                    headers=self._headers(require_auth=False),
                    timeout=10,
                )
                if resp.status_code != 200:
                    return None
                items = [it.get("data", it) for it in resp.json() if isinstance(it, dict)]
            except Exception:
                return None

        for it in items:
            if target_doi and self._normalize_doi(it.get("DOI")) == target_doi:
                return it.get("key")
            if len(target_title) >= 6 and self._normalize_title(it.get("title")) == target_title:
                return it.get("key")
        return None

    def attach_linked_pdf(
        self,
        parent_key: str,
        pdf_path: str | Path,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Attach a local PDF as a linked_file child attachment on an existing Zotero item."""
        resolved_pdf = Path(pdf_path).resolve()
        att_title = title or resolved_pdf.name

        if not self.is_server_available():
            self._stage_write(
                {
                    "type": "attach_pdf",
                    "item_key": parent_key,
                    "pdf_path": str(resolved_pdf),
                    "title": att_title,
                }
            )
            return {"status": "STAGED", "parent_key": parent_key, "pdf_path": str(resolved_pdf)}

        # Avoid duplicate PDF attachment with the same path or title
        try:
            children_resp = requests.get(
                f"{self.base_url}/items/{parent_key}/children",
                headers=self._headers(require_auth=False),
                timeout=10,
            )
            if children_resp.status_code == 200:
                for child in children_resp.json():
                    cdata = child.get("data", child)
                    if cdata.get("itemType") == "attachment" and (
                        cdata.get("path") == str(resolved_pdf) or cdata.get("contentType") == "application/pdf"
                    ):
                        return {"status": "EXISTS", "parent_key": parent_key, "attachment_key": cdata.get("key")}
        except Exception:
            pass

        payload = [
            {
                "itemType": "attachment",
                "parentItem": parent_key,
                "linkMode": "linked_file",
                "title": att_title,
                "path": str(resolved_pdf),
                "contentType": "application/pdf",
            }
        ]
        try:
            resp = requests.post(
                f"{self.base_url}/items",
                headers=self._headers(require_auth=True),
                json=payload,
                timeout=15,
            )
            if resp.status_code in (200, 201):
                succ = resp.json().get("successful", {})
                if succ:
                    first = next(iter(succ.values()))
                    return {
                        "status": "CREATED",
                        "parent_key": parent_key,
                        "attachment_key": first.get("key") or first.get("data", {}).get("key"),
                    }
            self._stage_write(
                {
                    "type": "attach_pdf",
                    "item_key": parent_key,
                    "pdf_path": str(resolved_pdf),
                    "title": att_title,
                }
            )
            return {"status": "STAGED", "code": resp.status_code, "parent_key": parent_key}
        except Exception as e:
            self._stage_write(
                {
                    "type": "attach_pdf",
                    "item_key": parent_key,
                    "pdf_path": str(resolved_pdf),
                    "title": att_title,
                }
            )
            return {"status": "STAGED", "error": str(e), "parent_key": parent_key}

    def import_paper_with_pdf(
        self,
        item_payload: dict[str, Any],
        pdf_path: str | Path | None = None,
        collection_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Ensure a paper item exists in the target Zotero collection and attach its PDF.
        Stages cleanly if Zotero is offline.
        """
        resolved_pdf = str(Path(pdf_path).resolve()) if pdf_path else None
        if not self.is_server_available():
            self._stage_write(
                {
                    "type": "import_paper_with_pdf",
                    "item": item_payload,
                    "pdf_path": resolved_pdf,
                    "collection_name": collection_name,
                }
            )
            return {"status": "STAGED", "collection_name": collection_name, "pdf_path": resolved_pdf}

        col_key: str | None = None
        if collection_name:
            col_key = self.get_collection_key(collection_name)
            if not col_key:
                c_res = self.create_collection(collection_name)
                col_key = c_res.get("key") or self.get_collection_key(collection_name)

        parent_key = self.find_item_key_by_doi_or_title(
            doi=item_payload.get("DOI"),
            title=item_payload.get("title"),
            collection_key=col_key,
        )
        if not parent_key:
            # Check library-wide before creating a duplicate
            parent_key = self.find_item_key_by_doi_or_title(
                doi=item_payload.get("DOI"),
                title=item_payload.get("title"),
                collection_key=None,
            )
            if parent_key and col_key:
                self.add_items_to_collection(col_key, [parent_key])

        item_status = "EXISTS"
        if not parent_key:
            payload = dict(item_payload)
            if col_key:
                payload["collections"] = [col_key]
            try:
                resp = requests.post(
                    f"{self.base_url}/items",
                    headers=self._headers(require_auth=True),
                    json=[payload],
                    timeout=15,
                )
                if resp.status_code in (200, 201):
                    succ = resp.json().get("successful", {})
                    if succ:
                        first = next(iter(succ.values()))
                        parent_key = first.get("key") or first.get("data", {}).get("key")
                        item_status = "CREATED"
            except Exception as e:
                self._stage_write(
                    {
                        "type": "import_paper_with_pdf",
                        "item": item_payload,
                        "pdf_path": resolved_pdf,
                        "collection_name": collection_name,
                    }
                )
                return {"status": "STAGED", "error": str(e)}

        if not parent_key:
            self._stage_write(
                {
                    "type": "import_paper_with_pdf",
                    "item": item_payload,
                    "pdf_path": resolved_pdf,
                    "collection_name": collection_name,
                }
            )
            return {"status": "STAGED", "collection_name": collection_name}

        att_res: dict[str, Any] = {"status": "SKIPPED"}
        if resolved_pdf:
            att_res = self.attach_linked_pdf(parent_key, resolved_pdf)

        return {
            "status": "PUSHED",
            "item_status": item_status,
            "item_key": parent_key,
            "collection_key": col_key,
            "attachment": att_res,
        }

    def create_items(self, items: list[dict[str, Any]], collection_key: str) -> int:
        """Create new library items (Zotero item JSON) directly inside a collection, skipping duplicates."""
        live_items = self.get_collection_items_live(collection_key)
        live_dois = {self._normalize_doi(it.get("DOI")) for it in live_items if self._normalize_doi(it.get("DOI"))}
        live_titles = {
            self._normalize_title(it.get("title"))
            for it in live_items
            if len(self._normalize_title(it.get("title"))) >= 6
        }

        deduped: list[dict[str, Any]] = []
        for it in items:
            d = self._normalize_doi(it.get("DOI"))
            t = self._normalize_title(it.get("title"))
            if (d and d in live_dois) or (len(t) >= 6 and t in live_titles):
                continue
            deduped.append(it)
            if d:
                live_dois.add(d)
            if len(t) >= 6:
                live_titles.add(t)

        created = 0
        for i in range(0, len(deduped), 25):
            batch = [dict(it, collections=[collection_key]) for it in deduped[i : i + 25]]
            try:
                resp = requests.post(
                    f"{self.base_url}/items",
                    headers=self._headers(require_auth=True),
                    json=batch,
                    timeout=15,
                )
                if resp.status_code in (200, 201):
                    created += len(resp.json().get("successful", {}))
            except Exception:
                continue
        return created

    def flush_staged_writes(self) -> list[dict[str, Any]]:
        """
        Replay all staged mutations when the Zotero server is available.
        """
        if not self.stage_file.is_file():
            return []
        try:
            queue = json.loads(self.stage_file.read_text(encoding="utf-8"))
        except Exception:
            return []

        if not queue:
            return []

        if not self.is_server_available():
            return []

        results: list[dict[str, Any]] = []
        unprocessed: list[dict[str, Any]] = []

        for item in queue:
            m_type = item.get("type")
            key = item.get("item_key")
            try:
                res = None
                if m_type == "audit_note":
                    c_data = item.get("card", {})
                    card = ZoteroAuditCard(
                        item_key=key,
                        contribution=c_data.get("contribution", ""),
                        assumptions_flagged=c_data.get("assumptions_flagged", []),
                        benchmarks_extracted=c_data.get("benchmarks_extracted", []),
                        math_verified=c_data.get("math_verified", False),
                        retraction_status=c_data.get("retraction_status", "OK"),
                    )
                    res = self.push_audit_card_note(key, card)
                elif m_type in ("tags", "tag"):
                    res = self.apply_tags(
                        key,
                        item.get("tags", []),
                        replace_scifi_tags=item.get("replace_scifi_tags", True),
                    )
                elif m_type == "create_collection":
                    res = self.create_collection(
                        item.get("name", ""),
                        parent_key=item.get("parent_key"),
                    )
                elif m_type == "add_to_collection":
                    col_name = item.get("collection_name", "")
                    col_key = item.get("collection_key") or (self.get_collection_key(col_name) if col_name else None)
                    item_keys = item.get("item_keys", [])
                    if col_key and item_keys:
                        added = self.add_items_to_collection(col_key, item_keys)
                        if added > 0:
                            res = {"status": "SUCCESS", "added": added}
                elif m_type == "create_items":
                    col_name = item.get("collection_name", "")
                    col_key = item.get("collection_key") or (self.get_collection_key(col_name) if col_name else None)
                    items_payload = item.get("items", [])
                    if col_key and items_payload:
                        created = self.create_items(items_payload, col_key)
                        res = {"status": "CREATED" if created > 0 else "EXISTS", "created": created}
                elif m_type == "attach_pdf":
                    pdf_p = item.get("pdf_path")
                    if key and pdf_p:
                        res = self.attach_linked_pdf(key, pdf_p, title=item.get("title"))
                elif m_type == "import_paper_with_pdf":
                    item_payload = item.get("item")
                    if item_payload:
                        res = self.import_paper_with_pdf(
                            item_payload,
                            pdf_path=item.get("pdf_path"),
                            collection_name=item.get("collection_name"),
                        )

                if res and res.get("status") in ("CREATED", "UPDATED", "SUCCESS", "EXISTS", "PUSHED"):
                    results.append(res)
                else:
                    unprocessed.append(item)
            except Exception:
                unprocessed.append(item)

        if unprocessed:
            self.stage_file.write_text(json.dumps(unprocessed, indent=2), encoding="utf-8")
        else:
            self.stage_file.unlink(missing_ok=True)

        return results
