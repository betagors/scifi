"""
End-to-End System Integration Verification for SciFi Central Literature Hub,
Workspace Synchronization Engine, Author Reprint System, and Web Cockpit API.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import threading
import urllib.request
import urllib.error
from unittest.mock import patch
import pytest

from scifi.literature.manifest import export_manifest, import_manifest, sync_workspace
from scifi.literature.models import CitationRecord, PaperLocationRecord, PaperRecord
from scifi.literature.reprint import (
    DEFAULT_STORAGE_DIR,
    generate_reprint_draft,
    ingest_paper_copy,
    prepare_reprint_for_paper,
)
from scifi.literature.store import DEFAULT_CENTRAL_STORE_PATH, LiteratureStore
from scifi.server import (
    scifi_draft_reprint_request,
    scifi_get_project_summary,
    scifi_ingest_paper_pdf,
    scifi_list_pending_reprints,
    scifi_list_projects,
)
from scifi.web.server import SciFiWebServer, find_available_port


def test_full_literature_hub_and_cockpit_lifecycle(tmp_path: Path):
    """
    Comprehensive lifecycle integration test exercising:
    1. Project registration and linking papers & citations in SQLite central store.
    2. In-repo manifest serialization and bidirectional sync (sync_workspace).
    3. Manifest re-hydration into a clean secondary central store.
    4. Author reprint draft generation for paywalled literature.
    5. Embedded Web Cockpit REST API (/api/projects, /api/projects/<id>/graph, /api/reprints).
    6. Content-addressed PDF ingestion, hash validation, and reprint status transition to RECEIVED.
    7. Post-ingest state propagation to web cockpit and workspace manifest.
    """
    # -------------------------------------------------------------------------
    # 1. Project discovery & linking
    # -------------------------------------------------------------------------
    central_db = tmp_path / "central_store.db"
    store = LiteratureStore(central_db)

    repo_dir = tmp_path / "autonomous-uav-repo"
    repo_dir.mkdir(parents=True, exist_ok=True)

    proj = store.register_project("autonomous-uav", str(repo_dir), description="Autonomous UAV Research")
    assert proj.id is not None
    assert proj.name == "autonomous-uav"

    p1 = PaperRecord(
        id="10.1000/oa_survey",
        title="Open Access UAV Survey",
        year=2022,
        venue_name="IEEE Trans. Robotics",
        citation_count=42,
    )
    p2 = PaperRecord(
        id="10.1000/paywalled_mpc",
        title="Paywalled MPC Tracking",
        year=2024,
        venue_name="Automatica",
        citation_count=15,
    )
    store.upsert_paper(p1)
    store.upsert_paper(p2)

    # Register open-access location for p1
    loc_p1 = PaperLocationRecord(
        id="loc-oa-1",
        paper_id=p1.id,
        location_type="publisher",
        is_oa=True,
        oa_status="gold",
        landing_page_url="https://doi.org/10.1000/oa_survey",
        pdf_url="https://publisher.org/oa_survey.pdf",
        is_accessible=True,
    )
    store.save_paper_location(loc_p1)

    store.link_paper_to_project(proj.id, p1.id)
    store.link_paper_to_project(proj.id, p2.id)

    citation = CitationRecord(
        source_paper_id=p2.id,
        target_paper_id=p1.id,
        is_influential=True,
    )
    store.add_citations([citation])

    project_papers = store.get_project_papers(proj.id)
    assert len(project_papers) == 2

    # -------------------------------------------------------------------------
    # 2. In-repo manifest sync & re-hydration
    # -------------------------------------------------------------------------
    synced_proj = sync_workspace(store, repo_dir)
    assert synced_proj.id == proj.id

    manifest_file = repo_dir / ".scifi" / "literature_manifest.json"
    bib_file = repo_dir / ".scifi" / "references.bib"

    assert manifest_file.exists()
    assert bib_file.exists()

    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest_data["project_name"] == "autonomous-uav"
    assert manifest_data["papers_count"] == 2
    assert len(manifest_data["citations"]) == 1
    assert manifest_data["citations"][0]["source_paper_id"] == p2.id
    assert manifest_data["citations"][0]["target_paper_id"] == p1.id

    bib_content = bib_file.read_text(encoding="utf-8")
    assert "Open Access UAV Survey" in bib_content
    assert "Paywalled MPC Tracking" in bib_content

    # Re-hydration test: fresh secondary store importing the manifest
    secondary_db = tmp_path / "secondary_store.db"
    store_clone = LiteratureStore(secondary_db)
    assert len(store_clone.list_projects()) == 0

    rehydrated_proj = import_manifest(store_clone, manifest_file, repo_dir)
    assert rehydrated_proj.name == "autonomous-uav"
    assert len(store_clone.get_project_papers(rehydrated_proj.id)) == 2
    cloned_citations = store_clone.get_paper_citations(p2.id)
    assert len(cloned_citations) == 1
    assert cloned_citations[0].target_paper_id == p1.id

    # -------------------------------------------------------------------------
    # 3. Reprint generation for paywalled paper
    # -------------------------------------------------------------------------
    req = prepare_reprint_for_paper(
        store=store,
        project_id=proj.id,
        paper_id=p2.id,
        author_name="Prof. Eleanor Vance",
        author_email="e.vance@hillhouse.ac.uk",
        author_affiliation="Hill House Institute of Robotics",
    )
    assert req.id is not None
    assert req.status == "DRAFT_READY"
    assert req.author_name == "Prof. Eleanor Vance"
    assert req.author_email == "e.vance@hillhouse.ac.uk"
    assert "Paywalled MPC Tracking" in req.subject
    assert "Dear Prof. Eleanor Vance," in req.body
    assert "mailto:e.vance@hillhouse.ac.uk" in req.mailto_url

    # Check store has recorded this reprint request
    reprints = store.get_reprint_requests(project_id=proj.id)
    assert len(reprints) == 1
    assert reprints[0].status == "DRAFT_READY"

    # -------------------------------------------------------------------------
    # 4. Local Web Cockpit API
    # -------------------------------------------------------------------------
    port = find_available_port(start_port=8960)
    static_dir = tmp_path / "static_assets"
    static_dir.mkdir(parents=True, exist_ok=True)
    (static_dir / "index.html").write_text("<html><body>SciFi Cockpit E2E</body></html>", encoding="utf-8")

    server = SciFiWebServer(store=store, host="127.0.0.1", port=port, static_dir=static_dir)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    storage_dir = tmp_path / "storage" / "pdfs"
    storage_dir.mkdir(parents=True, exist_ok=True)

    try:
        base_url = f"http://127.0.0.1:{server.port}"

        # 4.1 Check static asset serving
        with urllib.request.urlopen(f"{base_url}/") as res:
            assert res.status == 200
            assert b"SciFi Cockpit E2E" in res.read()

        # 4.2 Check GET /api/projects
        with urllib.request.urlopen(f"{base_url}/api/projects") as res:
            assert res.status == 200
            projects_data = json.loads(res.read().decode())
            assert "projects" in projects_data
            assert len(projects_data["projects"]) == 1
            assert projects_data["projects"][0]["name"] == "autonomous-uav"
            assert projects_data["projects"][0]["paper_count"] == 2

        # 4.3 Check GET /api/projects/<id>/papers
        with urllib.request.urlopen(f"{base_url}/api/projects/{proj.id}/papers") as res:
            assert res.status == 200
            papers_data = json.loads(res.read().decode())
            assert len(papers_data["papers"]) == 2
            p1_entry = next(p for p in papers_data["papers"] if p["id"] == p1.id)
            p2_entry = next(p for p in papers_data["papers"] if p["id"] == p2.id)
            assert p1_entry["oa_status"] == "gold"
            assert p2_entry["oa_status"] == "closed"
            assert p2_entry["has_pdf"] is False

        # 4.4 Check GET /api/projects/<id>/graph
        with urllib.request.urlopen(f"{base_url}/api/projects/{proj.id}/graph") as res:
            assert res.status == 200
            graph_data = json.loads(res.read().decode())
            assert "nodes" in graph_data
            assert "edges" in graph_data
            assert len(graph_data["nodes"]) == 2
            assert len(graph_data["edges"]) == 1
            assert graph_data["edges"][0]["from"] == p2.id
            assert graph_data["edges"][0]["to"] == p1.id

        # 4.5 Check GET /api/reprints
        with urllib.request.urlopen(f"{base_url}/api/reprints?project_id={proj.id}") as res:
            assert res.status == 200
            reprints_res = json.loads(res.read().decode())
            assert len(reprints_res["reprints"]) == 1
            assert reprints_res["reprints"][0]["status"] == "DRAFT_READY"
            assert reprints_res["reprints"][0]["author_email"] == "e.vance@hillhouse.ac.uk"

        # 4.6 Update reprint status via POST /api/reprints/<request_id> -> SENT
        update_url = f"{base_url}/api/reprints/{req.id}"
        req_post = urllib.request.Request(
            update_url,
            data=json.dumps({"status": "SENT"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_post) as res:
            assert res.status == 200
            update_res = json.loads(res.read().decode())
            assert update_res["status"] == "SUCCESS"
            assert update_res["reprint"]["status"] == "SENT"

        assert store.get_reprint_request(req.id).status == "SENT"

        # ---------------------------------------------------------------------
        # 5. Ingesting acquired paper copy & content-addressed storage
        # ---------------------------------------------------------------------
        pdf_bytes = b"%PDF-1.5 %Autonomous UAV Trajectory Tracking with MPC\nEOF"
        expected_hash = hashlib.sha256(pdf_bytes).hexdigest()
        incoming_pdf = tmp_path / "author_reprint_received.pdf"
        incoming_pdf.write_bytes(pdf_bytes)

        # Ingest via Web API POST /api/papers/ingest
        ingest_url = f"{base_url}/api/papers/ingest"
        ingest_payload = {
            "project_id": proj.id,
            "paper_id": p2.id,
            "pdf_path": str(incoming_pdf),
            "storage_dir": str(storage_dir),
        }
        ingest_req = urllib.request.Request(
            ingest_url,
            data=json.dumps(ingest_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(ingest_req) as res:
            assert res.status == 200
            ingest_res = json.loads(res.read().decode())
            assert ingest_res["status"] == "SUCCESS"
            assert ingest_res["sha256"] == expected_hash

        # Verify content-addressed storage on disk
        stored_file = storage_dir / f"{expected_hash}.pdf"
        assert stored_file.exists()
        assert stored_file.read_bytes() == pdf_bytes

        # Verify accessible location update in database
        locations = store.get_paper_locations(p2.id)
        assert len(locations) == 1
        assert locations[0].is_accessible is True
        assert locations[0].is_oa is True
        assert locations[0].oa_status == "green"
        assert locations[0].local_pdf_path == str(stored_file)

        # Verify reprint request transitioned to RECEIVED
        updated_reprint = store.get_reprint_request(req.id)
        assert updated_reprint.status == "RECEIVED"

        # 4.7 Verify web cockpit reflects RECEIVED reprint status and has_pdf
        with urllib.request.urlopen(f"{base_url}/api/reprints?project_id={proj.id}") as res:
            reprints_res = json.loads(res.read().decode())
            assert reprints_res["reprints"][0]["status"] == "RECEIVED"

        with urllib.request.urlopen(f"{base_url}/api/projects/{proj.id}/papers") as res:
            papers_data = json.loads(res.read().decode())
            p2_entry = next(p for p in papers_data["papers"] if p["id"] == p2.id)
            assert p2_entry["has_pdf"] is True
            assert p2_entry["local_pdf_path"] == str(stored_file)

        # ---------------------------------------------------------------------
        # 6. Re-sync workspace manifest and verify state consistency
        # ---------------------------------------------------------------------
        re_synced = sync_workspace(store, repo_dir)
        assert re_synced.id == proj.id

        updated_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        p2_manifest = next(p for p in updated_manifest["papers"] if p["id"] == p2.id)
        assert p2_manifest["has_local_pdf"] is True
        assert p2_manifest["reprint_status"] == "RECEIVED"
        assert len(updated_manifest["reprint_requests"]) == 1
        assert updated_manifest["reprint_requests"][0]["status"] == "RECEIVED"

    finally:
        server.shutdown()
        server.server_close()


def test_e2e_mcp_tools_and_central_hub_coordination(tmp_path: Path):
    """
    End-to-end integration test validating FastMCP tools coordination with
    the central literature store for project management, reprint generation,
    and PDF ingestion.
    """
    db_file = tmp_path / "mcp_hub.db"
    store = LiteratureStore(db_file)

    ws_dir = tmp_path / "deep-rl-workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)
    proj = store.register_project("deep-rl-flight", str(ws_dir))

    paper = PaperRecord(
        id="10.1000/paywalled_deep_rl",
        title="Deep Reinforcement Learning in Dynamic Environments",
        year=2023,
    )
    store.upsert_paper(paper)
    store.link_paper_to_project(proj.id, paper.id)

    dummy_pdf = tmp_path / "incoming_paper.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.7 %Deep RL in Dynamic Environments\nEOF")

    with patch("scifi.server.get_literature_store", return_value=store):
        # 1. List projects via FastMCP tool
        projects = scifi_list_projects()
        assert len(projects) == 1
        assert projects[0]["name"] == "deep-rl-flight"

        # 2. Get project summary via FastMCP tool
        summary = scifi_get_project_summary("deep-rl-flight")
        assert summary["status"] == "SUCCESS"
        assert summary["total_papers"] == 1

        # 3. Draft reprint request via FastMCP tool
        with patch(
            "scifi.literature.reprint.resolve_author_contact",
            return_value={
                "name": "Dr. Sarah Chen",
                "email": "schen@robotics.mit.edu",
                "affiliation": "MIT CSAIL",
            },
        ):
            draft = scifi_draft_reprint_request(
                identifier=paper.id,
                project_name="deep-rl-flight",
            )
            assert draft["status"] == "DRAFT_READY"
            assert draft["author_email"] == "schen@robotics.mit.edu"
            assert "Deep Reinforcement Learning" in draft["subject"]

        # 4. List pending reprints
        pending = scifi_list_pending_reprints(project_name="deep-rl-flight")
        assert len(pending) == 1
        assert pending[0]["paper_id"] == paper.id
        assert pending[0]["status"] == "DRAFT_READY"

        # 5. Ingest paper PDF via FastMCP tool
        ingest_res = scifi_ingest_paper_pdf(
            identifier=paper.id,
            pdf_path=str(dummy_pdf),
            project_name="deep-rl-flight",
        )
        assert ingest_res["status"] == "SUCCESS"
        assert Path(ingest_res["stored_path"]).exists()

        # 6. Verify pending reprints list is now empty (status transitioned to RECEIVED)
        pending_after = scifi_list_pending_reprints(project_name="deep-rl-flight")
        assert len(pending_after) == 0

        reprints_all = store.get_reprint_requests(project_id=proj.id)
        assert len(reprints_all) == 1
        assert reprints_all[0].status == "RECEIVED"


def test_central_store_default_path_resolution():
    """
    Validate that the central literature store resolves to
    Path.home() / ".scifi" / "literature_store.db" as required by specification.
    """
    expected_default = Path.home() / ".scifi" / "literature_store.db"
    assert DEFAULT_CENTRAL_STORE_PATH == expected_default
