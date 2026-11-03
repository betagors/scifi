# Research Evidence Intelligence (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Phase 2 (Research Evidence Intelligence): Semantic Scholar citation context ingestion, first-class evidence provenance registry, paywall-resilient limitation and unstated assumption extraction, multi-source corroboration triage, slide-out evidence drawer in Vis.js, and an evidence-backed Delta-Novelty Matrix in synthesis reports.

**Architecture:** Extends `scifi.literature` with new models (`models.py`), store persistence methods (`store.py`), Semantic Scholar client (`semantic_scholar.py`), 4-stage evidence and gap triage pipeline (`gaps.py`), and integrates evidence into the visualizer (`visualizer.py`), reporter (`reporter.py`), lineage crawler (`lineage.py`), CLI, and FastMCP server.

**Tech Stack:** Python 3.10+, SQLite3 (WAL mode), requests, Vis.js (embedded), pytest.

**Spec:** `docs/superpowers/specs/2026-11-03-literature-state-of-art-tool-design.md`

---

## Global Constraints

- Python compatibility: 3.10+ compatible type annotations and syntax.
- Evidence-first rule: Never present an inferred limitation as a fact without linking to an `evidence` record with exact quote, source section, and reporting paper attribution.
- No mandatory paid API keys: Semantic Scholar context queries run opportunistically with graceful fallback if unauthenticated or rate-limited.
- Strict XSS defense: All extracted evidence quotes and reporting paper details must be sanitized via `html.escape` and safe JSON encoding before embedding in Vis.js HTML templates.
- Markdown formatting: Tables must escape cell pipes (`\|`) to preserve formatting.

---

## Review Focus

1. **Semantic Scholar rate limits (HTTP 429 / timeouts):** Must degrade gracefully without crashing the crawl, falling back to reconstructed abstract limitation parsing.
2. **Attribution integrity on citation contexts:** When Paper B cites Paper A saying "Paper A requires high compute", the limitation must be attributed to Paper A, with Paper B marked as the reporting source.
3. **Corroboration counting:** Two independent citing papers mentioning the same limitation must upgrade status from `candidate` to `corroborated` without duplicating gap records.
4. **XSS in raw citation sentences:** Citation context quotes containing math notation (e.g. `<` or `>`) or HTML entities must not break HTML or script contexts in the slide-out drawer.
5. **Zero regressions on Phase 1 features:** Existing CLI commands and FastMCP tools must continue to pass all 268 tests.

---

## Task Structure

### Task 1: Evidence, Citation Context & Gap Data Models (`scifi.literature.models`)

**Files:**
- Modify: `scifi/literature/models.py`
- Test: `tests/test_literature_models.py`

**Interfaces:**
- Consumes: Standard library `dataclasses`, `typing`.
- Produces:
  - `CitationContextRecord`: id (str), source_paper_id (str), target_paper_id (str), context_text (str), section_name (str | None), intent (str | None), is_influential (bool)
  - `EvidenceRecord`: id (str), paper_id (str), reporting_paper_id (str | None), evidence_type (str), source_section (str | None), source_location (str | None), extracted_text (str), extraction_method (str), confidence (float | None), retrieved_at (str | None)
  - `PaperGapRecord`: id (str), paper_id (str), gap_type (str), claim_summary (str), primary_evidence_id (str), verification_status (str = 'candidate'), corroborating_count (int = 0), contradicting_count (int = 0)

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_literature_models.py
from scifi.literature.models import CitationContextRecord, EvidenceRecord, PaperGapRecord

def test_evidence_and_gap_records():
    ev = EvidenceRecord(
        id="ev-1",
        paper_id="p-target",
        reporting_paper_id="p-source",
        evidence_type="citation_context",
        source_section="Related Work",
        extracted_text="Although Method A reduces latency, it assumes static nodes.",
        extraction_method="semantic_scholar_api",
        confidence=None,
    )
    assert ev.id == "ev-1"
    assert ev.confidence is None
    assert ev.evidence_type == "citation_context"

    gap = PaperGapRecord(
        id="gap-1",
        paper_id="p-target",
        gap_type="unstated_assumption",
        claim_summary="Assumes static network topology",
        primary_evidence_id="ev-1",
        verification_status="candidate",
        corroborating_count=1,
    )
    assert gap.verification_status == "candidate"
    assert gap.gap_type == "unstated_assumption"
    assert gap.to_dict()["primary_evidence_id"] == "ev-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_models.py::test_evidence_and_gap_records -v`  
Expected: FAIL with `ImportError: cannot import name 'CitationContextRecord'`

- [ ] **Step 3: Implement data models in `scifi/literature/models.py`**

Define `CitationContextRecord`, `EvidenceRecord`, and `PaperGapRecord` dataclasses with `to_dict()` and `from_dict()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_models.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/models.py tests/test_literature_models.py
git commit -m "feat(literature): add data models for citation contexts, evidence, and research gaps"
```

---

### Task 2: Store Persistence for Evidence & Gaps (`scifi.literature.store`)

**Files:**
- Modify: `scifi/literature/store.py`
- Test: `tests/test_literature_store.py`

**Interfaces:**
- Consumes: `CitationContextRecord`, `EvidenceRecord`, `PaperGapRecord`
- Produces:
  - `save_citation_context(context: CitationContextRecord) -> None`
  - `save_evidence(evidence: EvidenceRecord) -> None`
  - `save_paper_gap(gap: PaperGapRecord) -> None`
  - `get_paper_evidence(paper_id: str) -> list[EvidenceRecord]`
  - `get_paper_gaps(paper_id: str) -> list[PaperGapRecord]`
  - `get_citation_contexts(source_id: str, target_id: str) -> list[CitationContextRecord]`

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_literature_store.py
from scifi.literature.models import EvidenceRecord, PaperGapRecord, CitationContextRecord

def test_store_evidence_and_gap_persistence(tmp_path):
    db_path = tmp_path / "test_evidence.db"
    store = LiteratureStore(db_path)
    store.create_or_get_graph("g-1", "Test Graph")
    
    ev = EvidenceRecord(
        id="ev-1",
        paper_id="p-1",
        reporting_paper_id="p-2",
        evidence_type="citation_context",
        source_section="Related Work",
        extracted_text="Method A scales quadratically with sequence length.",
        extraction_method="semantic_scholar_api",
    )
    store.save_evidence(ev)
    
    gap = PaperGapRecord(
        id="gap-1",
        paper_id="p-1",
        gap_type="computational_complexity",
        claim_summary="Scales quadratically with sequence length",
        primary_evidence_id="ev-1",
        verification_status="corroborated",
        corroborating_count=2,
    )
    store.save_paper_gap(gap)
    
    retrieved_ev = store.get_paper_evidence("p-1")
    retrieved_gaps = store.get_paper_gaps("p-1")
    
    assert len(retrieved_ev) == 1
    assert retrieved_ev[0].extracted_text == ev.extracted_text
    assert len(retrieved_gaps) == 1
    assert retrieved_gaps[0].verification_status == "corroborated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_store.py::test_store_evidence_and_gap_persistence -v`  
Expected: FAIL with `AttributeError: 'LiteratureStore' object has no attribute 'save_evidence'`

- [ ] **Step 3: Implement persistence methods in `scifi/literature/store.py`**

Add CRUD methods for `evidence`, `paper_gaps`, and `citation_contexts` within context-managed transactions.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_store.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/store.py tests/test_literature_store.py
git commit -m "feat(literature): add SQLite persistence for evidence provenance and research gaps"
```

---

### Task 3: Semantic Scholar Citation Context Client (`scifi.literature.semantic_scholar`)

**Files:**
- Create: `scifi/literature/semantic_scholar.py`
- Test: `tests/test_literature_semantic_scholar.py`

**Interfaces:**
- Consumes: `scifi.literature.models.CitationContextRecord`
- Produces: `SemanticScholarClient` class:
  - `__init__(api_key: str | None = None, timeout: int = 10, cache: Any = None)`
  - `get_paper_citations_with_contexts(paper_id_or_doi: str, limit: int = 25) -> list[CitationContextRecord]`
  - `get_paper_metadata(paper_id_or_doi: str) -> dict | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_literature_semantic_scholar.py
from unittest.mock import patch, MagicMock
from scifi.literature.semantic_scholar import SemanticScholarClient

@patch("scifi.literature.semantic_scholar.requests.get")
def test_get_citation_contexts(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {
                "citingPaper": {"paperId": "S2-SRC-1", "title": "Citing Paper", "year": 2024},
                "contexts": ["Although Method X achieves high accuracy, its memory overhead is prohibitive."],
                "intents": ["methodology"],
                "isInfluential": True,
            }
        ]
    }
    mock_get.return_value = mock_resp
    
    client = SemanticScholarClient()
    contexts = client.get_paper_citations_with_contexts("DOI:10.1234/test")
    assert len(contexts) == 1
    assert contexts[0].source_paper_id == "S2-SRC-1"
    assert "memory overhead is prohibitive" in contexts[0].context_text
    assert contexts[0].intent == "methodology"
    assert contexts[0].is_influential is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_semantic_scholar.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.literature.semantic_scholar'`

- [ ] **Step 3: Implement `SemanticScholarClient` in `scifi/literature/semantic_scholar.py`**

Implement S2 Graph API client with query formatting (`DOI:...` or arXiv ID), timeout and HTTP 429 exponential backoff, and mapping to `CitationContextRecord`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_semantic_scholar.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/semantic_scholar.py tests/test_literature_semantic_scholar.py
git commit -m "feat(literature): add Semantic Scholar citation context client with rate-limit resilience"
```

---

### Task 4: 4-Stage Gap Extraction & Corroboration Engine (`scifi.literature.gaps`)

**Files:**
- Create: `scifi/literature/gaps.py`
- Test: `tests/test_literature_gaps.py`

**Interfaces:**
- Consumes: `PaperRecord`, `CitationContextRecord`, `EvidenceRecord`, `PaperGapRecord`
- Produces: `GapExtractor` class:
  - `extract_abstract_gaps(paper: PaperRecord) -> list[tuple[EvidenceRecord, PaperGapRecord]]`
  - `extract_citation_context_gaps(target_paper: PaperRecord, contexts: list[CitationContextRecord]) -> list[tuple[EvidenceRecord, PaperGapRecord]]`
  - `corroborate_gaps(gaps_with_evidence: list[tuple[EvidenceRecord, PaperGapRecord]]) -> list[tuple[EvidenceRecord, PaperGapRecord]]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_literature_gaps.py
from scifi.literature.models import PaperRecord, CitationContextRecord
from scifi.literature.gaps import GapExtractor

def test_extract_abstract_and_corroborate_citation_gaps():
    extractor = GapExtractor()
    paper = PaperRecord(
        id="p-target",
        title="Scalable Coordination",
        year=2021,
        abstract="We propose a coordination algorithm. However, this method assumes full channel state information.",
    )
    
    # 1. Abstract extraction
    abstract_results = extractor.extract_abstract_gaps(paper)
    assert len(abstract_results) >= 1
    ev_abs, gap_abs = abstract_results[0]
    assert gap_abs.gap_type == "unstated_assumption"
    assert "channel state information" in gap_abs.claim_summary
    
    # 2. Inbound citation extraction
    contexts = [
        CitationContextRecord(
            id="c1",
            source_paper_id="p-src-1",
            target_paper_id="p-target",
            context_text="While Scalable Coordination performs well, it assumes full channel knowledge, limiting deployment.",
        ),
        CitationContextRecord(
            id="c2",
            source_paper_id="p-src-2",
            target_paper_id="p-target",
            context_text="Unlike Scalable Coordination, which requires full channel knowledge, our method uses partial states.",
        ),
    ]
    citation_results = extractor.extract_citation_context_gaps(paper, contexts)
    assert len(citation_results) >= 1
    
    # 3. Corroboration triage
    all_results = extractor.corroborate_gaps(abstract_results + citation_results)
    corroborated = [g for _, g in all_results if g.verification_status == "corroborated"]
    assert len(corroborated) >= 1
    assert corroborated[0].corroborating_count >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_gaps.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.literature.gaps'`

- [ ] **Step 3: Implement `GapExtractor` in `scifi/literature/gaps.py`**

Implement deterministic regex/linguistic triage rules detecting:
- `computational_complexity`: "complexity", "scales as", "prohibitive", "expensive", "memory bound"
- `unstated_assumption`: "assumes", "relies on assumption", "only holds in", "under ideal"
- `empirical_limitation`: "fails to", "degrades under", "limited to", "bottleneck", "narrow evaluation"
- `unresolved_problem`: "remains open", "future work", "unresolved challenge"
Implement clustering by gap type and key phrase similarity to increment `corroborating_count`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_gaps.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/gaps.py tests/test_literature_gaps.py
git commit -m "feat(literature): implement 4-stage evidence-based research gap extraction and corroboration"
```

---

### Task 5: Slide-Out Evidence Drawer in Vis.js Visualizer (`scifi.literature.visualizer`)

**Files:**
- Modify: `scifi/literature/visualizer.py`
- Test: `tests/test_literature_visualizer.py`

**Interfaces:**
- Consumes: `papers`, `citations`, `depths`, `paper_gaps: dict[str, list[PaperGapRecord]]`, `evidence: dict[str, EvidenceRecord]`
- Produces: Updated `render_interactive_html` and `save_interactive_html` embedding evidence and gap data safely into the HTML drawer.

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_literature_visualizer.py
from scifi.literature.models import PaperRecord, PaperGapRecord, EvidenceRecord
from scifi.literature.visualizer import render_interactive_html

def test_visualizer_renders_evidence_drawer_safely():
    paper = PaperRecord(id="p-1", title="Paper One", year=2022)
    ev = EvidenceRecord(
        id="ev-1",
        paper_id="p-1",
        reporting_paper_id="p-2",
        evidence_type="citation_context",
        source_section="Related Work",
        extracted_text="Paper One requires O(N^2) memory <script>alert('xss')</script>",
        extraction_method="semantic_scholar_api",
    )
    gap = PaperGapRecord(
        id="gap-1",
        paper_id="p-1",
        gap_type="computational_complexity",
        claim_summary="Quadratic memory complexity",
        primary_evidence_id="ev-1",
        verification_status="corroborated",
        corroborating_count=2,
    )
    
    html = render_interactive_html(
        "Evidence Test",
        [paper],
        [],
        {"p-1": 0},
        paper_gaps={"p-1": [gap]},
        evidence_map={"ev-1": ev},
    )
    assert "Extracted Technical Gaps" in html
    assert "Quadratic memory complexity" in html
    assert "corroborated" in html
    assert "<script>alert('xss')</script>" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_visualizer.py::test_visualizer_renders_evidence_drawer_safely -v`  
Expected: FAIL with unexpected keyword argument or missing content.

- [ ] **Step 3: Implement evidence drawer in `scifi/literature/visualizer.py`**

Update HTML template and JS drawer builder to render a collapsible "Technical Limitations & Gaps" section with verification badges (`candidate`, `corroborated`), reporting paper citations, and sanitized quotes.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_visualizer.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/visualizer.py tests/test_literature_visualizer.py
git commit -m "feat(literature): integrate evidence provenance and corroborated gaps into visualizer drawer"
```

---

### Task 6: Delta-Novelty Matrix & Evidence Reporting (`scifi.literature.reporter`)

**Files:**
- Modify: `scifi/literature/reporter.py`
- Test: `tests/test_literature_reporter.py`

**Interfaces:**
- Consumes: `papers`, `citations`, `depths`, `paper_gaps: dict[str, list[PaperGapRecord]]`, `evidence: dict[str, EvidenceRecord]`
- Produces: Updated `generate_markdown_report` and `save_markdown_report` synthesizing Section 3 (Delta-Novelty Matrix) and Section 4 (Traceable Limitations with quotes).

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_literature_reporter.py
from scifi.literature.models import PaperRecord, PaperGapRecord, EvidenceRecord
from scifi.literature.reporter import generate_markdown_report

def test_report_includes_delta_novelty_matrix_and_evidence():
    paper = PaperRecord(id="p-1", title="Seminal Method", year=2018)
    ev = EvidenceRecord(
        id="ev-1",
        paper_id="p-1",
        extracted_text="Seminal Method assumes static topology and unbounded compute.",
        evidence_type="citation_context",
        extraction_method="semantic_scholar_api",
    )
    gap = PaperGapRecord(
        id="gap-1",
        paper_id="p-1",
        gap_type="unstated_assumption",
        claim_summary="Assumes static topology",
        primary_evidence_id="ev-1",
        verification_status="corroborated",
        corroborating_count=2,
    )
    
    report = generate_markdown_report(
        "Evidence Synthesis",
        [paper],
        [],
        {"p-1": 0},
        paper_gaps={"p-1": [gap]},
        evidence_map={"ev-1": ev},
    )
    assert "## 3. Evidence-Backed Delta-Novelty Matrix" in report
    assert "Proposed Approach (Yours)" in report
    assert "## 4. Traceable Limitations & Research Opportunities" in report
    assert "Seminal Method assumes static topology" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_reporter.py::test_report_includes_delta_novelty_matrix_and_evidence -v`  
Expected: FAIL with missing sections or unexpected arguments.

- [ ] **Step 3: Implement Delta-Novelty Matrix and Evidence Sections in `scifi/literature/reporter.py`**

Format Delta-Novelty comparison table and evidence breakdown section.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_reporter.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/reporter.py tests/test_literature_reporter.py
git commit -m "feat(literature): add Delta-Novelty Matrix and traceable limitation sections to markdown report"
```

---

### Task 7: Full Lineage & CLI/MCP Pipeline Integration (`scifi.literature.lineage`, `cli.py`, `server.py`)

**Files:**
- Modify: `scifi/literature/lineage.py`
- Modify: `scifi/literature/cli.py`
- Modify: `scifi/server.py`
- Test: `tests/test_literature_cli_server.py`

**Interfaces:**
- Consumes: All Phase 2 modules.
- Produces:
  - `LineageCrawler.crawl_lineage(..., extract_gaps=True)` automatically extracting and storing evidence & gaps.
  - CLI `scifi literature report` and `scifi literature map` outputting gap counts and evidence metrics.
  - FastMCP tool `scifi_map_literature` returning gap summary counts and findings.

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_literature_cli_server.py
from scifi.server import scifi_map_literature

def test_mcp_map_literature_with_evidence_extraction():
    res = scifi_map_literature("Attention Is All You Need", depth=1, max_papers=3)
    assert res["status"] == "SUCCESS"
    assert "gaps_count" in res
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_cli_server.py::test_mcp_map_literature_with_evidence_extraction -v`  
Expected: FAIL with `AssertionError: assert 'gaps_count' in res`

- [ ] **Step 3: Wire evidence and gap pipeline into crawler, CLI, and FastMCP server**

Update `LineageCrawler`, `cli.py`, and `server.py` to trigger `GapExtractor` and pass evidence to visualizer and reporter.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_cli_server.py -v`  
Expected: PASS

- [ ] **Step 5: Run full test suite to guarantee zero regressions**

Run: `uv run pytest`  
Expected: All 268+ tests pass

- [ ] **Step 6: Commit**

```bash
git add scifi/literature/lineage.py scifi/literature/cli.py scifi/server.py tests/test_literature_cli_server.py
git commit -m "feat(literature): integrate research evidence intelligence across crawler, CLI, and FastMCP"
```
