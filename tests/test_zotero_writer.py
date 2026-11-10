# tests/test_zotero_writer.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from scifi.literature.zotero.writer import ZoteroLocalWriter
from scifi.literature.zotero.models import ZoteroAuditCard

def test_writer_offline_queues_mutations(tmp_path):
    queue_file = tmp_path / "zotero_write_queue.json"
    # Use non-existent port to guarantee offline testing
    writer = ZoteroLocalWriter(port=23999, stage_file=queue_file)
    
    card = ZoteroAuditCard(
        item_key="ITEMKEY1",
        contribution="UAV Optimization",
        assumptions_flagged=["Static users"],
        benchmarks_extracted=[{"metric": "Throughput", "value": "+23%"}],
        math_verified=True,
        retraction_status="OK"
    )
    
    # Server offline: should stage cleanly without raising
    res = writer.push_audit_card_note("ITEMKEY1", card)
    assert res["status"] == "STAGED"
    assert queue_file.exists()
    content = json.loads(queue_file.read_text(encoding="utf-8"))
    assert len(content) == 1
    assert content[0]["item_key"] == "ITEMKEY1"
    assert content[0]["type"] == "audit_note"

def test_writer_upsert_replaces_existing_audit_card(tmp_path):
    queue_file = tmp_path / "zotero_write_queue.json"
    writer = ZoteroLocalWriter(port=23119, stage_file=queue_file)
    
    with patch.object(writer, "is_server_available", return_value=True):
        with patch("requests.get") as mock_get, patch("requests.patch") as mock_patch:
            # Mock child items call
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: [
                    {"key": "NOTEKEY1", "data": {"itemType": "note", "note": '<div class="scifi-audit-card">old note</div>', "version": 5}}
                ]
            )
            mock_patch.return_value = MagicMock(status_code=204)
            
            card = ZoteroAuditCard(
                item_key="ITEMKEY1",
                contribution="Updated UAV Optimization",
                assumptions_flagged=[],
                benchmarks_extracted=[],
                math_verified=True,
                retraction_status="OK"
            )
            res = writer.push_audit_card_note("ITEMKEY1", card)
            assert res["status"] == "UPDATED"
            assert mock_patch.called

def test_writer_preserves_user_tags(tmp_path):
    queue_file = tmp_path / "zotero_write_queue.json"
    writer = ZoteroLocalWriter(port=23119, stage_file=queue_file)
    
    with patch.object(writer, "is_server_available", return_value=True):
        with patch("requests.get") as mock_get, patch("requests.patch") as mock_patch:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {
                    "key": "ITEMKEY1",
                    "version": 3,
                    "data": {
                        "tags": [
                            {"tag": "my-personal-tag"},
                            {"tag": "#unstated-assumption"}
                        ]
                    }
                }
            )
            mock_patch.return_value = MagicMock(status_code=204)
            
            # Apply #scifi-verified (should replace #unstated-assumption, but keep my-personal-tag)
            res = writer.apply_tags("ITEMKEY1", ["#scifi-verified"])
            assert res["status"] == "SUCCESS"
            
            # Check what was passed to patch
            patch_data = mock_patch.call_args[1]["json"]
            applied_tags = [t["tag"] for t in patch_data["tags"]]
            assert "my-personal-tag" in applied_tags
            assert "#scifi-verified" in applied_tags
            assert "#unstated-assumption" not in applied_tags

def test_flush_staged_writes(tmp_path):
    queue_file = tmp_path / "zotero_write_queue.json"
    writer = ZoteroLocalWriter(port=23119, stage_file=queue_file)
    
    # Stage an item
    writer._stage_write({"type": "tag", "item_key": "ITEM1", "tags": ["#scifi-verified"]})
    assert queue_file.exists()
    
    with patch.object(writer, "is_server_available", return_value=True), \
         patch.object(writer, "apply_tags", return_value={"status": "SUCCESS"}):
        flushed = writer.flush_staged_writes()
        assert len(flushed) == 1
        assert not queue_file.exists() or len(json.loads(queue_file.read_text(encoding="utf-8"))) == 0
