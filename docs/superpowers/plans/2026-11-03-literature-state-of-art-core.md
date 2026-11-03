# Literature Intelligence Core (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational literature discovery and graph intelligence core (Phase 1): canonical paper identity, graph-scoped SQLite storage, multi-signal lineage traversal with cycle detection, standalone XSS-safe Vis.js HTML visualizer, Markdown report generator, and FastMCP/CLI integration.

**Architecture:** Extends `scifi.literature` with modular components for data modeling (`models.py`), WAL-mode SQLite storage (`store.py`), OpenAlex/arXiv paper resolution (`resolver.py`), multi-signal lineage ranking and DAG cycle rectification (`lineage.py`), self-contained Vis.js visualizer (`visualizer.py`), and Markdown/BibTeX exporter (`reporter.py`), wired to CLI and FastMCP server.

**Tech Stack:** Python 3.10+, SQLite3 (WAL mode, busy_timeout), requests, Vis.js (embedded), pytest.

**Spec:** `docs/superpowers/specs/2026-11-03-literature-state-of-art-tool-design.md`

---

## Global Constraints

- Python compatibility: 3.10+ compatible type annotations and syntax.
- No mandatory external paid LLM API keys: base resolution, storage, and visualization must run deterministically.
- Concurrency: SQLite must use WAL mode (`PRAGMA journal_mode=WAL;`), `PRAGMA busy_timeout = 5000;`, and `BEGIN IMMEDIATE` transactions.
- Zero raw HTML injection: all bibliographic data (titles, authors, venues) must be sanitized via `html.escape` before serialization into Vis.js HTML templates.
- Security: `scifi_query_store` FastMCP tool must strictly reject mutating SQL statements (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`).

---

## Review Focus

1. **Cycle detection on circular citation links:** Two papers citing each other due to preprint revision lag must be rectified so topological sort does not crash or loop infinitely.
2. **XSS / HTML injection:** Titles or author strings with `<script>`, quotes, or angle brackets must be escaped without breaking JSON serialization inside the standalone HTML.
3. **Database lock contention:** Multiple read/write accesses to `.scifi/literature_store.db` within 5 seconds must succeed without throwing `sqlite3.OperationalError: database is locked`.
4. **Multi-topic graph isolation:** Running searches on two distinct topics must store papers under separate `graph_id` sessions without cross-contaminating graph queries or visual artifacts.
5. **Missing or partial provider metadata:** Papers missing DOIs, publication months, or abstracts must resolve gracefully to fallback identifiers and synthetic citekeys without `NoneType` attribute errors.

---

## Task Structure

### Task 1: Core Data Models (`scifi.literature.models`)

**Files:**
- Create: `scifi/literature/models.py`
- Test: `tests/test_literature_models.py`

**Interfaces:**
- Consumes: Standard library dataclasses / typing.
- Produces: `PaperRecord`, `PaperIdentifierRecord`, `PaperVersionRecord`, `PaperLocationRecord`, `AuthorRecord`, `CitationRecord`, `GraphSessionRecord`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_literature_models.py
from scifi.literature.models import (
    PaperRecord,
    PaperIdentifierRecord,
    PaperVersionRecord,
    PaperLocationRecord,
    AuthorRecord,
    CitationRecord,
    GraphSessionRecord,
)

def test_paper_record_defaults_and_citekey():
    author = AuthorRecord(id="A1", name="Ashish Vaswani")
    paper = PaperRecord(
        id="p-1234",
        title="Attention Is All You Need",
        year=2017,
        publication_date="2017-06-12",
        authors=[author],
    )
    assert paper.id == "p-1234"
    assert paper.year == 2017
    assert paper.generate_cite_key() == "Vaswani2017Attention"
    assert paper.recent_citation_growth == 0.0

def test_paper_location_access_tiers():
    loc = PaperLocationRecord(
        id="loc-1",
        paper_id="p-1234",
        location_type="repository",
        is_oa=True,
        oa_status="green",
        pdf_url="https://arxiv.org/pdf/1706.03762.pdf",
    )
    assert loc.is_oa is True
    assert loc.oa_status == "green"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_models.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.literature.models'`

- [ ] **Step 3: Implement data models in `scifi/literature/models.py`**

Define dataclasses with serialization helpers (`to_dict`, `from_dict`), `generate_cite_key()`, and field validations.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_models.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/models.py tests/test_literature_models.py
git commit -m "feat(literature): add canonical data models for papers and graph sessions"
```

---

### Task 2: Graph-Scoped SQLite Knowledge Store (`scifi.literature.store`)

**Files:**
- Create: `scifi/literature/store.py`
- Test: `tests/test_literature_store.py`

**Interfaces:**
- Consumes: `scifi.literature.models.*`
- Produces: `LiteratureStore` class:
  - `__init__(db_path: str | Path)`
  - `create_or_get_graph(graph_id: str, title: str, seed_paper_id: str | None = None) -> GraphSessionRecord`
  - `save_paper(paper: PaperRecord, graph_id: str, node_role: str = 'intermediate') -> None`
  - `save_citation(citation: CitationRecord) -> None`
  - `get_graph_papers(graph_id: str) -> list[PaperRecord]`
  - `get_graph_citations(graph_id: str) -> list[CitationRecord]`
  - `execute_read_query(query_sql: str) -> list[dict]` (enforcing `SELECT` only)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_literature_store.py
import pytest
from pathlib import Path
from scifi.literature.models import PaperRecord, AuthorRecord, CitationRecord
from scifi.literature.store import LiteratureStore

def test_store_session_isolation_and_wal(tmp_path: Path):
    db_path = tmp_path / "test_literature.db"
    store = LiteratureStore(db_path)
    
    # Create two isolated graph sessions
    store.create_or_get_graph("graph-a", "Transformer Lineage")
    store.create_or_get_graph("graph-b", "Quantum Key Distribution")
    
    paper_a = PaperRecord(id="p-1", title="Attention Is All You Need", year=2017)
    paper_b = PaperRecord(id="p-2", title="BB84 Protocol", year=1984)
    
    store.save_paper(paper_a, graph_id="graph-a", node_role="seed")
    store.save_paper(paper_b, graph_id="graph-b", node_role="seed")
    
    papers_a = store.get_graph_papers("graph-a")
    papers_b = store.get_graph_papers("graph-b")
    
    assert len(papers_a) == 1
    assert papers_a[0].id == "p-1"
    assert len(papers_b) == 1
    assert papers_b[0].id == "p-2"

def test_read_only_query_blocks_mutations(tmp_path: Path):
    store = LiteratureStore(tmp_path / "test_sec.db")
    with pytest.raises(PermissionError):
        store.execute_read_query("DROP TABLE papers;")
    with pytest.raises(PermissionError):
        store.execute_read_query("INSERT INTO graphs (id, title) VALUES ('x', 'y');")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_store.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.literature.store'`

- [ ] **Step 3: Implement `LiteratureStore` in `scifi/literature/store.py`**

Implement database initialization using the Phase 1 schema from Section 5 of the spec. Enforce WAL mode, `busy_timeout=5000`, `sqlite3.set_authorizer` in `execute_read_query` allowing only `SQLITE_SELECT`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_store.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/store.py tests/test_literature_store.py
git commit -m "feat(literature): implement graph-scoped SQLite knowledge store with WAL and read-only authorizer"
```

---

### Task 3: Canonical Paper Resolver & Registry Client (`scifi.literature.resolver`)

**Files:**
- Create: `scifi/literature/resolver.py`
- Test: `tests/test_literature_resolver.py`

**Interfaces:**
- Consumes: OpenAlex / arXiv APIs, `scifi.literature.models.*`
- Produces: `PaperResolver` class:
  - `resolve_by_title(title: str) -> PaperRecord | None`
  - `resolve_by_doi(doi: str) -> PaperRecord | None`
  - `resolve_references(openalex_work_id: str, limit: int = 10) -> list[PaperRecord]`
  - `resolve_citations(openalex_work_id: str, limit: int = 10) -> list[PaperRecord]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_literature_resolver.py
from unittest.mock import patch, MagicMock
from scifi.literature.resolver import PaperResolver

@patch("scifi.literature.resolver.requests.get")
def test_resolve_by_title_openalex(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {
                "id": "https://openalex.org/W2741809807",
                "doi": "https://doi.org/10.48550/arxiv.1706.03762",
                "title": "Attention Is All You Need",
                "publication_year": 2017,
                "publication_date": "2017-06-12",
                "cited_by_count": 95000,
                "authorships": [
                    {"author": {"id": "https://openalex.org/A1", "display_name": "Ashish Vaswani"}}
                ],
                "open_access": {
                    "is_oa": True,
                    "oa_status": "green",
                    "oa_url": "https://arxiv.org/pdf/1706.03762",
                },
            }
        ]
    }
    mock_get.return_value = mock_resp
    
    resolver = PaperResolver()
    paper = resolver.resolve_by_title("Attention Is All You Need")
    assert paper is not None
    assert paper.title == "Attention Is All You Need"
    assert paper.year == 2017
    assert paper.citation_count == 95000
    assert len(paper.authors) == 1
    assert paper.authors[0].name == "Ashish Vaswani"
    assert paper.locations[0].oa_status == "green"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_resolver.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.literature.resolver'`

- [ ] **Step 3: Implement `PaperResolver` in `scifi/literature/resolver.py`**

Implement OpenAlex work lookup, identifier normalization, author parsing, abstract inverted index reconstruction fallback, and polite User-Agent headers.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_resolver.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/resolver.py tests/test_literature_resolver.py
git commit -m "feat(literature): add canonical paper resolver for OpenAlex and arXiv"
```

---

### Task 4: Multi-Signal Lineage Traversal & Cycle Detection (`scifi.literature.lineage`)

**Files:**
- Create: `scifi/literature/lineage.py`
- Test: `tests/test_literature_lineage.py`

**Interfaces:**
- Consumes: `PaperResolver`, `LiteratureStore`, `PaperRecord`, `CitationRecord`
- Produces: `LineageCrawler` class:
  - `crawl_lineage(query: str, depth: int = 2, max_papers: int = 25, graph_id: str | None = None) -> tuple[str, list[PaperRecord], list[CitationRecord]]`
  - `detect_and_rectify_cycles(papers: list[PaperRecord], citations: list[CitationRecord]) -> list[CitationRecord]`
  - `compute_topological_depths(papers: list[PaperRecord], citations: list[CitationRecord]) -> dict[str, int]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_literature_lineage.py
from scifi.literature.models import PaperRecord, CitationRecord
from scifi.literature.lineage import LineageCrawler

def test_detect_and_rectify_cycles():
    crawler = LineageCrawler(resolver=None, store=None)
    # A -> B (2017 -> 2018), but B -> A due to preprint revision
    p_a = PaperRecord(id="A", title="Paper A", year=2017)
    p_b = PaperRecord(id="B", title="Paper B", year=2018)
    
    citations = [
        CitationRecord(source_paper_id="B", target_paper_id="A"), # B cites A
        CitationRecord(source_paper_id="A", target_paper_id="B"), # circular back-edge
    ]
    
    rectified = crawler.detect_and_rectify_cycles([p_a, p_b], citations)
    # The back-edge violating chronology (A citing newer B) should be removed or marked
    valid_targets = [c.target_paper_id for c in rectified if c.source_paper_id == "A"]
    assert "B" not in valid_targets

def test_topological_depth_calculation():
    crawler = LineageCrawler(resolver=None, store=None)
    p_root = PaperRecord(id="R", title="Root", year=2010)
    p_mid = PaperRecord(id="M", title="Mid", year=2015)
    p_leaf = PaperRecord(id="L", title="Leaf", year=2020)
    
    citations = [
        CitationRecord(source_paper_id="M", target_paper_id="R"),
        CitationRecord(source_paper_id="L", target_paper_id="M"),
    ]
    
    depths = crawler.compute_topological_depths([p_root, p_mid, p_leaf], citations)
    assert depths["R"] == 0
    assert depths["M"] == 1
    assert depths["L"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_lineage.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.literature.lineage'`

- [ ] **Step 3: Implement `LineageCrawler` in `scifi/literature/lineage.py`**

Implement multi-signal ranking: backward foundational expansion based on citation count and influence; forward expansion based on annualized growth; Tarjan's SCC / cycle breaking using publication year hierarchy; and Kahn's topological depth calculation.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_lineage.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/lineage.py tests/test_literature_lineage.py
git commit -m "feat(literature): implement multi-signal lineage crawler with cycle rectification and topological depth"
```

---

### Task 5: XSS-Safe Standalone Vis.js HTML Visualizer (`scifi.literature.visualizer`)

**Files:**
- Create: `scifi/literature/visualizer.py`
- Test: `tests/test_literature_visualizer.py`

**Interfaces:**
- Consumes: `list[PaperRecord]`, `list[CitationRecord]`, `dict[str, int]` (depths)
- Produces: `render_interactive_html(graph_title: str, papers: list[PaperRecord], citations: list[CitationRecord], depths: dict[str, int]) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_literature_visualizer.py
from scifi.literature.models import PaperRecord, CitationRecord, AuthorRecord
from scifi.literature.visualizer import render_interactive_html

def test_render_interactive_html_xss_protection():
    malicious_title = "<script>alert('xss')</script> & Safe"
    paper = PaperRecord(
        id="p-xss",
        title=malicious_title,
        year=2023,
        authors=[AuthorRecord(id="a1", name="Hacker <foo@bar.com>")],
    )
    citations = []
    depths = {"p-xss": 0}
    
    html_output = render_interactive_html("Security Test", [paper], citations, depths)
    assert "<script>alert('xss')</script>" not in html_output
    assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in html_output or "\\u003cscript\\u003e" in html_output
    assert "vis.Network" in html_output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_visualizer.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.literature.visualizer'`

- [ ] **Step 3: Implement `render_interactive_html` in `scifi/literature/visualizer.py`**

Generate a self-contained HTML page embedding Vis.js (via CDN or bundled JS), applying strict `html.escape` and JSON data sanitization. Render a directed hierarchical layout (Left-to-Right by topological depth) with color-coded access tier badges and a slide-out paper details drawer.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_visualizer.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/visualizer.py tests/test_literature_visualizer.py
git commit -m "feat(literature): add XSS-safe standalone Vis.js interactive graph visualizer"
```

---

### Task 6: Structured Markdown Report & BibTeX Exporter (`scifi.literature.reporter`)

**Files:**
- Create: `scifi/literature/reporter.py`
- Test: `tests/test_literature_reporter.py`

**Interfaces:**
- Consumes: `list[PaperRecord]`, `list[CitationRecord]`, `dict[str, int]` (depths)
- Produces:
  - `generate_markdown_report(graph_title: str, papers: list[PaperRecord], citations: list[CitationRecord], depths: dict[str, int]) -> str`
  - `export_bibtex_entries(papers: list[PaperRecord]) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_literature_reporter.py
from scifi.literature.models import PaperRecord, AuthorRecord
from scifi.literature.reporter import generate_markdown_report, export_bibtex_entries

def test_generate_markdown_report_structure():
    paper = PaperRecord(
        id="p-1",
        title="Attention Is All You Need",
        year=2017,
        citation_count=90000,
        authors=[AuthorRecord(id="a1", name="Ashish Vaswani")],
    )
    depths = {"p-1": 0}
    report = generate_markdown_report("Attention Mechanism", [paper], [], depths)
    assert "# Literature Intelligence Report: Attention Mechanism" in report
    assert "## 1. Intellectual Evolution & Lineage" in report
    assert "Attention Is All You Need" in report
    assert "Ashish Vaswani" in report

def test_export_bibtex_sanitization():
    paper = PaperRecord(
        id="p-1",
        title="Deep Residual Learning",
        year=2016,
        authors=[AuthorRecord(id="a1", name="Kaiming He")],
    )
    bib = export_bibtex_entries([paper])
    assert "@article{He2016Deep," in bib
    assert "title = {Deep Residual Learning}" in bib
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_reporter.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.literature.reporter'`

- [ ] **Step 3: Implement report and BibTeX generation in `scifi/literature/reporter.py`**

Format topological timeline progression, summarize papers by role (Seed, Foundation, Frontier), and format clean standardized BibTeX citations.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_reporter.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/reporter.py tests/test_literature_reporter.py
git commit -m "feat(literature): implement markdown report synthesis and standardized BibTeX exporter"
```

---

### Task 7: CLI Subcommands & FastMCP Server Exposure

**Files:**
- Create: `scifi/literature/cli.py`
- Modify: `scifi/cli.py:70-130`
- Modify: `scifi/server.py:180-250`
- Test: `tests/test_literature_cli_server.py`

**Interfaces:**
- Consumes: `scifi.literature.*`
- Produces:
  - CLI commands: `scifi literature report <title>`, `scifi literature map <title>`, `scifi literature db <subcmd>`
  - FastMCP tools: `scifi_map_literature`, `scifi_query_store`, `scifi_export_bibtex`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_literature_cli_server.py
from unittest.mock import patch, MagicMock
from scifi.cli import create_parser
from scifi.server import scifi_map_literature, scifi_query_store, scifi_export_bibtex

def test_cli_parser_literature_subcommand():
    parser = create_parser()
    args = parser.parse_args(["literature", "report", "Attention Is All You Need", "--depth", "1"])
    assert args.command == "literature"
    assert args.lit_command == "report"
    assert args.query == "Attention Is All You Need"
    assert args.depth == 1

@patch("scifi.literature.lineage.LineageCrawler.crawl_lineage")
def test_mcp_map_literature_tool(mock_crawl, tmp_path):
    mock_crawl.return_value = ("test-graph", [], [])
    res = scifi_map_literature("Attention Is All You Need", depth=1, max_papers=5)
    assert res["status"] == "SUCCESS"
    assert "graph_id" in res
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_cli_server.py -v`  
Expected: FAIL with unrecognized command or import errors

- [ ] **Step 3: Implement CLI wiring and FastMCP server tools**

Create `scifi/literature/cli.py`, connect it into `scifi/cli.py`, and register FastMCP tools in `scifi/server.py` with error handling and read-only query protections.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_cli_server.py -v`  
Expected: PASS

- [ ] **Step 5: Run full test suite to guarantee zero regressions**

Run: `uv run pytest`  
Expected: All 168+ tests pass

- [ ] **Step 6: Commit**

```bash
git add scifi/literature/cli.py scifi/cli.py scifi/server.py tests/test_literature_cli_server.py
git commit -m "feat(literature): integrate literature CLI subcommands and FastMCP server tools"
```
