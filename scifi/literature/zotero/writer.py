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

SCIFI_PDF_TAGS = {
    "#scifi-pdf-published",
    "#scifi-pdf-preprint",
    "#scifi-pdf-aam",
    "#scifi-pdf-missing",
}

SCIFI_PUB_STATUS_TAGS = {
    "#scifi-status-published",
    "#scifi-status-preprint",
}

SCIFI_AUDIT_TAGS = {
    "#scifi-audited",
    "#scifi-verified",
    "#unstated-assumption",
    "#retraction-or-concern",
    "#benchmark-sota",
    "#scifi-citation-verified",
    "#scifi-retracted",
    "#scifi-erratum",
    "#scifi-claims-checked",
    "#scifi-kg-digested",
    "#scifi-contradiction",
    "#scifi-claim-disputed",
    "#scifi-abstract-missing",
}

SCIFI_STATUS_TAGS = (
    SCIFI_PDF_TAGS
    | SCIFI_PUB_STATUS_TAGS
    | SCIFI_AUDIT_TAGS
    | {
        "#scifi-reprint-requested",
        "#scifi-ingested",
    }
)


def infer_pdf_provenance_tag(pdf_url: str | None = None, source: str | None = None) -> str:
    """Infer the SciFi PDF provenance tag from a download URL or source."""
    if not pdf_url and not source:
        return "#scifi-pdf-missing"
    combined = f"{pdf_url or ''} {source or ''}".lower()
    if any(host in combined for host in ("arxiv.org", "biorxiv.org", "medrxiv.org", "preprint")):
        return "#scifi-pdf-preprint"
    if "aam" in combined or "accepted manuscript" in combined:
        return "#scifi-pdf-aam"
    return "#scifi-pdf-published"


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
            '<div class="scifi-audit-card" data-scifi-version="2.0">',
            "<h3>SciFi Scientific Audit Card</h3>",
        ]

        if card.pdf_source or card.reprint_status or card.kg_digested_at:
            prov_parts = []
            if card.pdf_source:
                prov_parts.append(f"<strong>PDF Source:</strong> {card.pdf_source}")
            if card.reprint_status:
                prov_parts.append(f"<strong>Reprint Status:</strong> {card.reprint_status}")
            if card.kg_digested_at:
                prov_parts.append(f"<strong>KG Digested:</strong> {card.kg_digested_at}")
            lines.append(f"<p>{' | '.join(prov_parts)}</p>")

        if card.summary:
            lines.append(f"<p><strong>Résumé:</strong> {card.summary}</p>")

        lines.append(f"<p><strong>Primary Contribution:</strong> {card.contribution}</p>")

        if card.authors_info:
            lines.append(
                f"<details open><summary><strong>Authors &amp; Contacts ({len(card.authors_info)})</strong></summary><ul>"
            )
            for auth in card.authors_info:
                name = auth.get("name", "Unknown")
                parts = [f"<strong>{name}</strong>"]
                inst = auth.get("latest_institution") or auth.get("institution")
                if inst:
                    parts.append(f"({inst})")
                orcid = auth.get("orcid")
                if orcid:
                    parts.append(f'ORCID: <a href="https://orcid.org/{orcid}">{orcid}</a>')
                email = auth.get("email")
                if email:
                    parts.append(f"Email: {email}")
                h_idx = auth.get("h_index")
                if h_idx is not None:
                    parts.append(f"h-index: {h_idx}")
                lines.append(f"<li>👤 {' — '.join(parts)}</li>")
            lines.append("</ul></details>")

        if card.methods:
            lines.append(
                f"<details open><summary><strong>Extracted Methods ({len(card.methods)})</strong></summary><ul>"
            )
            for m in card.methods:
                lines.append(f"<li>⚙️ {m}</li>")
            lines.append("</ul></details>")

        if card.claims:
            lines.append(
                f"<details open><summary><strong>Key Claims ({len(card.claims)})</strong></summary><ul>"
            )
            for cl in card.claims:
                lines.append(f"<li>📌 {cl}</li>")
            lines.append("</ul></details>")

        if card.claims_checked:
            lines.append(
                f"<details open><summary><strong>Claim Verification ({len(card.claims_checked)})</strong></summary><ul>"
            )
            for c in card.claims_checked:
                verdict = str(c.get("verdict", "UNCHECKED")).upper()
                icon = "✅" if verdict in ("ENTAILED", "SUPPORTED") else ("⚠️" if "PARTIAL" in verdict else "❌")
                claim_txt = c.get("claim", "")
                evidence = c.get("evidence", "")
                ev_str = f" — <em>{evidence}</em>" if evidence else ""
                lines.append(f"<li>{icon} <strong>[{verdict}]</strong> {claim_txt}{ev_str}</li>")
            lines.append("</ul></details>")

        if card.contradictions:
            lines.append(
                f"<details open><summary><strong>Contradictions / Falsifications ({len(card.contradictions)})</strong></summary><ul>"
            )
            for ctr in card.contradictions:
                lines.append(f"<li>⚡ {ctr}</li>")
            lines.append("</ul></details>")

        if card.assumptions_flagged:
            lines.append(
                f"<details open><summary><strong>Flagged Assumptions ({len(card.assumptions_flagged)})</strong></summary><ul>"
            )
            for a in card.assumptions_flagged:
                lines.append(f"<li>⚠️ {a}</li>")
            lines.append("</ul></details>")
        else:
            lines.append("<p><em>No unstated assumptions flagged.</em></p>")

        if card.gaps:
            lines.append(
                f"<details open><summary><strong>Research Gaps ({len(card.gaps)})</strong></summary><ul>"
            )
            for g in card.gaps:
                lines.append(f"<li>🔍 {g}</li>")
            lines.append("</ul></details>")

        if card.limitations:
            lines.append(
                f"<details open><summary><strong>Limitations &amp; Failure Modes ({len(card.limitations)})</strong></summary><ul>"
            )
            for lim in card.limitations:
                lines.append(f"<li>🔸 {lim}</li>")
            lines.append("</ul></details>")

        if card.benchmarks_extracted:
            lines.append(
                f"<details open><summary><strong>Extracted SOTA Benchmarks ({len(card.benchmarks_extracted)})</strong></summary><ul>"
            )
            for b in card.benchmarks_extracted:
                metric = b.get("metric", "Metric")
                val = b.get("value", "")
                lines.append(f"<li>📊 <strong>{metric}:</strong> {val}</li>")
            lines.append("</ul></details>")

        if card.relevance_notes:
            lines.append(f"<p><strong>AI Project Notes:</strong> {card.relevance_notes}</p>")

        if card.citation_verified is not None:
            cit_status = "✅ Verified" if card.citation_verified else "⚠️ Unverified"
            lines.append(f"<p><strong>Citation Verification:</strong> {cit_status}</p>")

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
                    "card": card.to_dict(),
                }
            )
            return {"status": "STAGED", "message": "Zotero is offline; audit note staged in local queue."}

        # Check existing child notes
        try:
            resp = requests.get(f"{self.base_url}/items/{item_key}/children", headers=self._headers(), timeout=3)
            if resp.status_code == 200:
                children = resp.json()
                if isinstance(children, list):
                    for child in children:
                        if not isinstance(child, dict):
                            continue
                        c_data = child.get("data", child)
                        if not isinstance(c_data, dict):
                            continue
                        if c_data.get("itemType") == "note" and "scifi-audit-card" in str(c_data.get("note", "")):
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
                    "card": card.to_dict(),
                }
            )
            return {"status": "STAGED", "error": str(e)}

    def apply_tags(
        self,
        item_key: str,
        tags: list[str],
        replace_scifi_tags: bool = True,
        replace_tags: set[str] | None = None,
    ) -> dict[str, Any]:
        """
        Apply tags to parent item while preserving user-authored tags.
        """
        tags_to_replace = replace_tags if replace_tags is not None else SCIFI_STATUS_TAGS
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
                if replace_scifi_tags and tag_name in tags_to_replace:
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
        """Retrieve all item data dicts in a collection via the live local HTTP API."""
        items: list[dict[str, Any]] = []
        start = 0
        limit = 100
        try:
            while True:
                resp = requests.get(
                    f"{self.base_url}/collections/{collection_key}/items?limit={limit}&start={start}",
                    headers=self._headers(),
                    timeout=5,
                )
                if resp.status_code != 200:
                    break
                batch = resp.json()
                if not isinstance(batch, list) or not batch:
                    break
                for entry in batch:
                    data = entry.get("data", {})
                    if data.get("itemType") not in ("attachment", "note", "annotation"):
                        items.append(data)
                if len(batch) < limit:
                    break
                start += limit
        except Exception:
            pass
        return items

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

    def update_item_metadata(self, item_key: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Update bibliographic metadata fields on an existing Zotero item (PATCH), staging if offline."""
        if not fields:
            return {"status": "SKIPPED", "item_key": item_key}
        if not self.is_server_available():
            self._stage_write({"type": "update_metadata", "item_key": item_key, "fields": fields})
            return {"status": "STAGED", "item_key": item_key}
        try:
            g = requests.get(f"{self.base_url}/items/{item_key}", headers=self._headers(), timeout=5)
            if g.status_code != 200:
                self._stage_write({"type": "update_metadata", "item_key": item_key, "fields": fields})
                return {"status": "STAGED", "item_key": item_key, "code": g.status_code}
            data = g.json().get("data", {})
            version = data.get("version")
            patch_payload = {k: v for k, v in fields.items() if v is not None}
            p = requests.patch(
                f"{self.base_url}/items/{item_key}",
                headers=self._headers(version=version, require_auth=True),
                json=patch_payload,
                timeout=10,
            )
            if p.status_code in (200, 204):
                return {"status": "UPDATED", "item_key": item_key, "fields": list(patch_payload.keys())}
            return {"status": "ERROR", "item_key": item_key, "code": p.status_code}
        except Exception as e:
            self._stage_write({"type": "update_metadata", "item_key": item_key, "fields": fields})
            return {"status": "STAGED", "item_key": item_key, "error": str(e)}

    def delete_item(self, item_key: str) -> dict[str, Any]:
        """Delete an item (e.g. a duplicate) via the local Zotero HTTP API."""
        if not self.is_server_available():
            return {"status": "OFFLINE", "item_key": item_key}
        try:
            g = requests.get(f"{self.base_url}/items/{item_key}", headers=self._headers(), timeout=5)
            if g.status_code != 200:
                return {"status": "NOT_FOUND", "item_key": item_key, "code": g.status_code}
            version = g.json().get("data", {}).get("version")
            d = requests.delete(
                f"{self.base_url}/items/{item_key}",
                headers=self._headers(version=version, require_auth=True),
                timeout=10,
            )
            if d.status_code in (200, 204):
                return {"status": "DELETED", "item_key": item_key}
            return {"status": "ERROR", "item_key": item_key, "code": d.status_code}
        except Exception as e:
            return {"status": "ERROR", "item_key": item_key, "error": str(e)}

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
                    card = ZoteroAuditCard.from_dict(c_data, item_key=key)
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
                elif m_type == "update_metadata":
                    fields = item.get("fields")
                    if key and isinstance(fields, dict):
                        res = self.update_item_metadata(key, fields)

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
