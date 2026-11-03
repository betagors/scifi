# SOTA Benchmark & Novelty Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build empirical benchmark evaluation tracking, metric condition modeling, SOTA leader determination, and visual/report delta analysis to cleanly separate "Most Influential Research" (citation-driven) from "Best-Performing Published Method" (benchmark-driven).

**Architecture:** Extend SQLite schema with 4 normalized benchmark tables (`benchmarks`, `evaluation_metrics`, `evaluation_conditions`, `benchmark_results`) linked to immutable `evidence` records for table/figure provenance. Ingest benchmark scores via pattern-based paper text mining and open leaderboard reconciliation. Implement deterministic `SotaEvaluator` ranking performance by optimization direction (`maximize` vs `minimize`), computing benchmark deltas ($\Delta_{\text{SOTA}}$), and classifying graph nodes into `foundational`, `frontier`, and `sota_leader`. Enrich Vis.js visualizer with gold SOTA badges and a drawer section; add Section 5 to Markdown reports; and wire crawler, CLI, and FastMCP tools end-to-end.

**Tech Stack:** Python 3.12, SQLite 3 (WAL mode), Requests, Vis.js Network, Pytest, FastMCP.

**Spec:** User feedback on citation vs SOTA distinction (separating influential research, recent frontier, and verified benchmark SOTA).

## Global Constraints
- Zero fabricated benchmarks, metrics, datasets, or scores.
- Every benchmark result must either link to an `EvidenceRecord` or have an explicit provenance source.
- Zero paid LLM API requirements for deterministic benchmark parsing and SOTA evaluation.
- Parameterized SQLite queries (`?` placeholders) with authorizer protection on read-only queries.
- Multi-layer XSS defense in visualizer: `html.escape` + safe Unicode JSON escaping (`\u003c`, `\u003e`, `\u0026`) + safe DOM `textContent`.
- Academic prose free of AI marketing clichés (*delve*, *pivotal*, *testament*, *tapestry*, *beacon*, *groundbreaking*).
- 100% test pass rate with zero regressions across the existing test suite.

## Review Focus
1. Metric Goal Inversion: Metrics with `goal="minimize"` (e.g., latency, perplexity, word error rate) must rank lower values as superior; `goal="maximize"` (accuracy, F1, BLEU) must rank higher values as superior.
2. Condition Disparity in Deltas: Performance deltas between papers must account for differing evaluation conditions (e.g. 0-shot vs fine-tuned) and note condition mismatches in reports.
3. Numeric Parsing Robustness: Percentage stripping (`88.5%` $\to$ `88.5`), variance notation (`92.3 ± 0.4` $\to$ `92.3`), and scale normalization must parse reliably without throwing exceptions.
4. Missing Evidence Gracefulness: Benchmark results without full table citations must degrade gracefully with fallback provenance labels without breaking visualizer or reporter.
5. Markdown Table & HTML Escaping: Benchmark names, condition strings, and metric values containing pipe characters (`|`) or HTML tags (`<`, `>`) must be strictly sanitized.

---

### Task 1: SOTA Benchmark Data Models (`scifi.literature.models`)

**Files:**
- Modify: `scifi/literature/models.py`
- Test: `tests/test_literature_models.py`

**Interfaces:**
- Consumes: Existing dataclass paradigms in `scifi/literature/models.py`.
- Produces: `BenchmarkRecord`, `EvaluationMetricRecord`, `EvaluationConditionRecord`, and `BenchmarkResultRecord` with `to_dict` / `from_dict`.

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_literature_models.py
from scifi.literature.models import (
    BenchmarkRecord,
    EvaluationMetricRecord,
    EvaluationConditionRecord,
    BenchmarkResultRecord,
)

def test_benchmark_models_serialization():
    bm = BenchmarkRecord(
        id="bm-humaneval",
        name="HumanEval",
        domain="Code Generation",
        canonical_url="https://paperswithcode.com/dataset/humaneval",
        description="Functional correctness of code synthesis",
    )
    metric = EvaluationMetricRecord(
        id="metric-pass-1",
        name="pass@1",
        goal="maximize",
        unit="%",
        description="Percentage of problems solved on first attempt",
    )
    cond = EvaluationConditionRecord(
        id="cond-0shot-greedy",
        name="0-shot Greedy",
        dataset_split="test",
        hardware="1x A100 GPU",
        notes="Temperature=0.0",
    )
    res = BenchmarkResultRecord(
        id="res-1",
        paper_id="paper-1",
        benchmark_id="bm-humaneval",
        metric_id="metric-pass-1",
        condition_id="cond-0shot-greedy",
        metric_value=85.4,
        is_sota=True,
        rank=1,
        evidence_id="ev-123",
        table_or_figure="Table 1",
        result_date="2024-05-01",
        provenance_source="author_reported",
    )

    d_bm = bm.to_dict()
    assert d_bm["name"] == "HumanEval"
    assert BenchmarkRecord.from_dict(d_bm).id == "bm-humaneval"

    d_metric = metric.to_dict()
    assert d_metric["goal"] == "maximize"
    assert EvaluationMetricRecord.from_dict(d_metric).unit == "%"

    d_cond = cond.to_dict()
    assert d_cond["dataset_split"] == "test"
    assert EvaluationConditionRecord.from_dict(d_cond).hardware == "1x A100 GPU"

    d_res = res.to_dict()
    assert d_res["metric_value"] == 85.4
    assert d_res["is_sota"] is True
    assert BenchmarkResultRecord.from_dict(d_res).table_or_figure == "Table 1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_models.py::test_benchmark_models_serialization -v`  
Expected: FAIL with `ImportError: cannot import name 'BenchmarkRecord'`

- [ ] **Step 3: Implement data models in `scifi/literature/models.py`**

Add `BenchmarkRecord`, `EvaluationMetricRecord`, `EvaluationConditionRecord`, and `BenchmarkResultRecord` with validation defaults (`goal in ("maximize", "minimize")`) and serialization. Export in `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_models.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/models.py tests/test_literature_models.py
git commit -m "feat(literature): add BenchmarkRecord, EvaluationMetricRecord, EvaluationConditionRecord, and BenchmarkResultRecord models"
```

---

### Task 2: SQLite Store Persistence for Benchmarks & Results (`scifi.literature.store`)

**Files:**
- Modify: `scifi/literature/store.py`
- Test: `tests/test_literature_store.py`

**Interfaces:**
- Consumes: Task 1 benchmark models.
- Produces: `save_benchmark`, `save_evaluation_metric`, `save_evaluation_condition`, `save_benchmark_result`, `get_paper_benchmark_results`, `get_graph_benchmark_results`, `get_graph_benchmarks`, `get_graph_metrics`, `get_graph_conditions`, and `get_sota_leaders`.

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_literature_store.py
from scifi.literature.models import (
    BenchmarkRecord,
    EvaluationMetricRecord,
    EvaluationConditionRecord,
    BenchmarkResultRecord,
    PaperRecord,
)
from scifi.literature.store import LiteratureStore

def test_store_saves_and_retrieves_benchmarks_and_results(tmp_path):
    store = LiteratureStore(tmp_path / "benchmarks_test.db")
    store.create_or_get_graph("g-bench", "Benchmark Test Graph")
    p = PaperRecord(id="p-sota-1", title="SOTA Model Paper", year=2024)
    store.save_paper(p, "g-bench", node_role="frontier")

    bm = BenchmarkRecord(id="bm-glue", name="GLUE", domain="NLP")
    metric = EvaluationMetricRecord(id="m-acc", name="Accuracy", goal="maximize", unit="%")
    cond = EvaluationConditionRecord(id="c-test", name="Test Set")
    res = BenchmarkResultRecord(
        id="res-01",
        paper_id="p-sota-1",
        benchmark_id="bm-glue",
        metric_id="m-acc",
        condition_id="c-test",
        metric_value=92.5,
        is_sota=True,
        rank=1,
    )

    store.save_benchmark(bm)
    store.save_evaluation_metric(metric)
    store.save_evaluation_condition(cond)
    store.save_benchmark_result(res)

    results = store.get_paper_benchmark_results("p-sota-1")
    assert len(results) == 1
    assert results[0].metric_value == 92.5
    assert results[0].is_sota is True

    graph_res = store.get_graph_benchmark_results("g-bench")
    assert "p-sota-1" in graph_res
    assert len(graph_res["p-sota-1"]) == 1

    graph_bms = store.get_graph_benchmarks("g-bench")
    assert "bm-glue" in graph_bms

    leaders = store.get_sota_leaders("bm-glue", "m-acc")
    assert len(leaders) == 1
    assert leaders[0].paper_id == "p-sota-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_store.py::test_store_saves_and_retrieves_benchmarks_and_results -v`  
Expected: FAIL with `AttributeError: 'LiteratureStore' object has no attribute 'save_benchmark'`

- [ ] **Step 3: Implement benchmark schema and store methods in `scifi/literature/store.py`**

Add DDL for `benchmarks`, `evaluation_metrics`, `evaluation_conditions`, and `benchmark_results` tables with indexed foreign keys. Implement upsert methods and graph-scoped getters.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_store.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/store.py tests/test_literature_store.py
git commit -m "feat(literature): implement SQLite persistence and query methods for benchmarks, metrics, and results"
```

---

### Task 3: Benchmark Ingestion & Pattern Mining Engine (`scifi.literature.benchmarks`)

**Files:**
- Create: `scifi/literature/benchmarks.py`
- Test: `tests/test_literature_benchmarks.py`

**Interfaces:**
- Consumes: `PaperRecord`, `EvidenceRecord`, Task 1 models.
- Produces: `BenchmarkExtractor` with `extract_reported_results(paper: PaperRecord, evidence_items: Optional[list[EvidenceRecord]] = None) -> list[tuple[BenchmarkRecord, EvaluationMetricRecord, EvaluationConditionRecord, BenchmarkResultRecord, EvidenceRecord]]`.
- Provides canonical catalog of standard academic benchmarks (ImageNet, GLUE, SQuAD, HumanEval, MMLU, GSM8K, BLEU, etc.) and metrics.

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_literature_benchmarks.py
from scifi.literature.benchmarks import BenchmarkExtractor
from scifi.literature.models import PaperRecord

def test_extract_reported_results_from_abstract():
    paper = PaperRecord(
        id="p-eval-1",
        title="Scaling Laws for Code Generation",
        year=2023,
        abstract="Our method achieves 73.4% pass@1 on HumanEval and 85.2 F1 on SQuAD under zero-shot evaluation.",
    )
    extractor = BenchmarkExtractor()
    extracted = extractor.extract_reported_results(paper)
    assert len(extracted) >= 2

    # Verify HumanEval extraction
    he_items = [item for item in extracted if item[0].name == "HumanEval"]
    assert len(he_items) == 1
    bm, metric, cond, res, ev = he_items[0]
    assert bm.domain == "Code Generation"
    assert metric.name == "pass@1"
    assert metric.goal == "maximize"
    assert res.metric_value == 73.4
    assert ev.evidence_type == "benchmark_claim"
    assert "73.4% pass@1 on HumanEval" in ev.extracted_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_benchmarks.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.literature.benchmarks'`

- [ ] **Step 3: Implement `BenchmarkExtractor` in `scifi/literature/benchmarks.py`**

Implement canonical benchmark dictionary with known aliases and regex parsers for scores, metrics, and condition markers. Create accompanying `EvidenceRecord` of type `benchmark_claim`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_benchmarks.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/benchmarks.py tests/test_literature_benchmarks.py
git commit -m "feat(literature): implement BenchmarkExtractor for mining benchmark claims and metrics from papers"
```

---

### Task 4: SOTA Evaluator & Frontier Distinction Engine (`scifi.literature.sota`)

**Files:**
- Create: `scifi/literature/sota.py`
- Test: `tests/test_literature_sota.py`

**Interfaces:**
- Consumes: Task 1 models, `PaperRecord`, `CitationRecord`.
- Produces: `SotaEvaluator` with `evaluate_sota_frontier(papers: list[PaperRecord], benchmark_results: list[BenchmarkResultRecord], metrics: dict[str, EvaluationMetricRecord]) -> SotaEvaluationReport`.
- Calculates performance deltas ($\Delta_{\text{SOTA}}$), identifies true benchmark SOTA winners vs high-citation baselines, and assigns enriched roles (`foundational`, `frontier`, `sota_leader`).

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_literature_sota.py
from scifi.literature.models import (
    BenchmarkRecord,
    BenchmarkResultRecord,
    EvaluationMetricRecord,
    PaperRecord,
)
from scifi.literature.sota import SotaEvaluator

def test_sota_evaluator_distinguishes_leader_from_high_citation():
    # Paper A: Seminal, 5000 citations, score 78.0
    p_a = PaperRecord(id="p-a", title="Seminal Transformer", year=2017, citation_count=5000)
    # Paper B: Frontier, 300 citations, score 84.0
    p_b = PaperRecord(id="p-b", title="Improved Attention", year=2022, citation_count=300)
    # Paper C: Recent SOTA, 15 citations, score 91.2
    p_c = PaperRecord(id="p-c", title="Novel Architecture", year=2024, citation_count=15)

    metric = EvaluationMetricRecord(id="m-acc", name="Accuracy", goal="maximize", unit="%")
    results = [
        BenchmarkResultRecord(id="r1", paper_id="p-a", benchmark_id="bm-1", metric_id="m-acc", metric_value=78.0),
        BenchmarkResultRecord(id="r2", paper_id="p-b", benchmark_id="bm-1", metric_id="m-acc", metric_value=84.0),
        BenchmarkResultRecord(id="r3", paper_id="p-c", benchmark_id="bm-1", metric_id="m-acc", metric_value=91.2),
    ]

    evaluator = SotaEvaluator()
    report = evaluator.evaluate_sota_frontier([p_a, p_b, p_c], results, {"m-acc": metric})

    assert report.sota_leader_paper_id == "p-c"
    assert report.high_citation_frontier_paper_id == "p-b"
    assert report.best_metric_value == 91.2
    delta = report.get_delta("p-c", "p-b")
    assert delta.absolute_delta == pytest.approx(7.2)
    assert delta.is_improvement is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_sota.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.literature.sota'`

- [ ] **Step 3: Implement `SotaEvaluator` in `scifi/literature/sota.py`**

Implement goal-aware ranking (`maximize` vs `minimize`), tie-breaking, delta calculation, and role tagging (`sota_leader`, `frontier`, `foundational`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_sota.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/sota.py tests/test_literature_sota.py
git commit -m "feat(literature): implement SotaEvaluator for goal-aware benchmark ranking and performance delta calculation"
```

---

### Task 5: Visualizer SOTA Highlights & Benchmark Drawer Section (`scifi.literature.visualizer`)

**Files:**
- Modify: `scifi/literature/visualizer.py`
- Test: `tests/test_literature_visualizer.py`

**Interfaces:**
- Consumes: `benchmark_results: Optional[dict[str, list[BenchmarkResultRecord]]] = None`, `benchmarks_map: Optional[dict[str, BenchmarkRecord]] = None`, `metrics_map: Optional[dict[str, EvaluationMetricRecord]] = None`.
- Produces: Enriched Vis.js HTML rendering nodes with gold borders/badges for SOTA leaders and an "Empirical Benchmark Performance & SOTA Results" section in the slide-out drawer.

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_literature_visualizer.py
from scifi.literature.models import (
    BenchmarkRecord,
    BenchmarkResultRecord,
    EvaluationMetricRecord,
    PaperRecord,
)
from scifi.literature.visualizer import generate_interactive_html

def test_visualizer_renders_sota_badge_and_benchmark_section():
    paper = PaperRecord(id="p-sota", title="Winning Method", year=2024)
    bm = BenchmarkRecord(id="bm-1", name="HumanEval", domain="Code")
    m = EvaluationMetricRecord(id="m-1", name="pass@1", goal="maximize", unit="%")
    res = BenchmarkResultRecord(
        id="r-1",
        paper_id="p-sota",
        benchmark_id="bm-1",
        metric_id="m-1",
        metric_value=88.5,
        is_sota=True,
        table_or_figure="Table 2",
    )

    html = generate_interactive_html(
        "Benchmark Map",
        [paper],
        [],
        {"p-sota": 1},
        benchmark_results={"p-sota": [res]},
        benchmarks_map={"bm-1": bm},
        metrics_map={"m-1": m},
    )

    assert "SOTA Leader" in html or "sota-badge" in html
    assert "Empirical Benchmark Performance" in html
    assert "HumanEval" in html
    assert "88.5%" in html
    assert "Table 2" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_visualizer.py::test_visualizer_renders_sota_badge_and_benchmark_section -v`  
Expected: FAIL with missing benchmark section or keyword arguments.

- [ ] **Step 3: Implement SOTA node highlight and drawer section in `scifi/literature/visualizer.py`**

Update node styling logic (gold border `#FFD700`, star/badge in label/title for papers holding SOTA results) and expand drawer template to render benchmark cards with safe DOM escaping.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_visualizer.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/visualizer.py tests/test_literature_visualizer.py
git commit -m "feat(literature): add SOTA node styling and benchmark drawer section to interactive visualizer"
```

---

### Task 6: Empirical Benchmark Leaderboard & Delta Reporting (`scifi.literature.reporter`)

**Files:**
- Modify: `scifi/literature/reporter.py`
- Test: `tests/test_literature_reporter.py`

**Interfaces:**
- Consumes: `benchmark_results: Optional[dict[str, list[BenchmarkResultRecord]]] = None`, `benchmarks_map`, `metrics_map`, `conditions_map`.
- Produces: Updated `generate_markdown_report` and `save_markdown_report` rendering Section 5: "Empirical Benchmark Evaluation & SOTA Frontier Leaderboard" with delta columns ($\Delta$) and condition specs.

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_literature_reporter.py
from scifi.literature.models import (
    BenchmarkRecord,
    BenchmarkResultRecord,
    EvaluationMetricRecord,
    EvaluationConditionRecord,
    PaperRecord,
)
from scifi.literature.reporter import generate_markdown_report

def test_report_includes_sota_benchmark_leaderboard_section():
    p_baseline = PaperRecord(id="p-base", title="Influential Baseline", year=2022, citation_count=500)
    p_sota = PaperRecord(id="p-sota", title="Novel SOTA Method", year=2024, citation_count=20)
    bm = BenchmarkRecord(id="bm-mmlu", name="MMLU", domain="Reasoning")
    metric = EvaluationMetricRecord(id="m-acc", name="5-shot Accuracy", goal="maximize", unit="%")
    cond = EvaluationConditionRecord(id="c-5s", name="5-shot")

    res_base = BenchmarkResultRecord(
        id="r-b",
        paper_id="p-base",
        benchmark_id="bm-mmlu",
        metric_id="m-acc",
        condition_id="c-5s",
        metric_value=70.0,
        is_sota=False,
    )
    res_sota = BenchmarkResultRecord(
        id="r-s",
        paper_id="p-sota",
        benchmark_id="bm-mmlu",
        metric_id="m-acc",
        condition_id="c-5s",
        metric_value=86.5,
        is_sota=True,
        table_or_figure="Table 1",
    )

    report = generate_markdown_report(
        "SOTA Evaluation",
        [p_baseline, p_sota],
        [],
        {"p-base": 0, "p-sota": 1},
        benchmark_results={"p-base": [res_base], "p-sota": [res_sota]},
        benchmarks_map={"bm-mmlu": bm},
        metrics_map={"m-acc": metric},
        conditions_map={"c-5s": cond},
    )

    assert "## 5. Empirical Benchmark Evaluation & SOTA Leaderboard" in report
    assert "MMLU" in report
    assert "+16.5%" in report or "16.5" in report
    assert "Novel SOTA Method" in report
    assert "Table 1" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_reporter.py::test_report_includes_sota_benchmark_leaderboard_section -v`  
Expected: FAIL with missing Section 5 or unexpected arguments.

- [ ] **Step 3: Implement Section 5 formatting in `scifi/literature/reporter.py`**

Format Section 5 with markdown table comparing SOTA Leader vs Baseline Frontier across benchmarks and metrics, calculating performance deltas, displaying evaluation conditions, and escaping table cells.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_reporter.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/reporter.py tests/test_literature_reporter.py
git commit -m "feat(literature): add Empirical Benchmark Leaderboard and SOTA performance delta section to markdown report"
```

---

### Task 7: Lineage Traversal, CLI & FastMCP Tool Integration (`scifi.literature.lineage`, `cli.py`, `server.py`)

**Files:**
- Modify: `scifi/literature/lineage.py`
- Modify: `scifi/literature/cli.py`
- Modify: `scifi/server.py`
- Test: `tests/test_literature_cli_server.py`

**Interfaces:**
- Consumes: Tasks 1-6 modules.
- Produces:
  - `LineageCrawler.crawl_lineage(..., extract_benchmarks=True)` extracting and persisting benchmark results.
  - CLI `scifi literature report` and `map` reporting benchmark counts and SOTA leaders.
  - FastMCP tool `scifi_map_literature` returning `"sota_leaders"` and `"benchmark_results_count"`.
  - New FastMCP tool `scifi_query_sota_benchmarks` for direct benchmark inspection.

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_literature_cli_server.py
from scifi.server import scifi_map_literature, scifi_query_sota_benchmarks

def test_mcp_map_literature_with_benchmark_intelligence():
    res = scifi_map_literature("Attention Is All You Need", depth=1, max_papers=3)
    assert res["status"] == "SUCCESS"
    assert "benchmark_results_count" in res
    assert "sota_leaders" in res

def test_mcp_query_sota_benchmarks():
    res = scifi_query_sota_benchmarks(query="HumanEval")
    assert "benchmarks" in res
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_literature_cli_server.py::test_mcp_map_literature_with_benchmark_intelligence -v`  
Expected: FAIL with `AssertionError: assert 'benchmark_results_count' in res` or missing function.

- [ ] **Step 3: Wire benchmark extraction and SOTA evaluation across crawler, CLI, and FastMCP server**

Update `LineageCrawler`, `cli.py`, and `server.py` to invoke `BenchmarkExtractor` and `SotaEvaluator`, persist results to store, and pass them to visualizer and reporter.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_literature_cli_server.py -v`  
Expected: PASS

- [ ] **Step 5: Run full test suite to guarantee zero regressions**

Run: `uv run pytest`  
Expected: All 314+ tests pass.

- [ ] **Step 6: Commit**

```bash
git add scifi/literature/lineage.py scifi/literature/cli.py scifi/server.py tests/test_literature_cli_server.py
git commit -m "feat(literature): integrate SOTA benchmark intelligence across lineage crawler, CLI, and FastMCP server"
```
