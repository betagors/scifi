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

def test_server_zotero_push_audit_note_offline(tmp_path, monkeypatch):
    queue_file = tmp_path / "zotero_write_queue.json"
    monkeypatch.setattr("scifi.literature.zotero.writer.ZoteroLocalWriter.__init__",
                        lambda self, *args, **kwargs: setattr(self, "stage_file", queue_file) or
                                                      setattr(self, "base_url", "http://127.0.0.1:23999/api/users/0") or
                                                      setattr(self, "host", "127.0.0.1") or
                                                      setattr(self, "port", 23999) or
                                                      setattr(self, "api_key", None))
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
    assert res.get("status") == "STAGED"
    assert queue_file.is_file()
    import json
    staged = json.loads(queue_file.read_text(encoding="utf-8"))
    staged_types = [item["type"] for item in staged]
    assert "audit_note" in staged_types
    assert "tags" in staged_types
