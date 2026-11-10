import pytest
from pathlib import Path
from scifi.literature.store import LiteratureStore, DEFAULT_CENTRAL_STORE_PATH
from scifi.literature.models import (
    AuthorRecord,
    CitationRecord,
    PaperLocationRecord,
    PaperRecord,
    ProjectRecord,
    ReprintRequestRecord,
)


def test_project_registration_and_paper_linking(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)

    proj = store.register_project(
        name="quadrotor-control",
        workspace_path=str(tmp_path / "uav_project"),
        description="Autonomous UAV trajectory research",
    )
    assert proj.id is not None
    assert proj.name == "quadrotor-control"
    assert proj.description == "Autonomous UAV trajectory research"

    projects = store.list_projects()
    assert len(projects) == 1
    assert projects[0].name == "quadrotor-control"

    paper = PaperRecord(id="10.1016/test.2023", title="Test Quadrotor Paper", year=2023)
    store.upsert_paper(paper)
    store.link_paper_to_project(project_id=proj.id, paper_id=paper.id, notes="Seed paper")

    papers = store.get_project_papers(proj.id)
    assert len(papers) == 1
    assert papers[0].id == "10.1016/test.2023"
    assert papers[0].title == "Test Quadrotor Paper"


def test_reprint_request_lifecycle(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)
    proj = store.register_project(name="drone-mpc", workspace_path=str(tmp_path / "drone"))
    paper = PaperRecord(id="10.1109/paywalled.2024", title="Paywalled Drone Paper", year=2024)
    store.upsert_paper(paper)

    req = store.create_reprint_request(
        project_id=proj.id,
        paper_id=paper.id,
        author_name="Prof. Jane Doe",
        author_email=None,
        author_affiliation="MIT",
        subject="Reprint request",
        body="Dear Prof. Doe...",
        mailto_url=None,
    )
    assert req.id is not None
    assert req.status == "DRAFT_READY"
    assert req.author_email is None

    # Update email and status
    updated = store.update_reprint_request(req.id, author_email="jane.doe@mit.edu", status="SENT")
    assert updated is not None
    assert updated.author_email == "jane.doe@mit.edu"
    assert updated.status == "SENT"

    requests = store.get_reprint_requests(project_id=proj.id)
    assert len(requests) == 1
    assert requests[0].author_email == "jane.doe@mit.edu"
    assert requests[0].status == "SENT"


def test_project_idempotent_registration_and_lookup(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)

    ws_path = str(tmp_path / "my_project")
    proj1 = store.register_project(name="my-project-v1", workspace_path=ws_path)
    proj2 = store.register_project(name="my-project-v2", workspace_path=ws_path, description="Updated")

    # Should update existing project row rather than violating UNIQUE constraint
    assert proj1.id == proj2.id
    assert proj2.name == "my-project-v2"
    assert proj2.description == "Updated"

    fetched = store.get_project(proj1.id)
    assert fetched is not None
    assert fetched.name == "my-project-v2"

    by_ws = store.get_project_by_workspace(ws_path)
    assert by_ws is not None
    assert by_ws.id == proj1.id

    assert store.get_project("nonexistent-id") is None
    assert store.get_project_by_workspace(tmp_path / "nonexistent_ws") is None


def test_reprint_filters_and_status_update(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)
    proj1 = store.register_project(name="p1", workspace_path=str(tmp_path / "p1"))
    proj2 = store.register_project(name="p2", workspace_path=str(tmp_path / "p2"))

    paper1 = PaperRecord(id="10.1001/a", title="Paper A", year=2021)
    paper2 = PaperRecord(id="10.1002/b", title="Paper B", year=2022)
    store.upsert_paper(paper1)
    store.upsert_paper(paper2)

    req1 = store.create_reprint_request(
        project_id=proj1.id,
        paper_id=paper1.id,
        author_name="Author 1",
        author_email="a1@test.com",
    )
    req2 = store.create_reprint_request(
        project_id=proj2.id,
        paper_id=paper2.id,
        author_name="Author 2",
        author_email="a2@test.com",
    )

    # Filter by project
    assert len(store.get_reprint_requests(project_id=proj1.id)) == 1
    assert len(store.get_reprint_requests(project_id=proj2.id)) == 1
    assert len(store.get_reprint_requests()) == 2

    # Convenience helper update_reprint_status
    store.update_reprint_status(req1.id, "RECEIVED")
    assert store.get_reprint_requests(status="RECEIVED")[0].id == req1.id
    assert len(store.get_reprint_requests(status="DRAFT_READY")) == 1


def test_models_serialization():
    proj = ProjectRecord(
        id="proj-123",
        name="test-proj",
        workspace_path="/tmp/test",
        description="desc",
        created_at="2026-11-10 10:00:00",
        updated_at="2026-11-10 10:00:00",
    )
    d = proj.to_dict()
    assert d["id"] == "proj-123"
    assert d["name"] == "test-proj"
    proj_recreated = ProjectRecord.from_dict(d)
    assert proj_recreated == proj

    row = ("proj-123", "test-proj", "/tmp/test", "desc", "2026-11-10 10:00:00", "2026-11-10 10:00:00")
    proj_from_row = ProjectRecord.from_row(row)
    assert proj_from_row == proj

    req = ReprintRequestRecord(
        id="rep-123",
        project_id="proj-123",
        paper_id="10.1001/a",
        author_name="Dr. Smith",
        author_email=None,
        author_affiliation="Stanford",
        status="DRAFT_READY",
        subject="Request",
        body="Dear Dr. Smith",
        mailto_url=None,
        created_at="2026-11-10 10:00:00",
        updated_at="2026-11-10 10:00:00",
    )
    req_d = req.to_dict()
    assert req_d["author_email"] is None
    req_recreated = ReprintRequestRecord.from_dict(req_d)
    assert req_recreated == req

    req_row = (
        "rep-123",
        "proj-123",
        "10.1001/a",
        "Dr. Smith",
        None,
        "Stanford",
        "DRAFT_READY",
        "Request",
        "Dear Dr. Smith",
        None,
        "2026-11-10 10:00:00",
        "2026-11-10 10:00:00",
    )
    req_from_row = ReprintRequestRecord.from_row(req_row)
    assert req_from_row == req


def test_cascade_delete_project_and_paper(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)

    proj = store.register_project("cascade-test", str(tmp_path / "cproj"))
    paper = PaperRecord(
        id="10.1000/cascade",
        title="Cascade Paper",
        year=2024,
        authors=[AuthorRecord(id="a1", name="Alice Author")],
        locations=[PaperLocationRecord(id="loc1", paper_id="10.1000/cascade", location_type="pdf", is_oa=True, oa_status="gold")],
    )
    store.upsert_paper(paper)
    store.link_paper_to_project(proj.id, paper.id)
    store.create_reprint_request(
        project_id=proj.id,
        paper_id=paper.id,
        author_name="Alice Author",
    )

    assert len(store.get_project_papers(proj.id)) == 1
    assert len(store.get_reprint_requests(project_id=proj.id)) == 1

    # Deleting the project cascades to project_papers and reprint_requests
    with store.transaction():
        store.conn.execute("DELETE FROM projects WHERE id = ?", (proj.id,))

    assert store.get_project(proj.id) is None
    assert len(store.get_project_papers(proj.id)) == 0
    assert len(store.get_reprint_requests(project_id=proj.id)) == 0
    # Paper itself remains in global store
    assert store.get_paper(paper.id) is not None


def test_supporting_query_methods(tmp_path: Path):
    assert DEFAULT_CENTRAL_STORE_PATH == Path.home() / ".scifi" / "literature_store.db"
    
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)
    proj = store.register_project("support-test", str(tmp_path / "sproj"))
    
    p1 = PaperRecord(
        id="10.1000/p1",
        title="Paper 1",
        year=2021,
        locations=[PaperLocationRecord(id="loc1", paper_id="10.1000/p1", location_type="pdf", is_oa=True, oa_status="gold")],
    )
    p2 = PaperRecord(id="10.1000/p2", title="Paper 2", year=2022)
    store.upsert_paper(p1)
    store.upsert_paper(p2)
    
    # Test add_citations and get_paper_citations
    cite = CitationRecord(source_paper_id=p2.id, target_paper_id=p1.id, is_influential=True)
    store.add_citations([cite])
    citations = store.get_paper_citations(p2.id)
    assert len(citations) == 1
    assert citations[0].target_paper_id == p1.id
    assert citations[0].is_influential is True
    
    # Test get_paper_locations
    locs = store.get_paper_locations(p1.id)
    assert len(locs) == 1
    assert locs[0].oa_status == "gold"
    
    # Test get_reprint_request (singular)
    req = store.create_reprint_request(
        project_id=proj.id,
        paper_id=p2.id,
        author_name="Dr. Author",
        author_email="author@univ.edu",
    )
    fetched_req = store.get_reprint_request(req.id)
    assert fetched_req is not None
    assert fetched_req.author_name == "Dr. Author"
    assert fetched_req.author_email == "author@univ.edu"

