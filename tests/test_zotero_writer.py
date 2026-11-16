# tests/test_zotero_writer.py
import json
from unittest.mock import MagicMock, patch

from scifi.literature.zotero.models import ZoteroAuditCard
from scifi.literature.zotero.writer import ZoteroLocalWriter


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
        retraction_status="OK",
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
                    {
                        "key": "NOTEKEY1",
                        "data": {
                            "itemType": "note",
                            "note": '<div class="scifi-audit-card">old note</div>',
                            "version": 5,
                        },
                    }
                ],
            )
            mock_patch.return_value = MagicMock(status_code=204)

            card = ZoteroAuditCard(
                item_key="ITEMKEY1",
                contribution="Updated UAV Optimization",
                assumptions_flagged=[],
                benchmarks_extracted=[],
                math_verified=True,
                retraction_status="OK",
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
                    "data": {"tags": [{"tag": "my-personal-tag"}, {"tag": "#unstated-assumption"}]},
                },
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

    with (
        patch.object(writer, "is_server_available", return_value=True),
        patch.object(writer, "apply_tags", return_value={"status": "SUCCESS"}),
    ):
        flushed = writer.flush_staged_writes()
        assert len(flushed) == 1
        assert not queue_file.exists() or len(json.loads(queue_file.read_text(encoding="utf-8"))) == 0


def test_flush_staged_writes_retains_failed_items(tmp_path):
    queue_file = tmp_path / "zotero_write_queue.json"
    writer = ZoteroLocalWriter(port=23119, stage_file=queue_file)

    # Stage two items
    writer._stage_write({"type": "tag", "item_key": "ITEM1", "tags": ["#scifi-verified"]})
    writer._stage_write({"type": "tag", "item_key": "ITEM2", "tags": ["#scifi-verified"]})

    # First succeeds, second returns STAGED (server dropped)
    with (
        patch.object(writer, "is_server_available", return_value=True),
        patch.object(writer, "apply_tags", side_effect=[{"status": "SUCCESS"}, {"status": "STAGED"}]),
    ):
        flushed = writer.flush_staged_writes()
        assert len(flushed) == 1
        # queue file must still exist and hold the failed item
        assert queue_file.exists()
        retained = json.loads(queue_file.read_text(encoding="utf-8"))
        assert len(retained) == 1
        assert retained[0]["item_key"] == "ITEM2"


def test_create_collection_and_items_idempotent(tmp_path):
    queue_file = tmp_path / "zotero_write_queue.json"
    writer = ZoteroLocalWriter(port=23119, stage_file=queue_file)

    with (
        patch.object(writer, "is_server_available", return_value=True),
        patch.object(writer, "get_collection_key", return_value="COL123"),
        patch("scifi.literature.zotero.writer.requests.post") as mock_post,
    ):
        res = writer.create_collection("UAV")
        assert res["status"] == "EXISTS"
        assert res["collection_key"] == "COL123"
        mock_post.assert_not_called()

    with (
        patch.object(
            writer,
            "get_collection_items_live",
            return_value=[{"DOI": "10.1109/TEST.1", "title": "Existing UAV Paper"}],
        ),
        patch("scifi.literature.zotero.writer.requests.post") as mock_post,
    ):
        created = writer.create_items(
            [
                {"title": "Existing UAV Paper", "DOI": "10.1109/TEST.1"},
                {"title": "Existing UAV Paper"},  # same title, no DOI
            ],
            "COL123",
        )
        assert created == 0
        mock_post.assert_not_called()


def test_attach_linked_pdf_offline_and_online(tmp_path):
    queue_file = tmp_path / "zotero_write_queue.json"
    pdf_file = tmp_path / "sample.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 sample")
    writer = ZoteroLocalWriter(port=23119, stage_file=queue_file)

    with patch.object(writer, "is_server_available", return_value=False):
        res = writer.attach_linked_pdf("PARENT1", pdf_file)
        assert res["status"] == "STAGED"
        assert writer.pending_count() == 1

    with (
        patch.object(writer, "is_server_available", return_value=True),
        patch.object(writer, "_headers", return_value={"Content-Type": "application/json"}),
        patch("scifi.literature.zotero.writer.requests.get") as mock_get,
        patch("scifi.literature.zotero.writer.requests.post") as mock_post,
    ):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"successful": {"0": {"key": "ATT123"}}},
        )
        res = writer.attach_linked_pdf("PARENT1", pdf_file)
        assert res["status"] == "CREATED"
        assert res["attachment_key"] == "ATT123"


def test_import_paper_with_pdf_and_ingest_reciprocity(tmp_path):
    from scifi.literature.reprint import ingest_paper_copy
    from scifi.literature.store import LiteratureStore
    from scifi.server.app import _resolve_project

    proj_dir = tmp_path / "my-project"
    proj_dir.mkdir()
    store = LiteratureStore(tmp_path / "lit.db")

    # _resolve_project auto-registers an existing workspace directory
    proj = _resolve_project(store, str(proj_dir))
    assert proj is not None
    assert proj.name == "my-project"

    pdf_file = tmp_path / "paper.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 content")

    mock_writer = MagicMock()
    mock_writer.import_paper_with_pdf.return_value = {
        "status": "PUSHED",
        "item_key": "ITEM1",
        "attachment": {"status": "CREATED", "attachment_key": "ATT1"},
    }

    res = ingest_paper_copy(
        store=store,
        project_id=proj.id,
        paper_id="10.1016/j.comnet.2024.110615",
        pdf_path=pdf_file,
        storage_dir=tmp_path / "pdfs",
        save_to_zotero=True,
        zotero_collection="my-project",
        responder_email="author@univ.edu",
        zotero_writer=mock_writer,
    )
    assert res["status"] == "SUCCESS"
    assert res["zotero"]["status"] == "PUSHED"
    mock_writer.import_paper_with_pdf.assert_called_once()

    reqs = store.get_reprint_requests(paper_id="10.1016/j.comnet.2024.110615")
    assert len(reqs) == 1
    assert reqs[0].status == "RECEIVED"
    assert reqs[0].author_email == "author@univ.edu"
