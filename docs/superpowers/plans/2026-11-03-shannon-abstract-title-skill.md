# Shannon — Academic Title, Abstract & Keyword Optimization Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `shannon` skill, agent persona, empirical keyword/title validation script (`test_keywords.py`), and test suite for publication-grade title engineering, 5-beat cognitive dual-audience abstracts, and search-optimized (SEO) indexing metadata.

**Architecture:** A dual-layer system combining an LLM cognitive protocol (`skills/shannon/SKILL.md`) with a deterministic empirical validation script (`skills/shannon/scripts/test_keywords.py`). The script evaluates manuscript abstracts and titles against a 100-point Reviewer Triage Rubric, tests academic SEO visibility hacks (snippet truncation, keyphrase front-loading, 3-beat anchoring), checks accessibility and sentence complexity for non-technical readers, measures title-keyword redundancy, and optionally performs live title collision detection against OpenAlex/Crossref APIs.

**Tech Stack:** Python 3.12+, `pytest`, `urllib.request` (zero external dependencies for API lookups), standard library `re`, `json`, `argparse`, `difflib`.

**Spec:** [docs/superpowers/specs/2026-11-02-shannon-abstract-title-skill-design.md](file:///C:/Users/Betagors/.gemini/antigravity/worktrees/scifi/support_all_ai_tools/docs/superpowers/specs/2026-11-02-shannon-abstract-title-skill-design.md)

## Global Constraints

- Python >= 3.12 compatibility.
- Zero mandatory external API keys or heavy proprietary database dependencies.
- Zero tolerance for synthetic AI tropes (*delve*, *pivotal*, *testament*, *tapestry*, *seamless*, *groundbreaking*) or em dashes (—).
- Abstract length strictly targeted to 150–220 words.
- Title length targeted to 10–14 words (<120 characters) with primary keyphrase front-loaded in the first 65 characters.
- Non-redundancy rule: Keywords must not duplicate non-stop words present in the title.
- Academic SEO tricks: Keyphrase anchoring across Beat 1, Beat 3, and Beat 5; sweet-spot length; acronym defense.
- Dual-audience accessibility: Beat 1 must introduce context accessible to non-technical/interdisciplinary readers; flag sentences > 35 words.
- Deterministic scoring: Reviewer triage score must produce exact reproducible outputs for fixed inputs.
- Graceful offline fallback: Network failure or lack of `--live` flag must never crash `test_keywords.py`.

## Review Focus

1. **Title with punctuation or symbols (e.g. colons, hyphens, parentheses):** Word count and character length calculations must strip punctuation correctly without truncating valid hyphenated terms.
2. **Abstracts with formatted numbers, exponents, or percentages (e.g. `98.5%`, `3.2 \times 10^{-4}`, `4.2 dB`):** Experimental quantification regex must match standard scientific notations without false negatives.
3. **Keyword phrases with multiple words (e.g., `"deep reinforcement learning"`):** Overlap and density checks must handle both single-word and multi-word keyphrases cleanly.
4. **Sentences with excessive length (>35 words) or dense jargon in opening sentence:** Accessibility auditor must detect cognitive overload and flag run-on sentences.
5. **Academic SEO checks (Keyphrase in first 65 characters, anchoring across beats):** SEO validator must correctly identify whether the main topic appears before character 65 and is represented in opening, methodology, and conclusion.

---

### Task 1: Core Parsing, Overlap, Density, and Accessibility Metrics

**Files:**
- Create: `skills/shannon/scripts/test_keywords.py`
- Create: `tests/test_shannon.py`

**Interfaces:**
- Consumes: Standard library (`re`, `collections`, `typing`)
- Produces:
  - `normalize_token(word: str) -> str`
  - `tokenize(text: str) -> list[str]`
  - `compute_title_keyword_overlap(title: str, keywords: list[str]) -> dict`
  - `compute_abstract_keyword_density(abstract: str, keywords: list[str]) -> dict`
  - `evaluate_accessibility(abstract: str) -> dict`

- [ ] **Step 1: Write the failing tests for tokenization, overlap, density, and accessibility**

In `tests/test_shannon.py`:
```python
import pytest
from skills.shannon.scripts.test_keywords import (
    compute_title_keyword_overlap,
    compute_abstract_keyword_density,
    evaluate_accessibility,
    tokenize,
)

def test_title_keyword_overlap_detects_redundancy():
    title = "Adaptive Federated Learning for Edge Computing under Latency Constraints"
    keywords = ["federated learning", "edge computing", "privacy preservation", "stochastic optimization"]
    result = compute_title_keyword_overlap(title, keywords)
    assert result["overlap_ratio"] > 0.0
    assert "federated" in result["overlapping_words"]
    assert "edge" in result["overlapping_words"]

def test_title_keyword_overlap_zero_when_distinct():
    title = "Adaptive Resource Allocation under Strict Latency Constraints"
    keywords = ["federated learning", "differential privacy", "edge nodes"]
    result = compute_title_keyword_overlap(title, keywords)
    assert result["overlap_ratio"] == 0.0
    assert len(result["overlapping_words"]) == 0

def test_abstract_keyword_density_counts_and_flags():
    abstract = (
        "We propose federated learning across edge devices. "
        "Our federated learning framework optimizes transmission latency. "
        "Evaluations show federated learning achieves convergence."
    )
    keywords = ["federated learning", "differential privacy"]
    result = compute_abstract_keyword_density(abstract, keywords)
    assert result["densities"]["federated learning"]["count"] == 3
    assert result["densities"]["federated learning"]["status"] == "OPTIMAL"
    assert result["densities"]["differential privacy"]["count"] == 0
    assert result["densities"]["differential privacy"]["status"] == "OMITTED"

def test_evaluate_accessibility_flags_runon_sentences():
    long_sentence = " ".join(["word"] * 40) + "."
    normal_sentence = "This is a concise opening sentence explaining the practical context."
    res = evaluate_accessibility(long_sentence)
    assert res["has_runon_sentences"] is True
    assert res["max_sentence_length"] == 40

    res_normal = evaluate_accessibility(normal_sentence)
    assert res_normal["has_runon_sentences"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_shannon.py -k "test_title_keyword_overlap or test_abstract_keyword_density or test_evaluate_accessibility"`
Expected: FAIL (ModuleNotFoundError: No module named 'skills.shannon')

- [ ] **Step 3: Implement tokenization, overlap, density, and accessibility metrics**

In `skills/shannon/scripts/test_keywords.py`:
Implement stop words list, token normalization (lowercasing, punctuation stripping, lightweight suffix stemming), `tokenize()`, `compute_title_keyword_overlap()`, `compute_abstract_keyword_density()`, and `evaluate_accessibility()` (sentence splitting, sentence lengths, run-on detection >35 words).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_shannon.py -k "test_title_keyword_overlap or test_abstract_keyword_density or test_evaluate_accessibility"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/shannon/scripts/test_keywords.py tests/test_shannon.py
git commit -m "feat(shannon): implement parsing, overlap, density, and accessibility metrics"
```

---

### Task 2: Academic SEO & Visibility Engine and 100-Point Reviewer Triage Rubric

**Files:**
- Modify: `skills/shannon/scripts/test_keywords.py`
- Modify: `tests/test_shannon.py`

**Interfaces:**
- Consumes: Task 1
- Produces:
  - `evaluate_academic_seo(title: str, abstract: str, keywords: list[str]) -> dict`
  - `score_snippet_readability(title: str) -> dict` (20 pts)
  - `score_gap_precision(abstract: str) -> dict` (20 pts)
  - `score_algorithmic_specificity(abstract: str) -> dict` (20 pts)
  - `score_experimental_quantification(abstract: str) -> dict` (20 pts)
  - `score_style_and_debiasing(title: str, abstract: str) -> dict` (20 pts)
  - `evaluate_triage_score(title: str, abstract: str, keywords: list[str]) -> dict` (Total 100 pts)

- [ ] **Step 1: Write failing tests for SEO engine and 100-point rubric**

In `tests/test_shannon.py`:
```python
from skills.shannon.scripts.test_keywords import (
    evaluate_academic_seo,
    evaluate_triage_score,
)

def test_evaluate_academic_seo_frontloading_and_anchoring():
    # Good SEO: keyphrase in first 65 chars, 10-14 words, keyphrase in lead, middle, end
    title = "Decentralized Beamforming for Distributed Satellite Clusters under Doppler Constraints"
    abstract = (
        "Low Earth orbit satellite constellations rely on decentralized beamforming for inter-satellite links. "
        "However, high orbital velocities cause severe Doppler shifts that degrade synchronization. "
        "We introduce an adaptive decentralized beamforming algorithm using Riemannian manifold optimization. "
        "Simulations demonstrate a 4.2 dB signal-to-noise ratio gain and 28.5% lower phase drift. "
        "These results confirm that decentralized beamforming enables scalable satellite networking."
    )
    keywords = ["satellite constellations", "Doppler shift", "Riemannian manifold", "phase drift"]
    seo = evaluate_academic_seo(title, abstract, keywords)
    assert seo["front_loaded"] is True
    assert seo["sweet_spot_length"] is True
    assert seo["three_beat_anchoring"] is True
    assert len(seo["seo_hacks_applied"]) >= 3

def test_triage_score_penalizes_ai_tropes_and_em_dashes():
    title = "Delving into Deep Learning: A Pivotal Paradigm"
    abstract = (
        "It is crucial to note that this paper serves as a testament to deep learning — "
        "we delve into pivotal architectures to explore a rich tapestry of neural models."
    )
    keywords = ["deep learning", "neural networks"]
    res = evaluate_triage_score(title, abstract, keywords)
    assert res["scores"]["style_debiasing"]["points"] < 5
    assert "em_dash" in res["scores"]["style_debiasing"]["penalties"]
    assert "delve" in res["scores"]["style_debiasing"]["flagged_words"]

def test_triage_score_awards_clean_quantified_abstract():
    title = "Decentralized Beamforming for Distributed Satellite Clusters under Doppler Constraints"
    abstract = (
        "Low Earth orbit satellite constellations require coordinated beamforming. "
        "However, severe Doppler shift and propagation delays limit existing distributed algorithms. "
        "We formulate an adaptive synchronization algorithm based on Riemannian manifold optimization. "
        "Simulations demonstrate a 4.2 dB signal-to-noise ratio improvement and 28.5% reduction in phase drift "
        "compared to conventional gradient descent. "
        "These results enable real-time inter-satellite coordination under dynamic orbital geometry."
    )
    keywords = ["satellite constellations", "Doppler shift", "Riemannian manifold", "phase drift"]
    res = evaluate_triage_score(title, abstract, keywords)
    assert res["total_score"] >= 85
    assert res["scores"]["gap_precision"]["points"] >= 18
    assert res["scores"]["algorithmic_specificity"]["points"] >= 18
    assert res["scores"]["experimental_quantification"]["points"] >= 18
    assert res["scores"]["style_debiasing"]["points"] == 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_shannon.py -k "test_evaluate_academic_seo or test_triage_score"`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement SEO evaluation and 100-point rubric**

In `skills/shannon/scripts/test_keywords.py`:
- `evaluate_academic_seo`:
  - `front_loaded`: Checks if topic words appear in first 65 chars of title.
  - `sweet_spot_length`: Title contains 10–14 words (and 70–110 chars).
  - `three_beat_anchoring`: Checks keyphrase representation in first 2 sentences (lead), middle sentences (method), and final sentence (implication).
  - `acronym_check`: Flags standalone abbreviations in title.
  - Generates list of applied hacks and actionable tips.
- Subscores for the 100-point Rubric:
  - `score_snippet_readability`: Title word count, character length, keyphrase front-loading.
  - `score_gap_precision`: Contrastive discourse markers (*however, remains limited, bottleneck, unaddressed*).
  - `score_algorithmic_specificity`: Concrete technical terms (*algorithm, framework, formulation, manifold, matrix*).
  - `score_experimental_quantification`: Numerical values, percentages, error bounds, physical units (`%`, `dB`, `ms`, `fps`, `speedup`).
  - `score_style_and_debiasing`: Deductions for em dashes, first-person singular, banned AI tropes, and accessibility run-on sentences.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_shannon.py -k "test_evaluate_academic_seo or test_triage_score"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/shannon/scripts/test_keywords.py tests/test_shannon.py
git commit -m "feat(shannon): implement Academic SEO engine and 100-point triage rubric"
```

---

### Task 3: Title Collision & Live Search Diagnostics (OpenAlex & Crossref)

**Files:**
- Modify: `skills/shannon/scripts/test_keywords.py`
- Modify: `tests/test_shannon.py`

**Interfaces:**
- Consumes: Standard library `urllib.request`, `json`, `difflib.SequenceMatcher`
- Produces:
  - `compute_title_similarity(candidate: str, existing: str) -> float`
  - `query_openalex_titles(title: str, limit: int = 5) -> list[dict]`
  - `query_crossref_titles(title: str, limit: int = 5) -> list[dict]`
  - `check_title_collision(title: str, live: bool = False) -> dict`
  - `check_keyword_relevance(keywords: list[str], live: bool = False) -> dict`

- [ ] **Step 1: Write failing tests for similarity and mocked live search**

In `tests/test_shannon.py`:
```python
from unittest.mock import patch
from skills.shannon.scripts.test_keywords import (
    compute_title_similarity,
    check_title_collision,
    check_keyword_relevance,
)

def test_title_similarity_computation():
    t1 = "Federated Learning for Edge Computing under Latency Constraints"
    t2 = "Federated Learning for Edge Computing with Latency Constraints"
    t3 = "Deep Reinforcement Learning for Autonomous Drone Navigation"
    assert compute_title_similarity(t1, t2) > 0.85
    assert compute_title_similarity(t1, t3) < 0.40

def test_title_collision_offline_mode():
    result = check_title_collision("Adaptive Beamforming for Satellites", live=False)
    assert result["status"] == "SKIPPED_OFFLINE"

def test_title_collision_mocked_openalex_response():
    mock_payload = {
        "results": [
            {"title": "Adaptive Beamforming for Low Earth Orbit Satellites", "cited_by_count": 42, "publication_year": 2023}
        ]
    }
    with patch("skills.shannon.scripts.test_keywords.fetch_json_url", return_value=mock_payload):
        res = check_title_collision("Adaptive Beamforming for Low Earth Orbit Satellites", live=True)
        assert res["risk_level"] in ("MODERATE OVERLAP", "HIGH COLLISION")
        assert len(res["matches"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_shannon.py -k "test_title_similarity or test_title_collision"`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement similarity metric and HTTP search client**

In `skills/shannon/scripts/test_keywords.py`:
- `compute_title_similarity`: Uses normalized token matching and `SequenceMatcher`.
- `fetch_json_url`: Polite HTTP fetcher with User-Agent and timeout (3.0s).
- `query_openalex_titles`: Queries `https://api.openalex.org/works?search={title}&per_page={limit}`.
- `query_crossref_titles`: Fallback query to `https://api.crossref.org/works?query.title={title}&rows={limit}`.
- `check_title_collision`: Categorizes risk (<0.60 LOW RISK, 0.60–0.85 MODERATE OVERLAP, >0.85 HIGH COLLISION).
- `check_keyword_relevance`: Retrieves top venues and paper counts for candidate keywords.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_shannon.py -k "test_title_similarity or test_title_collision"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/shannon/scripts/test_keywords.py tests/test_shannon.py
git commit -m "feat(shannon): implement title collision and live search engine checks"
```

---

### Task 4: CLI Formatting, SEO Report Card, and Exit Codes

**Files:**
- Modify: `skills/shannon/scripts/test_keywords.py`
- Modify: `tests/test_shannon.py`

**Interfaces:**
- Consumes: Tasks 1–3
- Produces:
  - `generate_diagnostic_report(evaluation: dict) -> str`
  - `run_cli(args: list[str]) -> int`
  - `main() -> int`

- [ ] **Step 1: Write failing CLI integration tests**

In `tests/test_shannon.py`:
```python
import json
from skills.shannon.scripts.test_keywords import run_cli

def test_cli_json_output(capsys):
    args = [
        "--title", "Decentralized Beamforming for Distributed Satellite Clusters under Doppler Constraints",
        "--abstract", "Satellite networks require coordination. However, existing schemes fail under high latency. We formulate an algorithm achieving 3.5 dB gain. This enables robust links.",
        "--keywords", "satellite clusters, beamforming, latency constraints",
        "--json"
    ]
    exit_code = run_cli(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "triage_score" in data
    assert "seo" in data
    assert "accessibility" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_shannon.py -k "test_cli_json_output"`
Expected: FAIL (ImportError: cannot import name 'run_cli')

- [ ] **Step 3: Implement CLI interface and terminal formatter**

In `skills/shannon/scripts/test_keywords.py`:
- `argparse` with `--title`, `--abstract`, `--keywords`, `--target-venue`, `--live`, `--json`.
- Terminal report renderer featuring:
  - Reviewer Triage Scorecard (Breakdown of 5 subscores).
  - Academic SEO & Visibility Hacks Scorecard (Keyphrase front-loading, sweet-spot length, 3-beat anchoring).
  - Dual-Audience Accessibility Card (Run-on sentences, readability flags).
  - Vocabulary Overlap & Density table.
  - Live Search Diagnostics (Collision risk, subfield relevance).
- `run_cli` and `if __name__ == "__main__": sys.exit(main())`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_shannon.py -k "test_cli_json_output"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/shannon/scripts/test_keywords.py tests/test_shannon.py
git commit -m "feat(shannon): add CLI report formatting with SEO & accessibility diagnostics"
```

---

### Task 5: Skill Instructions (`SKILL.md`) and Agent Persona (`shannon.md`)

**Files:**
- Create: `skills/shannon/SKILL.md`
- Create: `agents/shannon.md`
- Modify: `commands/sf.md`
- Modify: `commands/sf.toml`
- Modify: `rules/AGENTS.md`
- Modify: `README.md`
- Modify: `plugin.json`

**Interfaces:**
- Consumes: `skills/shannon/scripts/test_keywords.py`
- Produces:
  - Antigravity / Claude Code skill documentation conforming to `writing-skills` standards.
  - Subagent persona for `shannon`.
  - CLI command aliases and rule updates.

- [ ] **Step 1: Write `skills/shannon/SKILL.md`**

Following the enhanced generative protocol:
- Step 1: Raw research note extraction (including broad context for non-technical readers).
- Step 2: 3 Title Structural Angles with front-loaded keyphrase and 10–14 word citation sweet-spot.
- Step 3: 5-Beat Dual-Audience Abstract structure:
  - Beat 1: Lay-accessible real-world context.
  - Beat 2: Specific technical gap.
  - Beat 3: Rigorous algorithmic mechanism.
  - Beat 4: Quantified benchmark results.
  - Beat 5: Practical system-level impact.
  - Academic SEO "Rule of Three" keyphrase anchoring.
- Step 4: Controlled vocabulary & non-redundant keyword selection (5–7 terms, zero overlap with title).
- Step 5: Verification using `uv run python skills/shannon/scripts/test_keywords.py`.

- [ ] **Step 2: Write `agents/shannon.md`**

Define the `shannon` subagent persona with system prompt, specialized instructions, accessibility rules, and SEO tricks.

- [ ] **Step 3: Update `rules/AGENTS.md`, `README.md`, and `plugin.json`**

Document `shannon` in the scientific writing rules, quickstart tables, and plugin capabilities.

- [ ] **Step 4: Run full test suite and verify clean execution**

Run: `uv run pytest tests/test_shannon.py -v`
Run: `uv run python skills/shannon/scripts/test_keywords.py --help`
Expected: All tests pass and CLI displays help documentation without error.

- [ ] **Step 5: Commit**

```bash
git add skills/shannon/ agents/shannon.md rules/AGENTS.md README.md plugin.json commands/
git commit -m "feat(shannon): add Shannon skill, subagent persona, SEO hacks, and documentation"
```
