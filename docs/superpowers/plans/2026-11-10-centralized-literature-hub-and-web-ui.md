# Centralized Literature Hub, Reprint Outreach Engine & Web Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the centralized literature hub with in-repo manifest sync, on-demand author reprint outreach engine, and a local Web research cockpit (`sf ui`) for SciFi.

**Architecture:** A central SQLite knowledge store at `~/.scifi/literature_store.db` maintains global paper deduplication, project scoping, and author reprint tracking. Projects maintain portable in-repo `.scifi/literature_manifest.json` and `references.bib` for git version control. A built-in, zero-dependency Python HTTP server (`scifi/web/`) serves a responsive Vis.js single-page application at `http://localhost:8080` with a project switcher, interactive citation DAG, papers table, and reprint outreach hub.

**Tech Stack:** Python 3.12+, SQLite (WAL mode), standard library `http.server`, HTML5/Tailwind/Vis.js (embedded static SPA), FastMCP.

**Spec:** `docs/superpowers/specs/2026-11-09-centralized-literature-hub-and-web-ui-design.md`

## Global Constraints

- Python runtime >= 3.12 across Windows, Linux, and macOS.
- Central store path resolved via `Path.home() / ".scifi" / "literature_store.db"`.
- SQLite WAL mode with `busy_timeout = 5000` and foreign keys enabled.
- Zero npm/node external build dependencies for the web UI frontend.
- Nullable `author_email` in `reprint_requests` schema to support missing/redacted author contacts.
- Non-blocking execution: no author lookups during batch crawls; author reprint drafting is strictly on-demand.

## Review Focus

- Redacted/missing author emails in OpenAlex/Semantic Scholar: handle `author_email = None`, set `status = 'DRAFT_READY'`, and allow manual email update in Web UI and CLI.
- Fresh repository clone with empty `~/.scifi/`: `sf literature sync` must re-hydrate papers, citation edges, gaps, and benchmarks without crashing.
- Web server port collision: if port 8080 is in use, auto-fallback to ports 8081–8089.
- Static file server security: prevent path traversal attacks (`../`) when serving frontend static assets.
- Ingesting acquired PDFs: copy to central store `~/.scifi/storage/pdfs/<hash>.pdf`, link in `paper_locations`, update `reprint_requests.status = 'RECEIVED'`.

---

### Task 1: Central Database Schema Evolution & Models

**Files:**
- Modify: `scifi/literature/models.py`
- Modify: `scifi/literature/store.py`
- Test: `tests/literature/test_store_projects_reprints.py`

**Interfaces:**
- Consumes: Existing `LiteratureStore` connection and SQLite migration patterns.
- Produces: `ProjectRecord`, `ReprintRequestRecord` models and methods `register_project()`, `list_projects()`, `get_project()`, `link_paper_to_project()`, `get_project_papers()`, `create_reprint_request()`, `get_reprint_requests()`, `update_reprint_status()`.

- [ ] **Step 1: Write failing tests for project registration and reprint tracking in store**

```python
# tests/literature/test_store_projects_reprints.py
import pytest
from pathlib import Path
from scifi.literature.store import LiteratureStore
from scifi.literature.models import PaperRecord, ProjectRecord, ReprintRequestRecord

def test_project_registration_and_paper_linking(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)
    
    proj = store.register_project(name="quadrotor-control", workspace_path=str(tmp_path / "uav_project"))
    assert proj.id is not None
    assert proj.name == "quadrotor-control"
    
    projects = store.list_projects()
    assert len(projects) == 1
    assert projects[0].name == "quadrotor-control"
    
    paper = PaperRecord(id="10.1016/test.2023", title="Test Quadrotor Paper", year=2023)
    store.upsert_paper(paper)
    store.link_paper_to_project(project_id=proj.id, paper_id=paper.id, notes="Seed paper")
    
    papers = store.get_project_papers(proj.id)
    assert len(papers) == 1
    assert papers[0].id == "10.1016/test.2023"

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
    store.update_reprint_request(req.id, author_email="jane.doe@mit.edu", status="SENT")
    updated = store.get_reprint_requests(project_id=proj.id)
    assert len(updated) == 1
    assert updated[0].author_email == "jane.doe@mit.edu"
    assert updated[0].status == "SENT"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/literature/test_store_projects_reprints.py -v`  
Expected: FAIL (`AttributeError: 'LiteratureStore' object has no attribute 'register_project'`)

- [ ] **Step 3: Implement data models in `scifi/literature/models.py`**

Add `ProjectRecord` and `ReprintRequestRecord` dataclasses with `to_dict()` and `from_row()` serialization.

- [ ] **Step 4: Implement schema migrations and store methods in `scifi/literature/store.py`**

Add `projects`, `project_papers`, and `reprint_requests` tables to `SCHEMA_SQL` and implement CRUD methods with write locks.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/literature/test_store_projects_reprints.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scifi/literature/models.py scifi/literature/store.py tests/literature/test_store_projects_reprints.py
git commit -m "feat(literature): add project scoping and reprint request tracking to store"
```

---

### Task 2: In-Repo Project Manifest & Sync Engine

**Files:**
- Create: `scifi/literature/manifest.py`
- Test: `tests/literature/test_manifest.py`

**Interfaces:**
- Consumes: `LiteratureStore`, `ProjectRecord`, `PaperRecord`, `CitationRecord`.
- Produces: `export_manifest(store, project_id, output_path)`, `import_manifest(store, manifest_path, workspace_path)`, `sync_workspace(store, workspace_path)`.

- [ ] **Step 1: Write failing test for manifest export and re-hydration**

```python
# tests/literature/test_manifest.py
from pathlib import Path
from scifi.literature.store import LiteratureStore
from scifi.literature.models import PaperRecord, CitationRecord
from scifi.literature.manifest import export_manifest, import_manifest, sync_workspace

def test_manifest_export_and_import_roundtrip(tmp_path: Path):
    db1_path = tmp_path / "central1.db"
    store1 = LiteratureStore(db1_path)
    proj1 = store1.register_project("uav-research", str(tmp_path / "repo"))
    
    p1 = PaperRecord(id="10.1000/1", title="Paper 1", year=2021)
    p2 = PaperRecord(id="10.1000/2", title="Paper 2", year=2022)
    store1.upsert_paper(p1)
    store1.upsert_paper(p2)
    store1.link_paper_to_project(proj1.id, p1.id)
    store1.link_paper_to_project(proj1.id, p2.id)
    store1.add_citations([CitationRecord(source_paper_id=p2.id, target_paper_id=p1.id, is_influential=True)])
    
    manifest_file = tmp_path / "repo" / ".scifi" / "literature_manifest.json"
    export_manifest(store1, proj1.id, manifest_file)
    assert manifest_file.exists()
    
    # Simulate fresh clone on machine 2
    db2_path = tmp_path / "central2.db"
    store2 = LiteratureStore(db2_path)
    proj2 = import_manifest(store2, manifest_file, str(tmp_path / "repo"))
    
    assert proj2.name == "uav-research"
    papers2 = store2.get_project_papers(proj2.id)
    assert len(papers2) == 2
    citations2 = store2.get_paper_citations(p2.id)
    assert len(citations2) == 1
    assert citations2[0].target_paper_id == p1.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/literature/test_manifest.py -v`  
Expected: FAIL (`ModuleNotFoundError: No module named 'scifi.literature.manifest'`)

- [ ] **Step 3: Implement `scifi/literature/manifest.py`**

Implement JSON serialization of papers, citation edges, gaps, and benchmarks to `.scifi/literature_manifest.json`, along with `sync_workspace()` that automatically merges local and central states and regenerates `references.bib`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/literature/test_manifest.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/manifest.py tests/literature/test_manifest.py
git commit -m "feat(literature): implement in-repo manifest export and re-hydration sync"
```

---

### Task 3: Author Reprint Outreach Engine

**Files:**
- Create: `scifi/literature/reprint.py`
- Test: `tests/literature/test_reprint.py`

**Interfaces:**
- Consumes: `LiteratureStore`, OpenAlex API / Semantic Scholar API via `requests`.
- Produces: `resolve_author_contact(doi)`, `generate_reprint_draft(paper, author_info)`, `create_reprint_record(...)`, `ingest_paper_copy(store, project_id, paper_id, pdf_path)`.

- [ ] **Step 1: Write failing test for reprint generation and manual email updates**

```python
# tests/literature/test_reprint.py
from pathlib import Path
from scifi.literature.store import LiteratureStore
from scifi.literature.models import PaperRecord
from scifi.literature.reprint import (
    generate_reprint_draft,
    build_mailto_url,
    prepare_reprint_for_paper,
    ingest_paper_copy,
)

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

def test_ingest_paper_copy(tmp_path: Path):
    db_file = tmp_path / "test_store.db"
    store = LiteratureStore(db_file)
    proj = store.register_project("test_proj", str(tmp_path / "workspace"))
    paper = PaperRecord(id="10.1000/paywall1", title="Paywalled Work", year=2023)
    store.upsert_paper(paper)
    store.link_paper_to_project(proj.id, paper.id)
    
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
    assert Path(result["stored_path"]).exists()
    
    # Paper location should now be marked local & accessible
    locations = store.get_paper_locations(paper.id)
    assert len(locations) > 0
    assert locations[0].is_accessible is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/literature/test_reprint.py -v`  
Expected: FAIL (`ModuleNotFoundError: No module named 'scifi.literature.reprint'`)

- [ ] **Step 3: Implement `scifi/literature/reprint.py`**

Implement OpenAlex/Crossref author contact resolution, disciplined non-AI-slop draft letter generator, URI percent-encoded `mailto:` builder, and `ingest_paper_copy()` with content-addressed SHA-256 PDF storage.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/literature/test_reprint.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/reprint.py tests/literature/test_reprint.py
git commit -m "feat(literature): add author reprint outreach generator and PDF ingestion engine"
```

---

### Task 4: Local Web Cockpit Server & REST API

**Files:**
- Create: `scifi/web/__init__.py`
- Create: `scifi/web/server.py`
- Test: `tests/web/test_web_server.py`

**Interfaces:**
- Consumes: `LiteratureStore`, standard library `http.server.ThreadingHTTPServer`.
- Produces: `SciFiWebServer`, `find_available_port(start_port=8080)`, REST routes for `/api/projects`, `/api/projects/<id>/graph`, `/api/projects/<id>/papers`, `/api/reprints`, `/api/papers/ingest`, and secure static asset dispatch.

- [ ] **Step 1: Write failing test for web server REST endpoints and port fallback**

```python
# tests/web/test_web_server.py
import json
import urllib.request
import threading
from pathlib import Path
from scifi.literature.store import LiteratureStore
from scifi.literature.models import PaperRecord
from scifi.web.server import SciFiWebServer, find_available_port

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
        
        # 2. Test GET /api/projects/<id>/papers
        req_papers = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/projects/{proj.id}/papers")
        assert req_papers.status == 200
        pdata = json.loads(req_papers.read().decode())
        assert len(pdata["papers"]) == 1
        assert pdata["papers"][0]["title"] == "Web Test Paper"
    finally:
        server.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web/test_web_server.py -v`  
Expected: FAIL (`ModuleNotFoundError: No module named 'scifi.web'`)

- [ ] **Step 3: Implement `scifi/web/server.py`**

Implement `ThreadingHTTPServer` with JSON route dispatching, path traversal guard for static assets, port fallback (8080..8089), and thread safety using the SQLite WAL store.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/web/test_web_server.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/web/__init__.py scifi/web/server.py tests/web/test_web_server.py
git commit -m "feat(web): add embedded HTTP REST API server with port fallback"
```

---

### Task 5: Local Web Cockpit Frontend Dashboard

**Files:**
- Create: `scifi/web/static/index.html`
- Create: `scifi/web/static/app.js`
- Create: `scifi/web/static/styles.css`
- Test: `tests/web/test_frontend_assets.py`

**Interfaces:**
- Consumes: REST endpoints from `scifi/web/server.py`.
- Produces: Responsive HTML5/Tailwind/Vis.js single-page application with Project Switcher, Session DAG view, Papers table, and Author Reprint Hub with inline email editing.

- [ ] **Step 1: Write test verifying frontend asset structure and security guards**

```python
# tests/web/test_frontend_assets.py
from pathlib import Path
from scifi.web.server import get_default_static_dir

def test_frontend_assets_present():
    static_dir = get_default_static_dir()
    index_file = static_dir / "index.html"
    assert index_file.exists()
    content = index_file.read_text(encoding="utf-8")
    assert "SciFi Research Cockpit" in content
    assert "network-container" in content
    assert "reprints-table" in content
    assert "projects-dropdown" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web/test_frontend_assets.py -v`  
Expected: FAIL (`FileNotFoundError: index.html`)

- [ ] **Step 3: Implement `index.html`, `app.js`, and `styles.css`**

Create a clean, responsive single-page dashboard with:
- Top bar: Project switcher dropdown, session picker, active sync status indicator.
- Tab 1: **Citation Lineage (Vis.js)** with node colors by OA status, zoom controls, and metadata sidebar.
- Tab 2: **Papers & Benchmarks**: Filterable table with year, venue, DOI, OA badges, and benchmark metrics.
- Tab 3: **Author Reprints**: Table of paywalled papers, editable email fields, 1-click `mailto:` buttons, and PDF upload drops.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/web/test_frontend_assets.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/web/static/ tests/web/test_frontend_assets.py
git commit -m "feat(web): add responsive single-page research cockpit dashboard"
```

---

### Task 6: CLI & FastMCP Tool Integration

**Files:**
- Modify: `scifi/literature/cli.py`
- Modify: `scifi/cli.py`
- Modify: `scifi/server.py`
- Test: `tests/literature/test_cli_ui_and_reprints.py`

**Interfaces:**
- Consumes: `scifi.literature.manifest`, `scifi.literature.reprint`, `scifi.web.server`.
- Produces: CLI commands `sf ui`, `sf literature sync`, `sf literature reprint`, `sf literature reprints`, `sf literature ingest-pdf`, and FastMCP tools `scifi_list_projects`, `scifi_get_project_summary`, `scifi_draft_reprint_request`, `scifi_list_pending_reprints`, `scifi_ingest_paper_pdf`.

- [ ] **Step 1: Write failing test for CLI commands and FastMCP tools**

```python
# tests/literature/test_cli_ui_and_reprints.py
from scifi.server import (
    scifi_list_projects,
    scifi_get_project_summary,
    scifi_draft_reprint_request,
    scifi_list_pending_reprints,
)

def test_mcp_projects_and_reprints_tools():
    # 1. Projects listing
    projects = scifi_list_projects()
    assert isinstance(projects, list)
    
    # 2. Draft reprint request tool
    draft = scifi_draft_reprint_request("10.1016/j.neucom.2023.12345")
    assert draft["status"] in ("DRAFT_READY", "ERROR")
    if draft["status"] == "DRAFT_READY":
        assert "subject" in draft
        assert "body" in draft
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/literature/test_cli_ui_and_reprints.py -v`  
Expected: FAIL (`ImportError: cannot import name 'scifi_list_projects' from 'scifi.server'`)

- [ ] **Step 3: Register CLI subcommands in `scifi/literature/cli.py` and `scifi/cli.py`**

Add `sf ui` (with `--port` and `--no-browser`), `sf literature sync`, `sf literature reprint`, `sf literature reprints`, and `sf literature ingest-pdf`.

- [ ] **Step 4: Register FastMCP tools in `scifi/server.py`**

Decorate `scifi_list_projects`, `scifi_get_project_summary`, `scifi_draft_reprint_request`, `scifi_list_pending_reprints`, and `scifi_ingest_paper_pdf` with `@mcp.tool()`.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/literature/test_cli_ui_and_reprints.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scifi/literature/cli.py scifi/cli.py scifi/server.py tests/literature/test_cli_ui_and_reprints.py
git commit -m "feat(cli,mcp): integrate sf ui, literature sync, and reprint tools"
```

---

### Task 7: End-to-End System Verification

**Files:**
- Test: `tests/literature/test_e2e_central_hub.py`

**Interfaces:**
- Exercises: Full flow from literature discovery -> in-repo manifest sync -> reprint generation -> local web cockpit API.

- [ ] **Step 1: Write comprehensive end-to-end integration test**

```python
# tests/literature/test_e2e_central_hub.py
from pathlib import Path
from scifi.literature.store import LiteratureStore
from scifi.literature.models import PaperRecord, CitationRecord
from scifi.literature.manifest import export_manifest, import_manifest
from scifi.literature.reprint import generate_reprint_draft
from scifi.web.server import SciFiWebServer, find_available_port
import urllib.request
import json
import threading

def test_full_literature_hub_and_cockpit_lifecycle(tmp_path: Path):
    central_db = tmp_path / "central_store.db"
    store = LiteratureStore(central_db)
    
    # 1. Project discovery & linking
    proj = store.register_project("autonomous-uav", str(tmp_path / "repo"))
    p1 = PaperRecord(id="10.1000/oa_paper", title="Open Access UAV Survey", year=2022)
    p2 = PaperRecord(id="10.1000/paywalled_paper", title="Paywalled MPC Tracking", year=2024)
    store.upsert_paper(p1)
    store.upsert_paper(p2)
    store.link_paper_to_project(proj.id, p1.id)
    store.link_paper_to_project(proj.id, p2.id)
    store.add_citations([CitationRecord(source_paper_id=p2.id, target_paper_id=p1.id, is_influential=True)])
    
    # 2. In-repo manifest sync
    manifest_path = tmp_path / "repo" / ".scifi" / "literature_manifest.json"
    export_manifest(store, proj.id, manifest_path)
    assert manifest_path.exists()
    
    # 3. Reprint generation for paywalled paper
    draft = generate_reprint_draft(p2, "Prof. Smith", "smith@univ.edu", "Univ Lab")
    req = store.create_reprint_request(
        project_id=proj.id,
        paper_id=p2.id,
        author_name="Prof. Smith",
        author_email="smith@univ.edu",
        author_affiliation="Univ Lab",
        subject=draft["subject"],
        body=draft["body"],
        mailto_url=f"mailto:smith@univ.edu?subject={draft['subject']}",
    )
    assert req.status == "DRAFT_READY"
    
    # 4. Web cockpit serves both project papers and reprints
    port = find_available_port(start_port=8950)
    server = SciFiWebServer(store=store, host="127.0.0.1", port=port, static_dir=tmp_path / "static")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    
    try:
        # Check graph API returns nodes and edges
        res_graph = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/projects/{proj.id}/graph")
        graph_data = json.loads(res_graph.read().decode())
        assert len(graph_data["nodes"]) == 2
        assert len(graph_data["edges"]) == 1
        
        # Check reprints API returns draft
        res_reprints = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/reprints?project_id={proj.id}")
        reprints_data = json.loads(res_reprints.read().decode())
        assert len(reprints_data["reprints"]) == 1
        assert reprints_data["reprints"][0]["author_email"] == "smith@univ.edu"
    finally:
        server.shutdown()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/literature/test_e2e_central_hub.py -v`  
Expected: PASS

- [ ] **Step 3: Run full literature test suite to verify zero regressions**

Run: `pytest tests/literature/ -v`  
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/literature/test_e2e_central_hub.py
git commit -m "test(literature): add end-to-end verification for central hub, sync, and web cockpit"
```
