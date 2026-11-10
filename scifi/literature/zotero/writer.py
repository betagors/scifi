"""
Local HTTP Note and Tag Dispatcher for Zotero.
Communicates with Zotero local API on port 23119 with in-place deduplicating
upserts (PATCH) and persistent offline staging.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import requests

from scifi.env import is_zotero_port_open
from scifi.literature.zotero.models import ZoteroAuditCard

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
        api_key: Optional[str] = None,
        stage_file: Optional[Union[str, Path]] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.api_key = api_key
        self.base_url = f"http://{host}:{port}/api/users/0"
        self.stage_file = Path(stage_file) if stage_file else Path(".scifi/zotero_write_queue.json")

    def is_server_available(self) -> bool:
        """Check if Zotero local server is responding."""
        return is_zotero_port_open(self.host, self.port, timeout=0.5)

    def _headers(self, version: Optional[int] = None) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Zotero-API-Key"] = self.api_key
        if version is not None:
            headers["If-Unmodified-Since-Version"] = str(version)
        return headers

    def _stage_write(self, mutation: Dict[str, Any]) -> None:
        """Persist an unwritten mutation to the offline queue."""
        self.stage_file.parent.mkdir(parents=True, exist_ok=True)
        queue: List[Dict[str, Any]] = []
        if self.stage_file.is_file():
            try:
                queue = json.loads(self.stage_file.read_text(encoding="utf-8"))
            except Exception:
                queue = []
        queue.append(mutation)
        self.stage_file.write_text(json.dumps(queue, indent=2), encoding="utf-8")

    def format_audit_card_html(self, card: ZoteroAuditCard) -> str:
        """Generate formatted HTML for a SciFi audit card child note."""
        lines = [
            '<div class="scifi-audit-card" data-scifi-version="1.0">',
            '<h3>SciFi Scientific Audit Card</h3>',
            f'<p><strong>Primary Contribution:</strong> {card.contribution}</p>',
        ]

        if card.assumptions_flagged:
            lines.append(f'<details open><summary><strong>Flagged Assumptions ({len(card.assumptions_flagged)})</strong></summary><ul>')
            for a in card.assumptions_flagged:
                lines.append(f'<li>⚠️ {a}</li>')
            lines.append('</ul></details>')
        else:
            lines.append('<p><em>No unstated assumptions flagged.</em></p>')

        if card.benchmarks_extracted:
            lines.append(f'<details open><summary><strong>Extracted SOTA Benchmarks ({len(card.benchmarks_extracted)})</strong></summary><ul>')
            for b in card.benchmarks_extracted:
                metric = b.get("metric", "Metric")
                val = b.get("value", "")
                lines.append(f'<li>📊 <strong>{metric}:</strong> {val}</li>')
            lines.append('</ul></details>')

        math_status = '✅ Verified' if card.math_verified else '⚪ Unaudited / Not applicable'
        lines.append(f'<p><strong>Symbolic Math Verification:</strong> {math_status}</p>')
        lines.append(f'<p><strong>Integrity & Retraction Check:</strong> {card.retraction_status}</p>')
        lines.append('<p><small>Audited autonomously by SciFi.</small></p>')
        lines.append('</div>')
        return "\n".join(lines)

    def push_audit_card_note(self, item_key: str, card: ZoteroAuditCard) -> Dict[str, Any]:
        """
        Push or in-place upsert a SciFi audit card child note under a parent item.
        """
        html_content = self.format_audit_card_html(card)

        if not self.is_server_available():
            self._stage_write({
                "type": "audit_note",
                "item_key": item_key,
                "card": {
                    "contribution": card.contribution,
                    "assumptions_flagged": card.assumptions_flagged,
                    "benchmarks_extracted": card.benchmarks_extracted,
                    "math_verified": card.math_verified,
                    "retraction_status": card.retraction_status,
                },
            })
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
                            headers=self._headers(version=ver),
                            json=patch_payload,
                            timeout=3,
                        )
                        if patch_resp.status_code in (200, 204):
                            return {"status": "UPDATED", "note_key": note_key}

            # Create new child note
            post_payload = [
                {
                    "itemType": "note",
                    "parentItem": item_key,
                    "note": html_content,
                    "tags": [{"tag": "#scifi-audited"}],
                }
            ]
            post_resp = requests.post(f"{self.base_url}/items", headers=self._headers(), json=post_payload, timeout=3)
            if post_resp.status_code in (200, 201):
                return {"status": "CREATED", "response": post_resp.json() if post_resp.text else {}}
            return {"status": "ERROR", "code": post_resp.status_code, "body": post_resp.text}
        except Exception as e:
            self._stage_write({
                "type": "audit_note",
                "item_key": item_key,
                "card": {
                    "contribution": card.contribution,
                    "assumptions_flagged": card.assumptions_flagged,
                    "benchmarks_extracted": card.benchmarks_extracted,
                    "math_verified": card.math_verified,
                    "retraction_status": card.retraction_status,
                },
            })
            return {"status": "STAGED", "error": str(e)}

    def apply_tags(self, item_key: str, tags: List[str], replace_scifi_tags: bool = True) -> Dict[str, Any]:
        """
        Apply tags to parent item while preserving user-authored tags.
        """
        if not self.is_server_available():
            self._stage_write({
                "type": "tags",
                "item_key": item_key,
                "tags": tags,
                "replace_scifi_tags": replace_scifi_tags,
            })
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
            merged_tags: List[Dict[str, str]] = []
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
                headers=self._headers(version=version),
                json={"tags": merged_tags},
                timeout=3,
            )
            if patch_resp.status_code in (200, 204):
                return {"status": "SUCCESS", "tags": [t["tag"] for t in merged_tags]}
            return {"status": "ERROR", "code": patch_resp.status_code}
        except Exception as e:
            self._stage_write({
                "type": "tags",
                "item_key": item_key,
                "tags": tags,
                "replace_scifi_tags": replace_scifi_tags,
            })
            return {"status": "STAGED", "error": str(e)}

    def flush_staged_writes(self) -> List[Dict[str, Any]]:
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

        results: List[Dict[str, Any]] = []
        unprocessed: List[Dict[str, Any]] = []

        for item in queue:
            m_type = item.get("type")
            key = item.get("item_key")
            try:
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
                    results.append(res)
                elif m_type in ("tags", "tag"):
                    res = self.apply_tags(
                        key,
                        item.get("tags", []),
                        replace_scifi_tags=item.get("replace_scifi_tags", True),
                    )
                    results.append(res)
            except Exception:
                unprocessed.append(item)

        if unprocessed:
            self.stage_file.write_text(json.dumps(unprocessed, indent=2), encoding="utf-8")
        else:
            self.stage_file.unlink(missing_ok=True)

        return results
