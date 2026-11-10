# tests/test_server_zotero.py
import pytest
from scifi.server import (
    scifi_zotero_status,
    scifi_zotero_get_collection_papers,
    scifi_zotero_get_annotations,
    scifi_zotero_push_audit_note,
)

def test_server_zotero_status_tool():
    status = scifi_zotero_status()
    assert isinstance(status, dict)
    assert "status" in status
    assert "detected" in status

def test_server_zotero_push_audit_note_offline():
    res = scifi_zotero_push_audit_note(
        item_key="TESTKEY",
        audit_data={
            "contribution": "Test Study",
            "assumptions_flagged": ["Assumption 1"],
            "benchmarks_extracted": [{"metric": "acc", "value": "95%"}],
            "math_verified": True,
            "retraction_status": "OK",
        }
    )
    assert isinstance(res, dict)
    assert res.get("status") in ("STAGED", "CREATED", "UPDATED", "ERROR")
