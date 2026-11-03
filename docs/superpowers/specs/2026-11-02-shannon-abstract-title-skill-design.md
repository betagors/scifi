# Design Document: Shannon — Academic Title, Abstract & Keyword Optimization Engine

## 1. Intent & Context
In scientific publishing (IEEE, Elsevier, Springer Nature, ACM), manuscripts must pass three major front-line filters before reaching detailed peer review and achieving high post-publication readership:

1. **Automated Indexing & Academic Search Engine Optimization (SEO)**:
   - Manuscript management systems (Aries Editorial Manager for Elsevier, Clarivate ScholarOne for IEEE, SNAPP for Springer Nature) use automated reviewer-matching engines (Reviewer Discovery, Reviewer Locator) driven by keyword extraction, BM25, and semantic embeddings.
   - Search engines (Google Scholar, Scopus, Web of Science, IEEE Xplore, ScienceDirect) rank papers based on title keyphrase placement, snippet truncation (first 60–65 characters), keyphrase density anchoring across abstract sections, and keyword metadata coverage.
2. **Reviewer Cognition & 30-Second Triage**:
   - During the paper bidding phase, invited reviewers decide whether to accept or decline a review invitation within 30 to 60 seconds based solely on the Title and Abstract.
   - Editors-in-Chief desk-reject papers that exhibit typical red flags: vague claims, lack of quantified experimental evidence, or synthetic AI writing tropes (*delve*, *pivotal*, *testament*, *tapestry*).
3. **Dual-Audience Accessibility (The Non-Technical / Interdisciplinary Reader)**:
   - Modern research is increasingly interdisciplinary. Journal editors, program committee members from adjacent tracks, industrial practitioners, and policy/grant evaluators may not be deep specialists in the author's micro-subfield.
   - Abstracts that jump immediately into dense, unexplained mathematical jargon or unanchored subfield assumptions alienate broad readers and editors, leading to desk rejection or missed citation opportunities.

The `shannon` skill provides an automated, empirically validated engine to transform raw research notes, experimental results, and draft findings into publication-grade title options, a 5-beat cognitive-load optimized abstract accessible to broad readers while rigorous for experts, and an engineered academic SEO and keyword strategy tested against real academic search databases.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- **Raw-to-Package Generation**: Ingest unstructured experimental notes, contribution bullets, and target publisher/venue; produce 3 title angles, a 5-beat structured abstract, and 5–7 engineered keywords.
- **Academic SEO & Visibility Engineering (Tricks & Hacks)**:
  - **Front-Loading Rule**: Anchor primary domain keywords within the first 65 characters (before search snippet/tab truncation in Google Scholar and browser tabs).
  - **The 10–14 Word Sweet-Spot**: Target optimal length (10–14 words, 70–110 characters) correlated with higher citation velocity.
  - **"Rule of Three" Keyphrase Anchoring**: Check that the primary search keyphrase appears naturally 2–4 times across the abstract (anchored in Beat 1 lead, Beat 3 method, and Beat 5 implication) to maximize BM25 indexing without stuffing.
  - **Title Acronym Guard**: Flag obscure abbreviations in titles that depress search traffic; ensure standard terms accompany novel framework names.
  - **Metadata Vocabulary Expansion**: Ensure author keywords do not duplicate title words, effectively doubling the paper's searchable indexing footprint across Scopus/WoS/IEEE.
- **Dual-Audience Readability & Cognitive Accessibility**:
  - **Beat 1 Lay-Accessible Problem Hook**: Ground the research problem in concrete physical/practical context that an interdisciplinary reader or non-technical editor can immediately grasp.
  - **Cognitive Load & Jargon Control**: Flag sentences exceeding 35 words; compute readability metrics (sentence complexity, readability index) to ensure accessibility without sacrificing technical rigor.
  - **Beat 5 Practical Implication**: Articulate clear real-world or system-level payoff rather than insular mathematical trivialities.
- **5-Beat Cognitive Abstract**:
  - Beat 1: Broad Problem Context & Motivation (1–2 sentences, accessible, no hype).
  - Beat 2: Specific Technical Bottleneck (1 sentence, exact gap in existing work).
  - Beat 3: Proposed Method / Mechanism (2–3 sentences, core architectural or algorithmic innovation).
  - Beat 4: Quantified Experimental Findings (2 sentences, exact benchmark numbers, % gains, error margins vs. specific modern baselines).
  - Beat 5: Practical Impact & Theoretical Implication (1 sentence, real-world utility and cross-disciplinary scope).
- **Empirical Search Engine Validation Tool (`test_keywords.py`)**:
  - Query live academic databases (OpenAlex API as primary, Crossref API as fallback) with zero authentication required.
  - Validate keyword search volume and relevance (inspect top retrieved papers to verify target subfield alignment).
  - Check candidate titles for near-duplicate collisions in existing literature using string distance metrics.
  - Measure abstract keyphrase density (target: 2–4 natural repetitions of primary terms).
  - Calculate title-keyword non-redundancy ratio.
  - Output an **Academic SEO & Visibility Breakdown** alongside the **Reviewer Triage Scorecard**.
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
- Never permit banned AI-marker vocabulary (*delve*, *pivotal*, *testament*, *tapestry*) or em dashes (—).
- Never allow an abstract so hyper-specialized that a general engineering/scientific editor cannot understand what problem is being solved.

---

## 3. Architecture & Technical Design

### 3.1 Directory Structure
```
skills/shannon/
  ├── SKILL.md                     # Core prompt instructions, SEO hacks, accessibility rules, and triage protocols
  └── scripts/
      └── test_keywords.py         # Empirical search engine validator, SEO auditor, and readability evaluator
agents/
  └── shannon.md                   # SciFi agent persona for title/abstract/indexing optimization
tests/
  └── test_shannon.py              # Unit tests for scoring, SEO checks, accessibility, overlap, and collision
```

### 3.2 Search Engine & Indexing Validator (`test_keywords.py`)
- **Execution**: `uv run python skills/shannon/scripts/test_keywords.py --title "..." --abstract "..." --keywords "k1, k2, k3" [--target-venue ieee|elsevier|springer] [--live]`
- **Modules / Responsibilities**:
  1. **Title-Keyword Non-Redundancy & Expansion Ratio**:
     - Tokenizes title and keywords, strips stop words and stemming.
     - Calculates vocabulary expansion ratio. Flags redundant keywords that duplicate title words.
  2. **Abstract Keyphrase Density & 3-Beat Anchoring**:
     - Measures repetition frequency of primary keywords in the abstract (optimal: 2–4 occurrences; flags stuffing >5 or omissions =0).
     - Checks if primary keyphrase is anchored across opening (Beat 1), mechanism (Beat 3), and conclusion (Beat 5).
  3. **Readability & Accessibility Check**:
     - Measures sentence lengths; penalizes run-on sentences (>35 words).
     - Evaluates lead sentence (Beat 1) accessibility and technical jargon density.
  4. **Academic SEO & Visibility Hacks Audit**:
     - Front-loading check: Primary keyphrase located in first 65 chars of title.
     - Sweet-spot length: Title has 10–14 words (70–110 characters).
     - Acronym audit: Flags isolated, undefined acronyms in title.
     - Dual-audience clarity: Checks presence of clear application/context terms.
  5. **Deterministic Reviewer Triage Scorecard (100 Points)**:
     - **Snippet Readability & SEO (20 pts)**: Length in 10–14 words, keyphrase in first 65 chars, no trailing period.
     - **Gap Precision (20 pts)**: Detects explicit contrastive discourse markers (*however*, *remains limited*, *fails to*, *bottleneck*, *unaddressed*).
     - **Algorithmic Specificity (20 pts)**: Detects concrete computational/structural descriptors (*algorithm*, *framework*, *formulation*, *complexity*, *convergence*).
     - **Experimental Quantification (20 pts)**: Scans for numbers, percentages, error bounds, and physical/computational units.
     - **Style, Accessibility & AI-De-biasing (20 pts)**: Zero em dashes, zero AI tropes, no run-on sentences, accessible lead sentence.
  6. **Decoupled Live Search Engine Diagnostics (OpenAlex & Crossref)**:
     - **Title Collision**: Queries OpenAlex works API with Crossref fallback. Flags LOW RISK (<0.60), MODERATE OVERLAP (0.60–0.85), or HIGH COLLISION (>0.85).
     - **Keyword Hit Relevance**: Queries OpenAlex for candidate keywords to verify target scientific subfield.

### 3.3 Generative Protocol (`SKILL.md`)
- **Step 1: Information Extraction**: Extracts Core Problem, Novel Mechanism, Benchmark Data, Quantitative Gains, and Target Audience/Application from user notes.
- **Step 2: Title Generation Matrix (Applying Academic SEO Hacks)**:
  - Enforces front-loading primary keyphrase in first 65 chars.
  - Enforces 10–14 word citation sweet spot.
  - Angle A (Declarative / Finding-First): *"[Primary Finding] via [Novel Mechanism] for [Application]"*
  - Angle B (Descriptive / Method-First): *"[Novel Mechanism]: [Methodology] for [Application] under [Constraint]"*
  - Angle C (Problem / Challenge-First): *"[Problem Challenge] in [Domain]: A [Mechanism] Approach"*
- **Step 3: 5-Beat Dual-Audience Abstract Drafting**:
  - Strictly 150–220 words.
  - Beat 1 accessible to non-specialists; Beat 3 rigorous for domain reviewers; Beat 5 highlights practical payoff.
  - Keyphrase anchored 2–4 times across Beats 1, 3, and 5.
  - Zero em dashes, zero AI tropes.
- **Step 4: Non-Redundant Keyword Expansion Strategy**:
  - Select 5–7 keywords that deliberately do not duplicate title words (capturing long-tail searches on Scopus/IEEE).
- **Step 5: Search Validation & SEO Diagnostics Run**:
  - Runs `test_keywords.py` to confirm search engine behavior, output the 100-point triage score, SEO checklist, and live collision report.
