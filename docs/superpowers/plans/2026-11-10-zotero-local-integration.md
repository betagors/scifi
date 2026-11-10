# SciFi Local Zotero 10 Integration, Project Scaffolding & Graceful UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a zero-copy local Zotero 10 integration, automated 2-pillar project scaffolding (`sf init`/`sf scaffold`), legacy codebase adaptation (`sf adapt`), and self-healing environment management (`sf doctor --fix`) with offline staging and bidirectional audit notes.

**Architecture:** 
- Direct zero-copy reader connecting to `zotero.sqlite` with `immutable=1` URI mode for instant offline PDF and metadata resolution.
- Local HTTP note and tag dispatcher with offline queue persistence and deduplicating in-place upserts (`PATCH`).
- Standardized 2-pillar scaffolding (`paper/` + `code/` orchestrated by `.scifi/config.toml`) with automated Zotero collection binding.
- Resilient self-healing environment manager handling `uv`, Zotero path detection, and graceful fallbacks.

**Tech Stack:** Python >= 3.10, SQLite3 (URI immutable mode), `requests`, `pydantic` / `dataclasses`, `bibtexparser`, `click` / `argparse`, FastMCP (`scifi.server`).

**Spec:** [docs/superpowers/specs/2026-11-10-zotero-local-integration-design.md](file:///c:/Users/Betagors/Code/scifi/docs/superpowers/specs/2026-11-10-zotero-local-integration-design.md)

## Global Constraints
- Concurrency mode: All SQLite connections to `zotero.sqlite` must strictly use `file:///<path>?immutable=1` URI syntax with `uri=True` to prevent `database is locked` errors while Zotero is running.
- Safety invariant: No raw SQL `INSERT` or `UPDATE` queries on `zotero.sqlite`. All writes must route through `127.0.0.1:23119` or stage to `.scifi/zotero_write_queue.json`.
- Non-destructive tagging: Updating SciFi tags must preserve all user-authored tags on top-level items.
- Offline independence: LaTeX projects in `paper/` must be 100% standard LaTeX compiling without requiring Python or SciFi.
- Zero-crash fallback: Missing dependencies (`uv`, Zotero, LaTeX) must never throw unhandled fatal exceptions; they must trigger graceful fallbacks or actionable diagnostics.

## Review Focus
1. Concurrency lock contention on `zotero.sqlite` -> Verified by connecting while another process holds an active write lock.
2. Offline port 23119 during note dispatch -> Verified by queuing mutations into `.scifi/zotero_write_queue.json` without crashing.
3. Note duplication on repeated audit -> Verified by updating existing note in-place using HTML marker `<div class="scifi-audit-card">`.
4. User tag preservation on parent items -> Verified by asserting user tags remain untouched when `#scifi-verified` is added.
5. Non-Zotero / Missing directory fallback -> Verified by asserting `find_local_pdf` falls back cleanly to `workspace/papers` without error.

---

### Task 1: Environment & Prerequisite Self-Healing Manager (`scifi.env`)

**Files:**
- Create: `scifi/env.py`
- Test: `tests/test_env.py`

**Interfaces:**
- Consumes: Standard library (`shutil`, `sys`, `subprocess`, `platform`, `pathlib`)
- Produces: `ensure_uv() -> dict`, `auto_detect_zotero_dir() -> Optional[Path]`, `diagnose_environment(auto_fix: bool = False) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_env.py
import pytest
from pathlib import Path
from scifi.env import ensure_uv, auto_detect_zotero_dir, diagnose_environment

def test_auto_detect_zotero_dir_default(monkeypatch, tmp_path):
    fake_zotero = tmp_path / "Zotero"
    fake_zotero.mkdir()
    (fake_zotero / "zotero.sqlite").touch()
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    detected = auto_detect_zotero_dir()
    assert detected == fake_zotero

def test_diagnose_environment_health():
    diag = diagnose_environment(auto_fix=False)
    assert "python" in diag
    assert "zotero" in diag
    assert "uv" in diag
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_env.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.env'`

- [ ] **Step 3: Implement `scifi/env.py`**

Implement `auto_detect_zotero_dir()` checking standard platform locations (`~/Zotero`), `ensure_uv()` checking PATH and offering safe install or `sys.executable` fallback, and `diagnose_environment(auto_fix: bool)` returning health status dict.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_env.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/env.py tests/test_env.py
git commit -m "feat(env): add self-healing prerequisite and Zotero discovery manager"
```

---

### Task 2: Zotero Data Models & Direct SQLite Reader (`scifi.literature.zotero.reader`)

**Files:**
- Create: `scifi/literature/zotero/__init__.py`
- Create: `scifi/literature/zotero/models.py`
- Create: `scifi/literature/zotero/reader.py`
- Test: `tests/test_zotero_reader.py`

**Interfaces:**
- Consumes: `scifi.env.auto_detect_zotero_dir`
- Produces: `ZoteroLocalReader`, `ZoteroItem`, `ZoteroCollection`, `ZoteroAnnotation`, `ZoteroAuditCard`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_zotero_reader.py
import sqlite3
import pytest
from pathlib import Path
from scifi.literature.zotero.reader import ZoteroLocalReader
from scifi.literature.zotero.models import ZoteroItem, ZoteroCollection

@pytest.fixture
def mock_zotero_db(tmp_path):
    db_path = tmp_path / "zotero.sqlite"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE collections (collectionID INTEGER PRIMARY KEY, collectionName TEXT, parentCollectionID INT)")
    cur.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT)")
    cur.execute("CREATE TABLE collectionItems (collectionID INT, itemID INT, PRIMARY KEY(collectionID, itemID))")
    cur.execute("CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT)")
    cur.execute("CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT)")
    cur.execute("CREATE TABLE itemData (itemID INT, fieldID INT, valueID INT)")
    cur.execute("CREATE TABLE itemAttachments (itemID INTEGER PRIMARY KEY, parentItemID INT, path TEXT, contentType TEXT)")
    cur.execute("CREATE TABLE itemAnnotations (itemID INTEGER PRIMARY KEY, parentItemID INT, type INT, text TEXT, comment TEXT, color TEXT, pageLabel TEXT)")
    
    # Insert test collection and item
    cur.execute("INSERT INTO collections VALUES (1, 'UAV', NULL)")
    cur.execute("INSERT INTO items VALUES (10, 'ITEMKEY1')")
    cur.execute("INSERT INTO items VALUES (11, 'ATTKEY1')")
    cur.execute("INSERT INTO collectionItems VALUES (1, 10)")
    cur.execute("INSERT INTO fields VALUES (1, 'title'), (2, 'DOI')")
    cur.execute("INSERT INTO itemDataValues VALUES (1, 'UAV Caching Study'), (2, '10.1109/TWC.2020.123')")
    cur.execute("INSERT INTO itemData VALUES (10, 1, 1), (10, 2, 2)")
    cur.execute("INSERT INTO itemAttachments VALUES (11, 10, 'storage:paper.pdf', 'application/pdf')")
    cur.execute("INSERT INTO itemAnnotations VALUES (20, 11, 1, 'Interesting result', 'Key theorem', '#ffd400', '3')")
    conn.commit()
    conn.close()
    
    storage_dir = tmp_path / "storage" / "ATTKEY1"
    storage_dir.mkdir(parents=True)
    (storage_dir / "paper.pdf").touch()
    return tmp_path

def test_reader_resolves_collection_and_pdf(mock_zotero_db):
    reader = ZoteroLocalReader(data_dir=mock_zotero_db)
    cols = reader.get_collections()
    assert len(cols) == 1
    assert cols[0].name == "UAV"
    
    items = reader.get_collection_items("UAV")
    assert len(items) == 1
    assert items[0].key == "ITEMKEY1"
    assert items[0].title == "UAV Caching Study"
    assert items[0].doi == "10.1109/TWC.2020.123"
    assert items[0].pdf_path is not None
    assert items[0].pdf_path.name == "paper.pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_zotero_reader.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.literature.zotero'`

- [ ] **Step 3: Implement `models.py` and `reader.py`**

Implement `ZoteroLocalReader` using `file:///{path}/zotero.sqlite?immutable=1` URI connection. Support:
- `get_collections()`
- `get_collection_items(collection_name_or_id)`
- `get_item_by_doi(doi)`
- `get_item_by_arxiv(arxiv_id)`
- `get_pdf_path(item_key)`
- `get_user_annotations(item_key)`

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_zotero_reader.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/zotero/ tests/test_zotero_reader.py
git commit -m "feat(zotero): add data models and zero-copy SQLite local reader"
```

---

### Task 3: Local HTTP Note Dispatcher & Offline Queue (`scifi.literature.zotero.writer`)

**Files:**
- Create: `scifi/literature/zotero/writer.py`
- Test: `tests/test_zotero_writer.py`

**Interfaces:**
- Consumes: `scifi.literature.zotero.models.ZoteroAuditCard`
- Produces: `ZoteroLocalWriter`, `push_audit_card_note()`, `apply_tags()`, `flush_staged_writes()`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_zotero_writer.py
from pathlib import Path
from unittest.mock import patch, MagicMock
from scifi.literature.zotero.writer import ZoteroLocalWriter
from scifi.literature.zotero.models import ZoteroAuditCard

def test_writer_offline_queues_mutations(tmp_path):
    queue_file = tmp_path / "zotero_write_queue.json"
    writer = ZoteroLocalWriter(port=23119, stage_file=queue_file)
    
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
    assert "ITEMKEY1" in queue_file.read_text(encoding="utf-8")

def test_writer_upsert_replaces_existing_audit_card(tmp_path):
    queue_file = tmp_path / "zotero_write_queue.json"
    writer = ZoteroLocalWriter(port=23119, stage_file=queue_file)
    
    with patch("requests.get") as mock_get, patch("requests.patch") as mock_patch:
        # Mock server available
        mock_get.side_effect = [
            MagicMock(status_code=200),  # ping
            MagicMock(status_code=200, json=lambda: [  # children items
                {"key": "NOTEKEY1", "itemType": "note", "note": '<div class="scifi-audit-card">old note</div>', "version": 5}
            ])
        ]
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_zotero_writer.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.literature.zotero.writer'`

- [ ] **Step 3: Implement `scifi/literature/zotero/writer.py`**

Implement `ZoteroLocalWriter` supporting:
- Server availability check (`127.0.0.1:23119`).
- HTML audit card formatting with embedded `<div class="scifi-audit-card">`.
- In-place upsert (`PATCH` if existing card note found, `POST` if new).
- Tag mutation on parent item preserving user tags.
- Persistent offline queue in `stage_file` (`.scifi/zotero_write_queue.json`) with `flush_staged_writes()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_zotero_writer.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/zotero/writer.py tests/test_zotero_writer.py
git commit -m "feat(zotero): add local HTTP note dispatcher and offline staging queue"
```

---

### Task 4: Literature Fetcher Integration (`scifi.literature.fetcher`)

**Files:**
- Modify: `scifi/literature/fetcher.py`
- Test: `tests/test_literature_zotero_fetch.py`

**Interfaces:**
- Consumes: `scifi.literature.zotero.reader.ZoteroLocalReader`
- Produces: Updated `find_local_pdf(paper, ...)` prioritizing Zotero local storage

- [ ] **Step 1: Write the failing test**

```python
# tests/test_literature_zotero_fetch.py
from pathlib import Path
from scifi.literature.fetcher import find_local_pdf
from scifi.literature.models import PaperRecord, PaperIdentifierRecord

def test_find_local_pdf_resolves_from_zotero(tmp_path, monkeypatch):
    # Set up mock Zotero directory
    zotero_dir = tmp_path / "Zotero"
    zotero_dir.mkdir()
    storage_dir = zotero_dir / "storage" / "UAVKEY"
    storage_dir.mkdir(parents=True)
    pdf_file = storage_dir / "Zhang2020.pdf"
    pdf_file.touch()
    
    # Mock Zotero reader returning pdf_file
    monkeypatch.setattr(
        "scifi.literature.zotero.reader.ZoteroLocalReader.get_pdf_path",
        lambda self, key: pdf_file if key == "UAVKEY" else None
    )
    
    paper = PaperRecord(
        id="10.1109/TWC.2020.3011881",
        title="Cache-Enabling UAV Communications",
        identifiers=[PaperIdentifierRecord(provider="zotero", external_id="UAVKEY")]
    )
    
    resolved = find_local_pdf(paper)
    assert resolved == pdf_file
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_literature_zotero_fetch.py -v`  
Expected: FAIL (Zotero provider resolution not yet present in `find_local_pdf`)

- [ ] **Step 3: Update `find_local_pdf` in `scifi/literature/fetcher.py`**

In `find_local_pdf`:
1. Check `paper.identifiers` for `provider == "zotero"`. If found, resolve path via `ZoteroLocalReader.get_pdf_path(external_id)`.
2. If not found by identifier, query `ZoteroLocalReader.get_item_by_doi(doi)` or `get_item_by_arxiv(arxiv_id)`.
3. If Zotero returns a valid existing file path, return it immediately (zero-copy).
4. Fall back to existing search directories (`workspace/papers`, etc.).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_literature_zotero_fetch.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/fetcher.py tests/test_literature_zotero_fetch.py
git commit -m "feat(fetcher): prioritize zero-copy local Zotero storage in find_local_pdf"
```

---

### Task 5: 2-Pillar Project Scaffolding Engine (`scifi.scaffold`)

**Files:**
- Create: `scifi/scaffold.py`
- Test: `tests/test_scaffold.py`

**Interfaces:**
- Consumes: `scifi.env.auto_detect_zotero_dir`, `scifi.literature.zotero.reader.ZoteroLocalReader`
- Produces: `scaffold_project(target_dir: Path, title: str, venue: str, collection: Optional[str]) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scaffold.py
from pathlib import Path
from scifi.scaffold import scaffold_project

def test_scaffold_creates_standard_two_pillar_layout(tmp_path):
    proj_dir = tmp_path / "test_research"
    res = scaffold_project(
        target_dir=proj_dir,
        title="Provably Robust UAV Networks",
        venue="ieee",
        collection="UAV"
    )
    assert res["status"] == "SUCCESS"
    assert (proj_dir / ".scifi" / "config.toml").is_file()
    assert (proj_dir / "paper" / "main.tex").is_file()
    assert (proj_dir / "paper" / "macros.tex").is_file()
    assert (proj_dir / "paper" / "references.bib").is_file()
    assert (proj_dir / "paper" / "sections" / "01_abstract.tex").is_file()
    assert (proj_dir / "code" / "src").is_dir()
    assert (proj_dir / "code" / "pyproject.toml").is_file()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_scaffold.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.scaffold'`

- [ ] **Step 3: Implement `scifi/scaffold.py`**

Implement `scaffold_project`:
1. Creates directory trees: `paper/sections/`, `paper/figures/`, `paper/tables/`, `code/src/`, `code/scripts/`, `code/data/`, `code/results/`, `.scifi/reviews/`, `.scifi/submissions/`.
2. Generates initial templates conforming to SciFi academic rules (semantic macros, upright math subscripts, vector figure stubs).
3. Writes `.scifi/config.toml` configuring target venue and Zotero collection binding.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_scaffold.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/scaffold.py tests/test_scaffold.py
git commit -m "feat(scaffold): implement standardized 2-pillar project scaffolding"
```

---

### Task 6: Legacy Project Adaptation & Migration Engine (`scifi.adapt`)

**Files:**
- Create: `scifi/adapt.py`
- Test: `tests/test_adapt.py`

**Interfaces:**
- Consumes: `scifi.literature.zotero.reader.ZoteroLocalReader`, `scifi.scaffold.scaffold_project`
- Produces: `adapt_project(repo_dir: Path, venue: str, collection: Optional[str], dry_run: bool) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_adapt.py
from pathlib import Path
from scifi.adapt import adapt_project

def test_adapt_migrates_flat_repo_safely(tmp_path):
    flat_repo = tmp_path / "legacy_repo"
    flat_repo.mkdir()
    (flat_repo / "paper.tex").write_text(r"\documentclass{article}\begin{document}Hello\end{document}", encoding="utf-8")
    (flat_repo / "refs.bib").write_text("@article{Zhang2020,\n title={UAV Caching}\n}", encoding="utf-8")
    (flat_repo / "train.py").write_text("print('training')", encoding="utf-8")
    (flat_repo / "data.csv").write_text("x,y\n1,2", encoding="utf-8")
    
    res = adapt_project(flat_repo, venue="ieee", collection="UAV", dry_run=False)
    assert res["status"] == "SUCCESS"
    assert (flat_repo / "paper" / "main.tex").is_file()
    assert (flat_repo / "paper" / "references.bib").is_file()
    assert (flat_repo / "code" / "src" / "train.py").is_file()
    assert (flat_repo / ".scifi" / "config.toml").is_file()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_adapt.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.adapt'`

- [ ] **Step 3: Implement `scifi/adapt.py`**

Implement `adapt_project`:
1. Safely discovers and classifies existing files: publication artifacts (moved to `paper/`), code/data/results (moved to `code/`).
2. Extracts cited references from `.bib` files, cross-references against `zotero.sqlite`, and reports matched vs. missing citations.
3. Generates `.scifi/config.toml` configuring Zotero collection binding and venue settings.
4. Supports `--dry-run` to preview file movements before execution.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_adapt.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/adapt.py tests/test_adapt.py
git commit -m "feat(adapt): implement safe legacy repository migration and .bib reconciliation"
```

---

### Task 7: CLI Commands (`sf zotero`, `sf init`, `sf adapt`, `sf doctor`)

**Files:**
- Modify: `scifi/cli.py`
- Test: `tests/test_cli_zotero.py`

**Interfaces:**
- Consumes: `scifi.literature.zotero`, `scifi.scaffold`, `scifi.adapt`, `scifi.env`
- Produces: CLI commands registered on `sf`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_zotero.py
from click.testing import CliRunner
from scifi.cli import cli

def test_cli_zotero_status():
    runner = CliRunner()
    result = runner.invoke(cli, ["zotero", "status"])
    assert result.exit_code == 0
    assert "Zotero Status" in result.output

def test_cli_doctor():
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor"])
    assert result.exit_code == 0
    assert "Environment Health" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_cli_zotero.py -v`  
Expected: FAIL (commands `zotero` not recognized)

- [ ] **Step 3: Register commands in `scifi/cli.py`**

Add click/argparse command groups:
- `sf zotero status`: prints database path, item count, port 23119 status, active collection.
- `sf zotero sync`: scans collection, syncs `references.bib`, flushes staged writes.
- `sf zotero audit [--key KEY] [--all]`: audits papers and dispatches audit card child notes.
- `sf zotero init-searches`: creates Saved Searches in Zotero.
- `sf zotero flush`: flushes offline staging queue.
- `sf init` / `sf scaffold`: calls `scaffold_project`.
- `sf adapt`: calls `adapt_project`.
- `sf doctor [--fix]`: calls `diagnose_environment`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_cli_zotero.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/cli.py tests/test_cli_zotero.py
git commit -m "feat(cli): wire up sf zotero, sf scaffold, sf adapt, and sf doctor commands"
```

---

### Task 8: FastMCP Tool Handlers (`scifi.server`)

**Files:**
- Modify: `scifi/server.py`
- Test: `tests/test_server_zotero.py`

**Interfaces:**
- Consumes: `scifi.literature.zotero`
- Produces: FastMCP tools: `scifi_zotero_status`, `scifi_zotero_get_collection_papers`, `scifi_zotero_get_annotations`, `scifi_zotero_push_audit_note`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_server_zotero.py
from scifi.server import scifi_zotero_status, scifi_zotero_get_collection_papers

def test_server_zotero_tools_registered():
    status = scifi_zotero_status()
    assert "installed" in status or "data_dir" in status
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_server_zotero.py -v`  
Expected: FAIL (`scifi_zotero_status` not defined)

- [ ] **Step 3: Implement FastMCP tools in `scifi/server.py`**

Expose tools using `@mcp.tool()`:
- `scifi_zotero_status() -> dict`
- `scifi_zotero_get_collection_papers(collection: str = None) -> list`
- `scifi_zotero_get_annotations(item_key: str) -> list`
- `scifi_zotero_push_audit_note(item_key: str, audit_data: dict) -> dict`

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_server_zotero.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/server.py tests/test_server_zotero.py
git commit -m "feat(server): expose Zotero intelligence tools over FastMCP"
```

---

### Task 9: Live Integration Verification & Diagnostic Gate

**Files:**
- Test: `tests/test_integration_zotero_live.py`

- [ ] **Step 1: Write live integration test against actual local Zotero library**

```python
# tests/test_integration_zotero_live.py
from pathlib import Path
from scifi.literature.zotero.reader import ZoteroLocalReader
from scifi.env import auto_detect_zotero_dir

def test_live_local_zotero_library_reads():
    zotero_dir = auto_detect_zotero_dir()
    if not zotero_dir or not (zotero_dir / "zotero.sqlite").exists():
        pytest.skip("Local Zotero library not found on this machine")
    
    reader = ZoteroLocalReader(data_dir=zotero_dir)
    cols = reader.get_collections()
    assert len(cols) > 0
    
    # Check UAV collection specifically
    uav_col = [c for c in cols if c.name == "UAV"]
    if uav_col:
        items = reader.get_collection_items("UAV")
        assert len(items) > 0
        # Verify first item resolves PDF without error
        pdf_items = [i for i in items if i.pdf_path is not None]
        if pdf_items:
            assert pdf_items[0].pdf_path.exists()
```

- [ ] **Step 2: Run live integration test**

Run: `.venv\Scripts\pytest tests/test_integration_zotero_live.py -v`  
Expected: PASS

- [ ] **Step 3: Run full test suite to guarantee zero regression**

Run: `.venv\Scripts\pytest tests/ -v`  
Expected: ALL PASS

- [ ] **Step 4: Final commit**

```bash
git add tests/test_integration_zotero_live.py
git commit -m "test(integration): verify live local Zotero reads against actual library"
```
