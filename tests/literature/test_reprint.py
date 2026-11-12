"""
Tests for Author Reprint Outreach Engine (scifi.literature.reprint).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scifi.literature.models import AuthorRecord, PaperLocationRecord, PaperRecord
from scifi.literature.reprint import (
    build_mailto_url,
    create_reprint_record,
    generate_reprint_draft,
    ingest_paper_copy,
    prepare_reprint_for_paper,
    resolve_author_contact,
)
from scifi.literature.store import LiteratureStore


def test_generate_reprint_draft_and_mailto():
    paper = PaperRecord(id="10.1016/j.neucom.2023.12345", title="Adaptive Quadrotor Control", year=2023)
    draft = generate_reprint_draft(
        paper=paper,
        author_name="Prof. Alice Walker",
        author_email="alice.walker@cam.ac.uk",
        author_affiliation="University of Cambridge",
    )
    assert "Adaptive Quadrotor Control" in draft["subject"]
    assert "Dear Prof. Alice Walker" in draft["body"]
    assert "scholarly sharing" in draft["body"].lower()

    url = build_mailto_url("alice.walker@cam.ac.uk", draft["subject"], draft["body"])
    assert url.startswith("mailto:alice.walker@cam.ac.uk?subject=")
    assert "Adaptive%20Quadrotor%20Control" in url


def test_generate_reprint_draft_with_dict_and_metadata():
    paper_dict = {
        "title": "Robust Optimization for Satellite Swarms",
        "year": 2024,
        "venue_name": "IEEE Trans. Control",
    }
    author_dict = {
        "name": "Dr. Sarah Connor",
        "email": "sconnor@caltech.edu",
        "affiliation": "Caltech",
    }
    draft = generate_reprint_draft(paper=paper_dict, author_name=author_dict)
    assert "Robust Optimization for Satellite Swarms" in draft["subject"]
    assert "Dear Dr. Sarah Connor," in draft["body"]
    assert "(IEEE Trans. Control, 2024)" in draft["body"]
    assert "scholarly sharing" in draft["body"].lower()


def test_generate_reprint_draft_no_author_name():
    paper = PaperRecord(id="10.1000/anon", title="Anonymous Preprint")
    draft = generate_reprint_draft(paper=paper, author_name=None)
    assert "Dear Colleague," in draft["body"]
    assert "Author reprint request: Anonymous Preprint" in draft["subject"]


def test_build_mailto_url_no_email():
    url = build_mailto_url(None, "Subject Line", "Body content")
    assert url.startswith("mailto:?subject=Subject%20Line&body=Body%20content")


def test_build_mailto_url_special_characters():
    url = build_mailto_url("author@example.com", "Request: Paper & Co.", "Line 1\nLine 2")
    assert "author@example.com" in url
    assert "Request%3A%20Paper%20%26%20Co." in url
    assert "Line%201%0ALine%202" in url


def test_resolve_author_contact_openalex_corresponding():
    fake_work = {
        "title": "Quadrotor Control",
        "authorships": [
            {
                "author": {"display_name": "First Author", "id": "A1"},
                "is_corresponding": False,
                "institutions": [{"display_name": "Uni A"}],
            },
            {
                "author": {"display_name": "Dr. Bob Smith", "id": "A2"},
                "is_corresponding": True,
                "email": "bob.smith@ox.ac.uk",
                "institutions": [{"display_name": "University of Oxford"}],
            },
        ],
    }
    with patch("scifi.literature.reprint._http_get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = fake_work
        mock_get.return_value = mock_resp

        contact = resolve_author_contact("10.1016/j.test.2023")
        assert contact["name"] == "Dr. Bob Smith"
        assert contact["email"] == "bob.smith@ox.ac.uk"
        assert contact["affiliation"] == "University of Oxford"


def test_resolve_author_contact_redacted_email():
    fake_work = {
        "title": "Unlisted Contact Paper",
        "authorships": [
            {
                "author": {"display_name": "Dr. Claire Lee", "id": "A3"},
                "is_corresponding": True,
                "email": None,
                "raw_affiliation_strings": ["MIT Media Lab"],
            }
        ],
    }
    with patch("scifi.literature.reprint._http_get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = fake_work
        mock_get.return_value = mock_resp

        contact = resolve_author_contact("10.1016/j.unlisted.2023")
        assert contact["name"] == "Dr. Claire Lee"
        assert contact["email"] is None
        assert contact["affiliation"] == "MIT Media Lab"


def test_resolve_author_contact_crossref_fallback():
    # OpenAlex 404, Crossref 200
    oa_resp = MagicMock()
    oa_resp.status_code = 404

    cr_data = {
        "message": {
            "author": [
                {
                    "given": "Gregory",
                    "family": "House",
                    "email": "ghouse@princeton.edu",
                    "affiliation": [{"name": "Princeton-Plainsboro"}],
                }
            ]
        }
    }
    cr_resp = MagicMock()
    cr_resp.status_code = 200
    cr_resp.json.return_value = cr_data

    with patch("scifi.literature.reprint._http_get", side_effect=[oa_resp, cr_resp]) as mock_get:
        contact = resolve_author_contact("10.1016/j.crossref.2023")
        assert contact["name"] == "Gregory House"
        assert contact["email"] == "ghouse@princeton.edu"
        assert contact["affiliation"] == "Princeton-Plainsboro"
        # Verify Crossref query uses percent-encoded DOI
        second_call_url = mock_get.call_args_list[1][0][0]
        assert "10.1016%2Fj.crossref.2023" in second_call_url


def test_resolve_author_contact_semantic_scholar_fallback():
    # OpenAlex 404, Crossref 404, Semantic Scholar 200
    oa_resp = MagicMock()
    oa_resp.status_code = 404

    cr_resp = MagicMock()
    cr_resp.status_code = 404

    s2_data = {
        "authors": [
            {
                "name": "Jane Doe",
                "affiliations": ["Stanford AI Lab"],
            }
        ]
    }
    s2_resp = MagicMock()
    s2_resp.status_code = 200
    s2_resp.json.return_value = s2_data

    with patch("scifi.literature.reprint._http_get", side_effect=[oa_resp, cr_resp, s2_resp]):
        contact = resolve_author_contact("10.1016/j.s2.2023")
        assert contact["name"] == "Jane Doe"
        assert contact["email"] is None
        assert contact["affiliation"] == "Stanford AI Lab"


def test_resolve_author_contact_empty_or_clean_doi():
    contact = resolve_author_contact("")
    assert contact["name"] == "Corresponding Author"
    assert contact["email"] is None


def test_resolve_author_contact_network_failure_fallback():
    with patch("scifi.literature.reprint._http_get", side_effect=Exception("Timeout")):
        contact = resolve_author_contact("10.1016/j.offline.2023")
        assert contact["name"] == "Corresponding Author"
        assert contact["email"] is None
        assert contact["affiliation"] is None


def test_prepare_reprint_for_paper(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)
    proj = store.register_project("test_proj", str(tmp_path / "workspace"))
    paper = PaperRecord(
        id="10.1000/paywalled.2023",
        title="Theoretical Stability of Neural ODEs",
        year=2023,
        authors=[AuthorRecord(id="a1", name="Dr. David Miller", email="david@toronto.edu", institution="U of Toronto")],
    )
    store.upsert_paper(paper)
    store.link_paper_to_project(proj.id, paper.id)

    # Calling prepare_reprint_for_paper without overriding author details
    req = prepare_reprint_for_paper(store=store, project_id=proj.id, paper_id=paper.id)
    assert req.id.startswith("rep-")
    assert req.paper_id == paper.id
    assert req.author_name == "Dr. David Miller"
    assert req.author_email == "david@toronto.edu"
    assert req.status == "DRAFT_READY"
    assert "Theoretical Stability of Neural ODEs" in req.subject
    assert "Dear Dr. David Miller" in req.body
    assert "mailto:david@toronto.edu" in req.mailto_url

    # Check that record is retrieved from store
    reprints = store.get_reprint_requests(project_id=proj.id)
    assert len(reprints) == 1
    assert reprints[0].id == req.id


def test_prepare_reprint_for_paper_triggers_contact_resolution(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)
    proj = store.register_project("test_proj", str(tmp_path / "workspace"))
    paper = PaperRecord(
        id="10.1000/noauthors.2023",
        title="Paper Without Local Authors",
        year=2023,
    )
    store.upsert_paper(paper)

    with patch(
        "scifi.literature.reprint.resolve_author_contact",
        return_value={"name": "Prof. External", "email": "ext@edu.org", "affiliation": "Org"},
    ):
        req = prepare_reprint_for_paper(store=store, project_id=proj.id, paper_id=paper.id)
        assert req.author_name == "Prof. External"
        assert req.author_email == "ext@edu.org"
        assert req.author_affiliation == "Org"


def test_prepare_reprint_for_paper_synchronizes_author_name_and_email(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)
    proj = store.register_project("test_proj", str(tmp_path / "workspace"))
    # Local paper only has a first author without email (e.g. graduate student)
    paper = PaperRecord(
        id="10.1000/synctest",
        title="Synchronized Author Test",
        year=2023,
        authors=[AuthorRecord(id="a1", name="Student Alice", email=None, institution="Lab A")],
    )
    store.upsert_paper(paper)
    store.link_paper_to_project(proj.id, paper.id)

    # External contact resolution finds the corresponding author (PI)
    with patch(
        "scifi.literature.reprint.resolve_author_contact",
        return_value={"name": "Prof. Bob (PI)", "email": "bob@pi.edu", "affiliation": "Lab A"},
    ):
        req = prepare_reprint_for_paper(store=store, project_id=proj.id, paper_id=paper.id)
        # Author name should be synchronized with the resolved corresponding email
        assert req.author_name == "Prof. Bob (PI)"
        assert req.author_email == "bob@pi.edu"
        assert "Dear Prof. Bob (PI)" in req.body
        assert "mailto:bob@pi.edu" in req.mailto_url


def test_create_reprint_record_helper(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)
    proj = store.register_project("test_proj", str(tmp_path / "workspace"))

    req = create_reprint_record(
        store=store,
        project_id=proj.id,
        paper_id="10.1000/helper",
        author_name="Manual Author",
        author_email="manual@test.org",
        subject="Manual Subject",
        body="Manual Body",
    )
    assert req.author_name == "Manual Author"
    assert req.status == "DRAFT_READY"


def test_ingest_paper_copy(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)
    proj = store.register_project("test_proj", str(tmp_path / "workspace"))
    paper = PaperRecord(id="10.1000/paywall1", title="Paywalled Work", year=2023)
    store.upsert_paper(paper)
    store.link_paper_to_project(proj.id, paper.id)

    # Also prepare a reprint request in store so we verify status flips to RECEIVED
    reprint_req = store.create_reprint_request(
        project_id=proj.id,
        paper_id=paper.id,
        author_name="Prof. Smith",
        status="DRAFT_READY",
    )

    # Prepare dummy PDF
    dummy_pdf = tmp_path / "author_copy.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 dummy content")

    result = ingest_paper_copy(
        store=store,
        project_id=proj.id,
        paper_id=paper.id,
        pdf_path=dummy_pdf,
        storage_dir=tmp_path / "global_storage",
    )
    assert result["status"] == "SUCCESS"
    assert result["file_size"] == len(b"%PDF-1.4 dummy content")
    assert Path(result["stored_path"]).exists()

    # Paper location should now be marked local & accessible
    locations = store.get_paper_locations(paper.id)
    assert len(locations) > 0
    assert locations[0].is_accessible is True
    assert locations[0].is_oa is True
    assert locations[0].local_pdf_path == result["stored_path"]

    # Reprint request should transition to RECEIVED
    updated_req = store.get_reprint_request(reprint_req.id)
    assert updated_req.status == "RECEIVED"


def test_ingest_paper_copy_unindexed_paper_creates_stub(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)
    proj = store.register_project("test_proj", str(tmp_path / "workspace"))

    dummy_pdf = tmp_path / "unindexed.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 brand new paper")

    # Ingest without prior upsert_paper
    result = ingest_paper_copy(
        store=store,
        project_id=proj.id,
        paper_id="10.1000/unindexed.never.seen",
        pdf_path=dummy_pdf,
        storage_dir=tmp_path / "storage",
    )
    assert result["status"] == "SUCCESS"
    paper = store.get_paper("10.1000/unindexed.never.seen")
    assert paper is not None
    assert paper.id == "10.1000/unindexed.never.seen"

    locations = store.get_paper_locations("10.1000/unindexed.never.seen")
    assert len(locations) == 1
    assert locations[0].is_accessible is True


def test_ingest_paper_copy_distinct_location_ids_for_shared_pdf(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)
    proj = store.register_project("test_proj", str(tmp_path / "workspace"))

    shared_pdf = tmp_path / "shared_volume.pdf"
    shared_pdf.write_bytes(b"%PDF-1.4 conference proceedings volume")

    # Ingest same PDF for two distinct papers
    ingest_paper_copy(store, proj.id, "10.1000/paper_a", shared_pdf, storage_dir=tmp_path / "storage")
    ingest_paper_copy(store, proj.id, "10.1000/paper_b", shared_pdf, storage_dir=tmp_path / "storage")

    locs_a = store.get_paper_locations("10.1000/paper_a")
    locs_b = store.get_paper_locations("10.1000/paper_b")

    assert len(locs_a) == 1
    assert len(locs_b) == 1
    assert locs_a[0].id != locs_b[0].id
    assert locs_a[0].local_pdf_path == locs_b[0].local_pdf_path


def test_ingest_paper_copy_preserves_declined_and_skipped_status(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)
    proj = store.register_project("test_proj", str(tmp_path / "workspace"))

    req_sent = store.create_reprint_request(proj.id, "10.1000/status_test", "Author A", status="SENT")
    req_skipped = store.create_reprint_request(proj.id, "10.1000/status_test", "Author B", status="SKIPPED")
    req_declined = store.create_reprint_request(proj.id, "10.1000/status_test", "Author C", status="DECLINED")

    dummy_pdf = tmp_path / "copy.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 test")

    ingest_paper_copy(store, proj.id, "10.1000/status_test", dummy_pdf, storage_dir=tmp_path / "storage")

    assert store.get_reprint_request(req_sent.id).status == "RECEIVED"
    assert store.get_reprint_request(req_skipped.id).status == "SKIPPED"
    assert store.get_reprint_request(req_declined.id).status == "DECLINED"


def test_store_upsert_paper_preserves_is_accessible(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)

    loc = PaperLocationRecord(
        id="loc-accessible-test",
        paper_id="10.1000/accessible",
        location_type="local",
        is_oa=True,
        oa_status="gold",
        is_accessible=True,
        local_pdf_path="/path/to/paper.pdf",
    )
    paper = PaperRecord(
        id="10.1000/accessible",
        title="Accessible Paper",
        year=2024,
        locations=[loc],
    )
    store.upsert_paper(paper)

    rehydrated = store.get_paper("10.1000/accessible")
    assert rehydrated is not None
    assert len(rehydrated.locations) == 1
    assert rehydrated.locations[0].is_accessible is True

    locs = store.get_paper_locations("10.1000/accessible")
    assert len(locs) == 1
    assert locs[0].is_accessible is True


def test_ingest_paper_copy_missing_file_raises(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)
    proj = store.register_project("test_proj", str(tmp_path / "workspace"))

    with pytest.raises(FileNotFoundError):
        ingest_paper_copy(
            store=store,
            project_id=proj.id,
            paper_id="10.1000/notfound",
            pdf_path=tmp_path / "non_existent.pdf",
        )


def test_ingest_paper_copy_invalid_pdf_raises(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)
    proj = store.register_project("test_proj", str(tmp_path / "workspace"))

    bad_file = tmp_path / "not_a_pdf.txt"
    bad_file.write_text("Hello, this is just plain text, not a PDF document.", encoding="utf-8")

    with pytest.raises(ValueError, match="not a valid PDF"):
        ingest_paper_copy(
            store=store,
            project_id=proj.id,
            paper_id="10.1000/invalid_pdf",
            pdf_path=bad_file,
        )
