# Design Document: Shannon — Academic Title, Abstract & Keyword Optimization Engine

## 1. Intent & Context
In scientific publishing (IEEE, Elsevier, Springer Nature, ACM), manuscripts must pass two major front-line filters before reaching detailed peer review:
1. **Automated Indexing & Editorial Discovery Algorithms**:
   - Manuscript management systems (Aries Editorial Manager for Elsevier, Clarivate ScholarOne for IEEE, SNAPP for Springer Nature) use automated reviewer-matching engines (Reviewer Discovery, Reviewer Locator) driven by keyword extraction, BM25, and semantic embeddings.
   - Search engines (Google Scholar, Scopus, Web of Science, IEEE Xplore, ScienceDirect) rank papers based on title keyphrase placement, snippet truncation (first 60–65 characters), and keyword metadata coverage.
2. **Reviewer Cognition & 30-Second Triage**:
   - During the paper bidding phase, invited reviewers decide whether to accept or decline a review invitation within 30 to 60 seconds based solely on the Title and Abstract.
   - Editors-in-Chief desk-reject papers that exhibit typical red flags: vague claims, lack of quantified experimental evidence, or synthetic AI writing tropes (*delve*, *pivotal*, *testament*, *tapestry*).

The `shannon` skill provides an automated, empirically validated engine to transform raw research notes, experimental results, and draft findings into publication-grade title options, a 5-beat cognitive-load optimized abstract, and an engineered keyword strategy tested against real academic search databases.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- **Raw-to-Package Generation**: Ingest unstructured experimental notes, contribution bullets, and target publisher/venue; produce 3 title angles, a 5-beat structured abstract, and 5–7 engineered keywords.
- **Title Engineering**:
  - Front-load primary domain keywords within the first 65 characters (before search snippet/tab truncation).
  - Target the optimal length band (10–14 words, <120 characters) correlated with higher discovery and citations.
  - Provide 3 distinct structural angles: Declarative (Result/Finding-First), Descriptive (Methodology/System-First), and Problem-Oriented (Challenge/Solution).
- **5-Beat Cognitive Abstract**:
  - Beat 1: Context & Domain Problem (1–2 sentences, neutral, no grandiosity).
  - Beat 2: Specific Technical Gap (1 sentence, exact bottleneck in existing work).
  - Beat 3: Proposed Method / Mechanism (2–3 sentences, core algorithmic or architectural innovation).
  - Beat 4: Quantified Experimental Findings (2 sentences, exact benchmark numbers, % gains, error margins vs. specific modern baselines).
  - Beat 5: Scope & Implication (1 sentence, practical or theoretical significance).
- **Complementary Keyword Strategy**:
  - Generate 5–7 keywords that deliberately do **not** duplicate words present in the chosen title.
  - Prompt instructions guide mapping to publisher controlled vocabularies (IEEE Thesaurus, Inspec, Ei Compendex, MeSH).
- **Empirical Search Engine Validation Tool (`test_keywords.py`)**:
  - Query live academic databases (OpenAlex API as primary, Crossref API as fallback) with zero authentication required.
  - Validate keyword search volume and relevance (inspect top retrieved papers to verify target subfield alignment).
  - Check candidate titles for near-duplicate collisions in existing literature using string distance metrics.
  - Measure abstract keyphrase density (target: 2–4 natural repetitions of primary terms).
  - Calculate title-keyword non-redundancy ratio.
- **Reviewer Triage Scorecard & Search Diagnostics**:
  - Output an objective 100-point rubric assessing: Snippet Readability (20 pts), Gap Precision (20 pts), Algorithmic Specificity (20 pts), Experimental Quantification (20 pts), and Style/AI-De-biasing (20 pts).
  - Provide a decoupled Search Engine & Indexing Diagnostics report (Title Collision Risk, Vocabulary Overlap %, and Live Search Hit Relevance).
- **SciFi Toolkit Integration**:
  - Provide `skills/shannon/SKILL.md`.
  - Provide `skills/shannon/scripts/test_keywords.py` (runnable with `uv run`).
  - Provide `agents/shannon.md` subagent configuration.
  - Provide comprehensive test suite in `tests/test_shannon.py`.
  - Update `rules/AGENTS.md`, `README.md`, and `plugin.json`.

### Non-Goals
- Full manuscript generation (Sections 1–6 belong to the author or other skills).
- Rewriting full manuscript bodies (handled by `human`).
- Paid API keys or private database scrapers (relies on open, reliable academic APIs: OpenAlex and Crossref).

### Anti-Goals
- Never produce clickbait or unsubstantiated titles that over-promise and lead to reviewer backlash during Section 4/5 evaluation.
- Never generate generic abstracts with empty qualifiers (*"shows remarkable improvements"*, *"outperforms prior art"*) without concrete metrics.
- Never waste author keyword slots on exact copies of words already in the title.
- Never permit banned AI-marker vocabulary or em dashes.

---

## 3. Approaches Considered & Selected

- **Approach 1: Dual-Layer Skill with Real-Time Search Validation Script (SELECTED)**:
  - Generative protocol in `SKILL.md` combined with an executable Python tool `test_keywords.py` using OpenAlex & Crossref APIs to test search relevance, title collisions, and keyword saturation.
  - *Trade-off*: Adds a lightweight script dependency, but provides empirical validation against live publisher indexing databases.
- **Approach 2: Pure In-Prompt LLM Protocol (REJECTED)**:
  - Prompt instructions only, relying on the model's internal memory or generic web search.
  - *Trade-off*: Simpler to write, but incapable of programmatic keyword saturation checks, exact metadata overlap calculation, or automated title collision scoring.

---

## 4. Architecture & Technical Design

### 4.1 Directory Structure
```
skills/shannon/
  ├── SKILL.md                     # Core prompt instructions, publisher rubrics, and triage protocols
  └── scripts/
      └── test_keywords.py         # Empirical search engine validator and metadata auditor
agents/
  └── shannon.md                   # SciFi agent persona for title/abstract/indexing optimization
tests/
  └── test_shannon.py              # Unit tests for scoring, keyword overlap, collision, and API parsers
```

### 4.2 Search Engine & Indexing Validator (`test_keywords.py`)
- **Execution**: `uv run python skills/shannon/scripts/test_keywords.py --title "..." --abstract "..." --keywords "k1, k2, k3" [--target-venue ieee|elsevier|springer] [--live]`
- **Modules / Responsibilities**:
  1. **Title-Keyword Non-Redundancy**:
     - Tokenizes title and keywords, strips stop words and stemming.
     - Calculates vocabulary overlap ratio. Flags redundant keywords that waste index slots.
  2. **Abstract Keyphrase Density**:
     - Measures repetition frequency of primary keywords in the abstract (optimal: 2–4 occurrences; flags stuffing >5 or omissions =0).
  3. **Deterministic Reviewer Triage Scorecard (100 Points)**:
     - **Snippet Readability (20 pts)**: Length within 10–14 words, core topic in first 65 chars, appropriate punctuation.
     - **Gap Precision (20 pts)**: Detects explicit contrastive discourse markers in Beat 2 (*"however"*, *"remains limited"*, *"fails to"*, *"bottleneck"*, *"unaddressed"*, *"trade-off"*).
     - **Algorithmic Specificity (20 pts)**: Detects concrete computational/structural descriptors (*"algorithm"*, *"framework"*, *"formulation"*, *"complexity"*, *"convergence"*, *"optimization"*, *"layer"*, *"matrix"*).
     - **Experimental Quantification (20 pts)**: Scans for numbers, percentages, error bounds, and physical/computational units (e.g., `%`, `dB`, `ms`, `FLOPS`, `accuracy`, `speedup`).
     - **Style & AI-De-biasing (20 pts)**: Full credit if clean; deducts heavily for em dashes (—), first-person pronouns, and AI marker vocabulary (*delve*, *pivotal*, *testament*, *tapestry*, *seamless*, *groundbreaking*).
  4. **Decoupled Live Search Engine Diagnostics (OpenAlex & Crossref)**:
     - **Title Collision**: Queries OpenAlex works API (`https://api.openalex.org/works?search={title}&per_page=5`) with Crossref as fallback. Computes token-set ratio / Levenshtein similarity to existing papers. Flags:
       - LOW RISK (<0.60)
       - MODERATE OVERLAP (0.60–0.85)
       - HIGH COLLISION (>0.85 — risk of duplicate/near-duplicate).
     - **Keyword Hit Relevance**: Queries OpenAlex for candidate keywords. Retrieves top 3 publication venues and top cited titles to verify that the query maps to the intended scientific community.
     - **Network Fallback**: If offline, `--live` omitted, or API times out, gracefully outputs local diagnostics with a clear notice.

### 4.3 Generative Protocol (`SKILL.md`)
- **Step 1: Information Extraction**: Extracts Core Problem, Novel Mechanism, Benchmark Data, and Quantitative Gains from user notes.
- **Step 2: Title Generation Matrix**:
  - Angle A (Declarative / Finding-First): *"[Primary Finding] via [Novel Mechanism] for [Application]"*
  - Angle B (Descriptive / Method-First): *"[Novel Mechanism]: [Methodology] for [Application] under [Constraint]"*
  - Angle C (Problem / Challenge-First): *"[Problem Challenge] in [Domain]: A [Mechanism] Approach"*
- **Step 3: 5-Beat Abstract Drafting**:
  - Strictly 150–220 words.
  - Zero em dashes, zero AI tropes.
  - Explicit metrics in Beat 4 (e.g., *"achieves a 23.4% reduction in inference latency and 4.2 dB SNR gain"*).
- **Step 4: Controlled Vocabulary & Keyword Allocation**:
  - Uses prompt knowledge of IEEE Thesaurus, Inspec, and MeSH to select 5–7 standard indexing terms.
  - Verified non-overlapping with title words.
- **Step 5: Search Validation Run**:
  - Runs `test_keywords.py` to confirm search engine behavior, output the 100-point triage score, and display the live search diagnostic report.

---

## 5. Builder Calls & Resolved Design Decisions
1. **Controlled Vocabulary Mapping**: Handled via prompt instructions in `SKILL.md` (leveraging LLM knowledge of IEEE Thesaurus, Inspec, and MeSH) rather than bundling a multi-megabyte proprietary database in the repository.
2. **Deterministic Semantic Scoring**: Gap Precision and Algorithmic Specificity are evaluated via robust discourse-marker and syntactic token lists in `test_keywords.py` so unit tests execute deterministically without external LLM calls.
3. **API Architecture**: OpenAlex is the primary search and metadata endpoint (rich topic and citation metadata), with Crossref serving as a secondary failover.
4. **Decoupled Diagnostics**: The 100-point Reviewer Triage Score evaluates internal manuscript prose and formatting, while the live search checks (Collision Risk, Keyword Coverage, Index Hits) are presented as an empirical companion diagnostic.
