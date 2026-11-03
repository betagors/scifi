# Design Specification: Literature Lineage, State of the Art & Gap Intelligence Tool (Revision 2)

**Status:** Revised Specification (Ready for Approval)  
**Date:** 2026-11-03  
**Target Package:** `scifi.literature`  
**Command / Interface:** `scifi literature` CLI & FastMCP Tools  

---

## 1. Intent & Product Vision

Conducting a literature review and mapping the frontier of a research area is currently treated by existing tools as a static search or graph clustering problem (e.g., Connected Papers, Litmaps). While these tools show that two publications share citations, they leave the most difficult intellectual labor entirely to the researcher:
1. **Lineage:** Where did an idea actually originate, and what conceptual transformations occurred across generations of methods?
2. **True State of the Art vs. Influence:** Which works represent the actual performance frontier on specific benchmarks versus which works are simply heavily cited?
3. **Evidence-Backed Gaps & Deltas:** Why did the community move away from previous techniques, what unstated assumptions or computational bottlenecks remain unresolved, and where is a defensible delta for new research?

**Product Vision:** The tool is not merely a citation graph generator; it is a **scientific decision-support and knowledge discovery engine**. It maps the intellectual evolution of a field, extracts traceable evidence of technical limitations across both open and paywalled papers, and distinguishes citation popularity from benchmark-verified state of the art.

---

## 2. Goals, Non-Goals & Anti-Goals

### Goals
- **Decoupled Identity & Multi-Provider Reconciliation:** Unify Crossref, OpenAlex, Semantic Scholar, arXiv, and PubMed entries into an internal canonical paper entity with explicit version and location modeling.
- **Tripartite SOTA & Influence Separation:** Explicitly distinguish:
  1. *Influential Research:* High historical citations, seminal status, high betweenness centrality.
  2. *Recent Research Frontier:* High recent citation growth, latest architectural variations.
  3. *Actual SOTA:* Best verified empirical performance on standardized benchmark tasks.
- **Evidence-First Architecture:** Every claim of a research gap, unstated assumption, or benchmark score must link to an immutable `evidence` record (source paper, section, exact quote, retrieval method, and corroborating/contradicting context).
- **Paywall-Resilient Multi-Tier Mining:** Extract limitations via:
  1. Full-text open-access PDF extraction (via arXiv/Unpaywall).
  2. Reconstructed abstracts (via OpenAlex inverted indices).
  3. Inbound citation contexts (analyzing how citing papers contextualize and critique earlier works via Semantic Scholar).
- **Multi-Signal Lineage Traversal:** Combine direct citations, citation influence (`isInfluential`), co-citation frequency, bibliographic coupling, and publication chronology to reconstruct intellectual lineage rather than raw citation leaderboards.
- **Graph-Scoped Persistent SQLite Storage:** Robust multi-tenancy database (`.scifi/literature_store.db`) isolating distinct research topics, with WAL mode, busy timeout handling, and transactional integrity.
- **Interactive Visual Artifact & Publication Deliverables:**
  1. Standalone, XSS-sanitized Vis.js HTML graph distinguishing visual lineage direction (`roots -> frontier`) from citation edges (`citing -> cited`), with cycle detection and a detailed metadata/evidence drawer.
  2. Structured Markdown report with topological evolution narrative, verified BibTeX export, and a rigorous Delta-Novelty Matrix.

### Non-Goals
- Bypassing publisher paywalls or credential gates through illicit mechanisms.
- Automated end-to-end paper writing (the tool produces verified intelligence and drafted synthesis for researcher refinement).
- Blind automated acceptance of citation claims (citation contexts are treated as subjective evidence from a reporting paper, not unquestioned ground truth).

### Anti-Goals
- **Conflating Citations with SOTA:** Never crown a paper as the state of the art purely on the basis of citation counts or citation velocity.
- **Uncorroborated "Fact" Gaps:** Never present an inferred limitation as a definitive fact without displaying its supporting evidence passage and reporting author attribution.
- **Citation Hairballs & Cycle-Riddled DAGs:** Never present an unranked, tangled citation mass. Apparent cycles arising from inconsistent preprint/publication dates must be programmatically detected, resolved, and diagnosed.

---

## 3. Evaluated Approaches & Selected Direction

### Approach A: Integrated CLI & FastMCP Tool with Local SQLite & Standalone HTML Artifact (Selected)
- **Architecture:** Embedded within `scifi.literature`. FastMCP tools (`scifi_map_literature`, `scifi_expand_graph`, `scifi_query_store`) and CLI command `scifi literature`.
- **Storage:** Local SQLite database in `.scifi/literature_store.db`.
- **Visualization:** Self-contained single-file HTML artifact using Vis.js embedded in the output directory, with strict input sanitization.
- **Rationale:** Delivers zero-dependency developer experience, scriptability, offline persistence, and seamless agentic integration without the operational overhead of a persistent web server.

### Approach B: Client-Server Web Application (FastAPI + React Frontend)
- **Trade-offs:** Adds Node/React daemon management, port collisions, and background processes. Rejected as unnecessary for a developer/researcher CLI toolkit.

### Approach C: Text & Mermaid-Only Terminal Pipeline
- **Trade-offs:** Lacks the required exploratory ergonomics for large citation graphs, evidence inspection drawers, and interactive filtering.

---

## 4. Evidence-Based Research Intelligence Architecture

```
                                  +-----------------------+
                                  |   Input Query/Title   |
                                  +-----------+-----------+
                                              |
                                              v
                        +-------------------------------------------+
                        | Canonical Resolver & Identity Engine       |
                        | (OpenAlex, Crossref, S2, arXiv)           |
                        +---------------------+---------------------+
                                              |
                                              v
                        +-------------------------------------------+
                        | Multi-Signal Lineage Traversal            |
                        | - Direct citations (influential)          |
                        | - Co-citation & Bibliographic coupling    |
                        | - Chronological ordering & Cycle check    |
                        +---------------------+---------------------+
                                              |
                     +------------------------+------------------------+
                     |                                                 |
                     v                                                 v
+-----------------------------------------+   +-----------------------------------------+
|     Evidence & Gap Extraction Pipeline  |   |     SOTA & Benchmark Discovery Pipeline |
| 1. Evidence Collection (Quotes/Context) |   | - Benchmark tasks & datasets            |
| 2. Claim Classification (Assumption/Gap)|   | - Evaluation metrics (F1, BLEU, latency)|
| 3. Attribution & Contextual Triage      |   | - Experimental conditions & splits      |
| 4. Candidate Finding (Corroborated)     |   | - Evidence pointer to Table/Section     |
+--------------------+--------------------+   +--------------------+--------------------+
                     |                                                 |
                     +------------------------+------------------------+
                                              |
                                              v
                        +-------------------------------------------+
                        | Persistent SQLite Knowledge Store         |
                        | (.scifi/literature_store.db)              |
                        | - Isolated Graph Sessions                 |
                        | - Full Evidence Provenance Registry       |
                        +---------------------+---------------------+
                                              |
                     +------------------------+------------------------+
                     |                                                 |
                     v                                                 v
+-----------------------------------------+   +-----------------------------------------+
| Interactive HTML Visual Map (.html)     |   | Structured Research Synthesis (.md)     |
| - Lineage DAG (Roots -> Frontier)       |   | - Topological Evolution Narrative       |
| - Color-coded access & SOTA badges      |   | - Evidence-backed Delta-Novelty Matrix  |
| - Slide-out Evidence & Context Drawer   |   | - Verified clean references.bib         |
+-----------------------------------------+   +-----------------------------------------+
```

---

## 5. Comprehensive Relational Data Model (`.scifi/literature_store.db`)

SQLite is configured with WAL mode (`PRAGMA journal_mode=WAL;`), busy timeout (`PRAGMA busy_timeout=5000;`), and foreign key constraints enabled.

```sql
-- 1. Multi-Graph Session Scoping
CREATE TABLE IF NOT EXISTS graphs (
    id TEXT PRIMARY KEY,                 -- Slug or UUID (e.g., "transformer-scaling-laws")
    title TEXT NOT NULL,                -- User research topic or seed title
    seed_paper_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Internal Canonical Paper Record
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,                 -- Internal UUID
    title TEXT NOT NULL,
    year INTEGER,
    publication_date TEXT,              -- ISO date YYYY-MM-DD when known
    citation_count INTEGER DEFAULT 0,
    influential_citation_count INTEGER DEFAULT 0,
    recent_citation_growth REAL DEFAULT 0.0, -- Annualized growth rate over recent window
    is_retracted BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. External Provider Identifiers (Many-to-One mapping)
CREATE TABLE IF NOT EXISTS paper_identifiers (
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,             -- 'doi', 'openalex', 'semantic_scholar', 'arxiv', 'pubmed'
    external_id TEXT NOT NULL,
    is_canonical BOOLEAN DEFAULT 0,
    PRIMARY KEY (provider, external_id)
);

-- 4. Publication Versions (Preprint revisions, conference vs journal)
CREATE TABLE IF NOT EXISTS paper_versions (
    id TEXT PRIMARY KEY,                 -- UUID
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    version_type TEXT NOT NULL,         -- 'preprint', 'conference_proceedings', 'journal_article', 'extension'
    version_label TEXT,                 -- e.g. "arXiv:v1", "NeurIPS 2023", "IEEE T-PAMI"
    doi TEXT,
    release_date TEXT,
    reconciliation_confidence REAL DEFAULT 1.0
);

-- 5. Document Locations & Granular Access Modeling
CREATE TABLE IF NOT EXISTS paper_locations (
    id TEXT PRIMARY KEY,                 -- UUID
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    version_id TEXT REFERENCES paper_versions(id) ON DELETE SET NULL,
    location_type TEXT NOT NULL,        -- 'publisher', 'repository', 'archive'
    is_oa BOOLEAN NOT NULL DEFAULT 0,
    oa_status TEXT NOT NULL,            -- 'gold', 'green', 'hybrid', 'bronze', 'closed'
    landing_page_url TEXT,
    pdf_url TEXT,
    is_accessible BOOLEAN DEFAULT 0,    -- Verified downloadable
    local_pdf_path TEXT
);

-- 6. Junction connecting papers to scoped graph sessions
CREATE TABLE IF NOT EXISTS graph_papers (
    graph_id TEXT NOT NULL REFERENCES graphs(id) ON DELETE CASCADE,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    node_role TEXT NOT NULL,            -- 'seed', 'foundation', 'intermediate', 'frontier', 'benchmark_sota'
    topological_depth INTEGER DEFAULT 0,
    PRIMARY KEY (graph_id, paper_id)
);

-- 7. Authors & Temporal Institutional Affiliations
CREATE TABLE IF NOT EXISTS authors (
    id TEXT PRIMARY KEY,                 -- Canonical OpenAlex/ORCID ID
    name TEXT NOT NULL,
    orcid TEXT,
    email TEXT,
    homepage TEXT
);

CREATE TABLE IF NOT EXISTS paper_authors (
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    author_id TEXT NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    author_position INTEGER NOT NULL,   -- 1 = first author
    is_corresponding BOOLEAN DEFAULT 0,
    PRIMARY KEY (paper_id, author_id)
);

CREATE TABLE IF NOT EXISTS paper_author_affiliations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    institution_name TEXT NOT NULL,
    ror_id TEXT,
    country_code TEXT,
    FOREIGN KEY (paper_id, author_id) REFERENCES paper_authors(paper_id, author_id) ON DELETE CASCADE
);

-- 8. Venues & Contextual Ranking Metadata
CREATE TABLE IF NOT EXISTS venues (
    id TEXT PRIMARY KEY,                 -- Normalised slug
    name TEXT NOT NULL,
    venue_type TEXT NOT NULL,           -- 'conference', 'journal', 'repository'
    series_acronym TEXT,                -- 'NeurIPS', 'ICML', 'CVPR'
    issn TEXT
);

CREATE TABLE IF NOT EXISTS venue_rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue_id TEXT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    ranking_authority TEXT NOT NULL,    -- 'CORE', 'Scimago', 'OpenAlex'
    ranking_edition_or_year TEXT NOT NULL, -- e.g. "2023", "2024"
    rank_value TEXT NOT NULL,           -- 'A*', 'A', 'B', 'C', 'Q1', 'Q2', 'Q3', 'Q4'
    metric_definition TEXT NOT NULL,    -- 'expert_peer_review', 'SJR', '2yr_mean_citedness'
    raw_score REAL,
    retrieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS paper_venues (
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    venue_id TEXT NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    publication_year INTEGER,
    PRIMARY KEY (paper_id, venue_id)
);

-- 9. Directed Citation Network
CREATE TABLE IF NOT EXISTS citations (
    source_paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE, -- Citing paper
    target_paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE, -- Cited paper
    is_influential BOOLEAN DEFAULT 0,
    co_citation_count INTEGER DEFAULT 0,
    bibliographic_coupling_strength REAL DEFAULT 0.0,
    PRIMARY KEY (source_paper_id, target_paper_id)
);

-- 10. Granular Citation Contexts (Multiple mentions per paper pair)
CREATE TABLE IF NOT EXISTS citation_contexts (
    id TEXT PRIMARY KEY,                 -- UUID
    source_paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    target_paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    context_text TEXT NOT NULL,
    section_name TEXT,                  -- 'Introduction', 'Related Work', 'Discussion'
    intent TEXT,                        -- 'methodology', 'background', 'result_comparison'
    is_influential BOOLEAN DEFAULT 0
);

-- 11. First-Class Evidence & Provenance Registry
CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,                 -- UUID
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE, -- Target paper concerned
    reporting_paper_id TEXT REFERENCES papers(id) ON DELETE SET NULL, -- Paper stating the claim
    evidence_type TEXT NOT NULL,        -- 'citation_context', 'author_abstract', 'full_text_section', 'benchmark_table'
    source_section TEXT,
    source_location TEXT,               -- Page, paragraph, or table reference
    extracted_text TEXT NOT NULL,
    extraction_method TEXT NOT NULL,    -- 'semantic_scholar_api', 'openalex_inverted_index', 'pdf_text_parser'
    confidence REAL,                    -- Nullable uncalibrated confidence score
    retrieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 12. Candidate Research Gaps & Limitations
CREATE TABLE IF NOT EXISTS paper_gaps (
    id TEXT PRIMARY KEY,                 -- UUID
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    gap_type TEXT NOT NULL,             -- 'computational_complexity', 'unstated_assumption', 'empirical_limitation', 'generalization_bound', 'unresolved_problem'
    claim_summary TEXT NOT NULL,
    primary_evidence_id TEXT NOT NULL REFERENCES evidence(id) ON DELETE RESTRICT,
    verification_status TEXT NOT NULL DEFAULT 'candidate', -- 'candidate', 'corroborated', 'disputed'
    corroborating_count INTEGER DEFAULT 0,
    contradicting_count INTEGER DEFAULT 0
);

-- 13. SOTA Benchmark Intelligence
CREATE TABLE IF NOT EXISTS benchmarks (
    id TEXT PRIMARY KEY,                 -- Normalised slug (e.g. "glue-benchmark", "imagenet-1k")
    name TEXT NOT NULL,
    task_type TEXT NOT NULL,            -- 'classification', 'translation', 'generation', 'reasoning'
    domain TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS benchmark_results (
    id TEXT PRIMARY KEY,                 -- UUID
    benchmark_id TEXT NOT NULL REFERENCES benchmarks(id) ON DELETE CASCADE,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    version_id TEXT REFERENCES paper_versions(id) ON DELETE SET NULL,
    metric_name TEXT NOT NULL,          -- 'Top-1 Accuracy', 'BLEU', 'Latency (ms)', 'Throughput'
    metric_value REAL NOT NULL,
    is_higher_better BOOLEAN NOT NULL DEFAULT 1,
    evaluation_conditions TEXT,         -- Dataset split, parameter count, hardware setup
    evidence_id TEXT REFERENCES evidence(id) ON DELETE RESTRICT,
    is_verified_sota BOOLEAN DEFAULT 0,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 6. Research Methodology & Algorithmic Strategy

### 6.1 Multi-Signal Lineage Traversal
Rather than relying purely on top-K citation counts, the lineage traversal applies a multi-factor graph discovery algorithm:
1. **Seed Anchoring:** Resolve query to canonical seed paper, register graph in `graphs`, and assign seed depth 0.
2. **Backward Traversal (Roots & Foundations):**
   - Retrieve referenced works via OpenAlex and Crossref.
   - Rank references using composite weight:
     $$\text{Weight}_{\text{back}} = w_1 \cdot \log(1 + C_{\text{global}}) + w_2 \cdot \mathbb{I}_{\text{influential}} + w_3 \cdot \text{CoCite}_{\text{seed}}$$
   - Retain top 5 distinct foundational nodes per expansion step.
3. **Forward Traversal (Recent Frontier):**
   - Query citing papers published in the last 3 years.
   - Calculate normalized annualized citation growth:
     $$\text{Growth} = \frac{C_{\text{recent}}}{\max(0.5, \text{CurrentYear} - \text{Year}_{\text{pub}})}$$
   - Identify candidate frontier works displaying high momentum rather than just raw historical accumulation.
4. **Apparent Cycle Detection & Chronological DAG Rectification:**
   - Run Tarjan's strongly connected components algorithm on the extracted subgraph.
   - When a cycle is detected (caused by preprint revisions or back-dated citations), resolve using `publication_date` hierarchy (`paper_versions`). If unresolvable, flip back-edge to an annotated bidirectional correlation edge, preventing topological sort breakdown.
   - Compute topological depth ($0, 1, 2, \dots, D$) representing intellectual progression.

### 6.2 The 4-Stage Evidence Pipeline for Gap Extraction
Never present a limitation as an established fact without attribution:
1. **Stage 1 (Evidence Collection):**
   - Capture exact textual passages from:
     - Open-access PDF text (`limitations_and_conclusion` parsed via PyMuPDF/pdfminer).
     - Author abstract (reconstructed from OpenAlex inverted indices).
     - Inbound citation contexts from Semantic Scholar (`/citations?fields=contexts,intents`).
   - Store passage into `evidence` with extraction method, timestamp, and source section.
2. **Stage 2 (Claim Classification):**
   - Apply deterministic linguistic triage to detect limitation patterns:
     - Computational overhead (*"requires $O(N^2)$ memory"*, *"prohibitive training cost"*).
     - Unstated assumptions (*"assumes static channel"*, *"holds only in convex regime"*).
     - Empirical boundaries (*"fails on long-tail distributions"*, *"degrades under noise"*).
3. **Stage 3 (Attribution & Verification):**
   - Explicitly link the claim to its reporting paper. If Paper B states that Paper A is slow, the claim is attributed to Paper B's perspective.
4. **Stage 4 (Candidate Finding & Corroboration):**
   - Group evidence items by target paper and gap category.
   - If multiple independent citing papers report the same limitation, upgrade `verification_status` from `candidate` to `corroborated`. If a subsequent work demonstrates a fix or refutation, record a contradicting passage.

### 6.3 Decoupling Influence from SOTA Performance
- **Influential Papers:** Tagged via historical citation count, PageRank, and foundational node role.
- **Frontier Papers:** Tagged via high recent citation growth rate and active methodological iteration.
- **Benchmark SOTA:** Populated from `benchmark_results`. A paper is crowned SOTA only if it holds the verified superior metric on a recorded benchmark under comparable evaluation conditions, with direct reference to the reporting evidence (table/section).

### 6.4 Venue Rankings as Supporting Context
- CORE conference rankings (A*, A, B) and Scimago SJR quartiles (Q1–Q4) are displayed as contextual badges in the UI and report.
- Venue metrics are strictly forbidden from overriding empirical benchmark results or excluding unranked preprints that achieve superior verified performance.

---

## 7. System Interfaces & Execution Modes

### 7.1 FastMCP Server Tools
- `scifi_map_literature(query: str, depth: int = 2, max_papers: int = 25, graph_id: str | None = None) -> dict`:
  Executes multi-signal traversal, stores papers/evidence in SQLite, and returns generated report paths.
- `scifi_expand_graph(graph_id: str, paper_id: str, direction: str = 'both', limit: int = 5) -> dict`:
  Expands a specific node forward or backward, incrementally deepening long-horizon research graphs.
- `scifi_query_store(query_sql: str) -> list[dict]`:
  Safe, read-only SQL query interface. Enforces `SELECT`-only execution via query parsing and sqlite3 authorizer hooks; rejects modifying statements (`INSERT`, `UPDATE`, `DELETE`, `DROP`).
- `scifi_export_bibtex(graph_id: str, output_path: str) -> dict`:
  Exports sanitized, deduplicated `.bib` entries for all papers in the specified graph session.

### 7.2 CLI Commands
```bash
# Generate full evidence-backed literature report and interactive map
scifi literature report "Attention Is All You Need" --depth 2 --output-dir ./lit_review

# Generate interactive visual map only
scifi literature map "Deep Residual Learning for Image Recognition" --open

# Manage local research graph sessions
scifi literature db list-graphs
scifi literature db export-bib --graph-id "attention-is-all-you-need" -o references.bib
```

### 7.3 Output Deliverables
1. **Interactive Standalone HTML (`literature_map.html`):**
   - Vis.js hierarchical network layout oriented from Roots $\to$ Frontier.
   - Node styling: Color denotes Access Tier (`Gold OA`, `Green Preprint`, `Hybrid`, `Paywalled`); node halo denotes SOTA status.
   - Slide-out Evidence Drawer:
     - Author names, affiliations, ORCIDs, and corresponding emails.
     - Venue rankings with authority and edition.
     - Extracted candidate gaps with exact quote passages, reporting paper attribution, and corroboration count.
     - Benchmark performance comparisons with evidence pointers.
   - Security: All bibliographic and author strings are sanitized against XSS before DOM insertion.
2. **Structured Research Synthesis (`literature_report.md`):**
   - Section 1: Topological Lineage & Intellectual Evolution.
   - Section 2: Verified State-of-the-Art Benchmark Table.
   - Section 3: Evidence-Backed Delta-Novelty Matrix (Foundations vs Frontier vs Proposed Approach template).
   - Section 4: Traceable Limitations & Research Opportunities (with source citations).

---

## 8. Concurrency, Performance & Security Safeguards

1. **SQLite Concurrency:** Connection factory sets `PRAGMA busy_timeout = 5000;`, enables WAL mode, and encapsulates all state modifications within explicit write transactions (`BEGIN IMMEDIATE`) with backoff retries.
2. **Adaptive API Budgeting:** No hardcoded runtime assumptions. Crawling adheres to an adaptive budget:
   - Configurable maximum request limit (default: 30 calls).
   - Local caching of API responses in `~/.scifi/cache/` to eliminate duplicate network calls.
   - Graceful degradation when rate-limited.
3. **Safe Read-Only SQL Tool:** The `scifi_query_store` FastMCP tool registers a SQLite authorizer (`set_authorizer`) allowing only `SQLITE_SELECT` operations and blocking schema modification or writes.
4. **HTML Injection Defense:** All user-supplied strings, author names, paper titles, and extracted evidence passages are escaped using Python's `html.escape` and sanitized before serializing into the Vis.js HTML template.

---

## 9. Phased Implementation Roadmap

To maintain velocity and ensure each phase delivers an independently verifiable, high-quality product, implementation proceeds across three distinct phases:

### Phase 1: Literature Intelligence Core
- Internal canonical paper identity model (`papers`, `paper_identifiers`, `paper_versions`, `paper_locations`).
- Graph-scoped SQLite storage engine with WAL and concurrency guards.
- OpenAlex and arXiv resolver with deduplication.
- Multi-signal backward and forward lineage traversal with cycle detection.
- Standalone XSS-safe Vis.js HTML generator (lineage DAG, metadata drawer).
- Structured Markdown report generator and sanitized BibTeX exporter.

### Phase 2: Research Evidence Intelligence
- Semantic Scholar citation context ingestion (`citation_contexts`).
- First-class `evidence` provenance registry.
- Paywall-resilient gap extraction (author abstract parsing + inbound citing context triage).
- Attribution and corroboration engine (`paper_gaps` with candidate/corroborated status).
- Evidence drawer integration in `literature_map.html`.

### Phase 3: SOTA & Novelty Intelligence
- Benchmark and evaluation condition schema (`benchmarks`, `benchmark_results`).
- Metric extraction and verified SOTA flagging.
- SOTA vs. Influence distinction in reporting and visualization.
- Full Delta-Novelty Matrix generation.
- Incremental graph expansion FastMCP tool (`scifi_expand_graph`).
