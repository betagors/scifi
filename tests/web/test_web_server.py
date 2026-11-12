import json
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from scifi.literature.models import CitationRecord, PaperRecord
from scifi.literature.store import LiteratureStore
from scifi.web.server import (
    SciFiWebServer,
    find_available_port,
)


def test_web_server_api_routes(tmp_path: Path):
    db_file = tmp_path / "web_store.db"
    store = LiteratureStore(db_file)
    proj = store.register_project("uav-lab", str(tmp_path / "uav"))
    paper = PaperRecord(id="10.1000/web_test", title="Web Test Paper", year=2024)
    store.upsert_paper(paper)
    store.link_paper_to_project(proj.id, paper.id)

    port = find_available_port(start_port=8900)
    server = SciFiWebServer(store=store, host="127.0.0.1", port=port, static_dir=tmp_path / "static")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        # 1. Test GET /api/projects
        req = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/projects")
        assert req.status == 200
        data = json.loads(req.read().decode())
        assert len(data["projects"]) == 1
        assert data["projects"][0]["name"] == "uav-lab"
        assert data["projects"][0]["paper_count"] == 1

        # 2. Test GET /api/projects/<id>/papers
        req_papers = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/projects/{proj.id}/papers")
        assert req_papers.status == 200
        pdata = json.loads(req_papers.read().decode())
        assert len(pdata["papers"]) == 1
        assert pdata["papers"][0]["title"] == "Web Test Paper"
        assert "oa_status" in pdata["papers"][0]
        assert "has_pdf" in pdata["papers"][0]
        assert "gap_count" in pdata["papers"][0]
    finally:
        server.shutdown()
        server.server_close()


def test_web_server_graph_and_reprints(tmp_path: Path):
    db_file = tmp_path / "graph_store.db"
    store = LiteratureStore(db_file)
    proj = store.register_project("graph-proj", str(tmp_path / "graph_repo"))

    p1 = PaperRecord(id="10.1000/p1", title="Paper One", year=2022)
    p2 = PaperRecord(id="10.1000/p2", title="Paper Two", year=2024)
    store.upsert_paper(p1)
    store.upsert_paper(p2)
    store.link_paper_to_project(proj.id, p1.id)
    store.link_paper_to_project(proj.id, p2.id)
    store.add_citations(
        [
            CitationRecord(
                source_paper_id=p2.id,
                target_paper_id=p1.id,
                is_influential=True,
            )
        ]
    )

    reprint_req = store.create_reprint_request(
        project_id=proj.id,
        paper_id=p2.id,
        author_name="Prof. Turing",
        author_email="turing@cam.ac.uk",
        author_affiliation="Cambridge",
        subject="Reprint Request: Paper Two",
        body="Dear Prof. Turing...",
        mailto_url="mailto:turing@cam.ac.uk?subject=Reprint",
    )

    port = find_available_port(start_port=8910)
    server = SciFiWebServer(store=store, host="127.0.0.1", port=port, static_dir=tmp_path / "static")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        # GET /api/projects/<id>/graph
        res_graph = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/projects/{proj.id}/graph")
        assert res_graph.status == 200
        gdata = json.loads(res_graph.read().decode())
        assert len(gdata["nodes"]) == 2
        assert len(gdata["edges"]) == 1
        assert gdata["edges"][0]["from"] == p2.id
        assert gdata["edges"][0]["to"] == p1.id
        assert gdata["edges"][0]["is_influential"] is True

        # GET /api/reprints with project_id filter
        res_reprints = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/reprints?project_id={proj.id}")
        assert res_reprints.status == 200
        rdata = json.loads(res_reprints.read().decode())
        assert len(rdata["reprints"]) == 1
        assert rdata["reprints"][0]["id"] == reprint_req.id
        assert rdata["reprints"][0]["author_email"] == "turing@cam.ac.uk"
    finally:
        server.shutdown()
        server.server_close()


def test_web_server_update_reprint_and_ingest(tmp_path: Path):
    db_file = tmp_path / "update_store.db"
    store = LiteratureStore(db_file)
    proj = store.register_project("update-proj", str(tmp_path / "workspace"))
    paper = PaperRecord(id="10.1000/paywalled", title="Paywalled Work", year=2023)
    store.upsert_paper(paper)
    store.link_paper_to_project(proj.id, paper.id)

    reprint_req = store.create_reprint_request(
        project_id=proj.id,
        paper_id=paper.id,
        author_name="Dr. Hopper",
        author_email=None,
        author_affiliation="Yale",
        subject="Reprint: Paywalled Work",
        body="Dear Dr. Hopper...",
    )

    port = find_available_port(start_port=8920)
    server = SciFiWebServer(store=store, host="127.0.0.1", port=port, static_dir=tmp_path / "static")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        # 1. Update reprint email and status via POST /api/reprints/<id>
        update_payload = json.dumps(
            {
                "author_email": "grace.hopper@yale.edu",
                "status": "SENT",
            }
        ).encode("utf-8")
        req_post = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/reprints/{reprint_req.id}",
            data=update_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_post) as resp:
            assert resp.status == 200
            resp_data = json.loads(resp.read().decode())
            assert resp_data["status"] == "SUCCESS"
            assert resp_data["reprint"]["author_email"] == "grace.hopper@yale.edu"
            assert resp_data["reprint"]["status"] == "SENT"
            assert "mailto:grace.hopper@yale.edu" in resp_data["reprint"]["mailto_url"]

        # 2. Ingest PDF via POST /api/papers/ingest
        dummy_pdf = tmp_path / "hopper_reprint.pdf"
        dummy_pdf.write_bytes(b"%PDF-1.4 dummy reprint content")

        ingest_payload = json.dumps(
            {
                "project_id": proj.id,
                "paper_id": paper.id,
                "pdf_path": str(dummy_pdf),
                "storage_dir": str(tmp_path / "storage"),
            }
        ).encode("utf-8")
        req_ingest = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/papers/ingest",
            data=ingest_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_ingest) as resp:
            assert resp.status == 200
            ingest_data = json.loads(resp.read().decode())
            assert ingest_data["status"] == "SUCCESS"
            assert ingest_data["file_size"] == len(b"%PDF-1.4 dummy reprint content")
            assert Path(ingest_data["stored_path"]).exists()

        # 3. Test alias REJECTED -> DECLINED
        decline_payload = json.dumps({"status": "REJECTED"}).encode("utf-8")
        req_decline = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/reprints/{reprint_req.id}",
            data=decline_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_decline) as resp:
            assert resp.status == 200
            decline_data = json.loads(resp.read().decode())
            assert decline_data["reprint"]["status"] == "DECLINED"

        # Test query ?status=REJECTED maps to DECLINED
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/reprints?status=REJECTED") as resp:
            assert resp.status == 200
            query_data = json.loads(resp.read().decode())
            assert len(query_data["reprints"]) == 1
            assert query_data["reprints"][0]["status"] == "DECLINED"

        # Check paper in store now has accessible PDF
        locs = store.get_paper_locations(paper.id)
        assert len(locs) > 0
        assert locs[0].is_accessible is True
    finally:
        server.shutdown()
        server.server_close()


def test_web_server_static_files_and_path_traversal(tmp_path: Path):
    static_dir = tmp_path / "static"
    static_dir.mkdir(parents=True)
    index_file = static_dir / "index.html"
    index_file.write_text("<h1>SciFi Cockpit</h1>", encoding="utf-8")
    css_file = static_dir / "styles.css"
    css_file.write_text("body { background: #000; }", encoding="utf-8")

    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("super_secret_credentials", encoding="utf-8")

    db_file = tmp_path / "static_store.db"
    store = LiteratureStore(db_file)

    port = find_available_port(start_port=8930)
    server = SciFiWebServer(store=store, host="127.0.0.1", port=port, static_dir=static_dir)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        # GET / serves index.html
        res_root = urllib.request.urlopen(f"http://127.0.0.1:{port}/")
        assert res_root.status == 200
        assert "<h1>SciFi Cockpit</h1>" in res_root.read().decode()

        # GET /styles.css serves css
        res_css = urllib.request.urlopen(f"http://127.0.0.1:{port}/styles.css")
        assert res_css.status == 200
        assert "body { background: #000; }" in res_css.read().decode()

        # Path traversal: /../secret.txt should be blocked with 403 Forbidden
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/../secret.txt")
        assert exc_info.value.code == 403

        # URL encoded path traversal: /%2e%2e%2fsecret.txt
        with pytest.raises(urllib.error.HTTPError) as exc_info_enc:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/%2e%2e%2fsecret.txt")
        assert exc_info_enc.value.code == 403

        # Non-existent static file -> 404
        with pytest.raises(urllib.error.HTTPError) as exc_info_404:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/missing.js")
        assert exc_info_404.value.code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_port_fallback():
    # Occupy port 8940
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 8940))
    sock.listen(1)

    try:
        # find_available_port should detect 8940 is in use and return 8941
        available = find_available_port(start_port=8940, max_attempts=5)
        assert available == 8941

        # SciFiWebServer with auto_fallback=True starting at 8940 should bind to 8941
        server = SciFiWebServer(
            store=None,
            host="127.0.0.1",
            port=8940,
            auto_fallback=True,
            max_attempts=5,
        )
        assert server.port == 8941
        server.server_close()
    finally:
        sock.close()


def test_web_server_payload_too_large(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)
    port = find_available_port(start_port=8970)
    server = SciFiWebServer(store=store, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        req_large = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/papers/ingest",
            data=b"{}",
            headers={"Content-Length": str(16 * 1024 * 1024), "Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req_large)
        assert exc_info.value.code == 413
    finally:
        server.shutdown()
        server.server_close()
