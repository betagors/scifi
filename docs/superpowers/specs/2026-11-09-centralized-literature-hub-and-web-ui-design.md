# SciFi Centralized Literature Hub, Reprint Outreach Engine & Web Dashboard Design Document

**Date:** 2026-11-09  
**Author:** Antigravity  
**Status:** In Review  
**Target Modules:** `scifi/literature/`, `scifi/web/`, `scifi/server.py`, `scifi/cli.py`  

---

## 1. Intent & Context

Academic literature discovery and synthesis are iterative, multi-day, multi-project investigations. In modern research workflows:
1. **Cross-Project Scope**: Researchers work on multiple related papers and domains (e.g., UAV control, reinforcement learning, robotics vision). Currently, SciFi persists literature graphs into a project-local SQLite file (`.scifi/literature_store.db`). This causes fragmentation: there is no global overview across all projects, and the same foundational papers are downloaded and parsed repeatedly across different project folders.
2. **Paywalled Papers & Author Reprints**: When a critical paper has no open-access PDF, the pipeline currently returns `NO_OA_PDF` and stops. In academic practice, authors share "author reprints" privately upon polite email request. However, fully autonomous emailing risks spamming researchers and blocking research pipelines. A non-blocking, provider-agnostic reprint assistant is needed to find corresponding author contacts and draft professional requests with human-in-the-loop confirmation.
3. **Visual Cockpit & Continuation**: Research graphs with 30+ nodes, citation lineages, benchmark leaderboards, and gap taxonomies are difficult to digest and navigate purely through terminal logs. A dedicated local web dashboard (`sf ui` / `localhost:8080`) provides a visual research cockpit to explore citation DAGs, manage projects, and resume investigations.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- **Hybrid Centralized Hub & In-Repo Sync (Alternative 3)**:
  - Central runtime database at `~/.scifi/literature_store.db` powering global cross-project search, universal paper/PDF deduplication, and the centralized Web UI.
  - In-repo project manifest at `<project_dir>/.scifi/literature_manifest.json` and `references.bib` for git version control, team sharing, and machine portability.
  - Fast bidirectional sync (`sf literature sync`) to import from or export to the local repository manifest.
- **Non-Blocking Author Reprint Outreach Engine**:
  - Automatically query OpenAlex / Semantic Scholar for corresponding author metadata (name, institutional affiliation, verified email, ORCID) when a paper is paywalled (`NO_OA_PDF`).
  - Generate polite, academic-standard reprint request drafts (RFC-compliant subject, body, and URI-encoded `mailto:` deep link).
  - Provider-agnostic output: compatible with Gmail MCP, Microsoft Outlook / 365 MCP, Zoho MCP, or native OS email clients.
  - Never stall or block literature search, citation lineage, or gap extraction on missing PDFs.
- **Local Web Research Cockpit (`sf ui` / `http://localhost:8080`)**:
  - Multi-project overview: switch between research projects and inspect global literature statistics.
  - Interactive Vis.js citation DAG with hierarchical layout, color-coded Open Access badges, and slide-out metadata drawer.
  - Paper catalog & full-text viewer with extracted research gaps and SOTA benchmarks.
  - Author Reprint Hub: list of pending reprint requests with 1-click email drafting and drag-and-drop PDF ingestion.
- **Decoupled MCP Tools & CLI Extensions**:
  - Expose session management, reprint drafting, and PDF ingestion to both CLI (`sf literature ...`) and FastMCP tools (`scifi_...`).

### Non-Goals
- Autonomous, non-consensual email sending (all emails remain drafts or require user confirmation).
- Building an external cloud-hosted SaaS platform (all servers run locally on `localhost`).
- Heavy frontend build toolchains (Node.js/npm/Webpack); the Web UI is self-contained HTML5/CSS/JS served directly by Python.

### Anti-Goals
- **Zero Pipeline Blocking**: Paywalled papers must never pause batch crawling or literature synthesis.
- **Zero Lock-In**: Repositories must remain completely functional and portable without requiring the central machine database.
- **Zero Duplicated Large Assets**: Avoid downloading duplicate multi-megabyte PDFs across multiple project directories.

---

## 3. Constraints

- **Python Runtime**: Python >= 3.12.
- **Operating Systems**: Windows, macOS, Linux with proper path resolution (`Path.home() / ".scifi"`).
- **Zero External Node Dependencies**: Frontend dashboard must be an embedded, self-contained single-page application (SPA) using CDN or bundled Vis.js and Tailwind CSS.
- **Concurrency & Concurrency Safety**: SQLite WAL mode with busy timeouts (5000ms) and table-level locking to support concurrent access by CLI, FastMCP server, and Web UI.
- **Network Resilience**: Author email extraction must handle missing author contacts gracefully without throwing fatal exceptions.

---

## 4. Approaches Considered

### Approach 1: Centralized Database Only (The Zotero / Notion Model)
- Single global database in `~/.scifi/literature_store.db`.
- **Pros**: Complete cross-project visibility; simple architecture; instant global search.
- **Cons**: Projects committed to git lack literature metadata unless manually dumped; zero repo self-containment.

### Approach 2: Distributed Per-Project DBs with Registry (The Git / VS Code Model)
- Each project keeps `<project_dir>/.scifi/literature.db`, with a global path pointer registry in `~/.scifi/registry.json`.
- **Pros**: Strict repository isolation.
- **Cons**: No automatic PDF or paper deduplication; cross-project search is inefficient and fragile against directory moves/renames.

### Approach 3: Hybrid Hub-and-Spoke (Central Runtime DB + In-Repo Sync Manifest) *(Selected)*
- Central SQLite database at `~/.scifi/literature_store.db` serves as the runtime brain for the Web UI, MCP, and deduplicated paper/PDF storage.
- Each project maintains `<project_dir>/.scifi/literature_manifest.json` and `references.bib`.
- Running literature commands inside a project automatically updates both the central DB and the local manifest.
- **Trade-off Decision**: Selected because it gives seamless cross-project navigation and zero duplicate downloads while preserving 100% git portability.

---

## 5. System Architecture & Detailed Specifications

```
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                         Central Storage Runtime                         │
  │  Location: ~/.scifi/                                                    │
  │  ├── literature_store.db (SQLite WAL: projects, papers, citations,      │
  │  │                        gaps, benchmarks, reprint_requests)           │
  │  └── storage/pdfs/<doi_or_hash>.pdf (Global Content-Addressed PDFs)     │
  └────────────────────────────┬───────────────────────────────▲────────────┘
                               │                               │
            ┌──────────────────┴──────────────────┐            │
            ▼                                     ▼            │
  ┌───────────────────────────────┐     ┌──────────────────────┴────────────┐
  │      Local Web Cockpit        │     │         SciFi FastMCP Server      │
  │  Command: sf ui (port 8080)   │     │  - scifi_map_literature           │
  │  - Multi-Project Switcher     │     │  - scifi_list_projects            │
  │  - Interactive Vis.js DAG     │     │  - scifi_draft_reprint_request    │
  │  - Reprint Outreach Manager   │     │  - scifi_ingest_paper_pdf         │
  │  - SOTA Leaderboard           │     └───────────────────────────────────┘
  └───────────────────────────────┘                    ▲
                                                       │ (MCP Client/Agent)
  ┌──────────────────────────────────────────┐         ▼
  │          Active Project Workspace        │  ┌───────────────────────────┐
  │  Location: <repo>/                       │  │      Agentic Bridge       │
  │  └── .scifi/                             │  │  - Gmail MCP              │
  │      ├── literature_manifest.json        │  │  - Outlook / 365 MCP      │
  │      └── references.bib                  │  │  - Zoho MCP               │
  │  (Auto-synced via sf literature sync)    │  │  - OS mailto: fallback    │
  └──────────────────────────────────────────┘  └───────────────────────────┘
```

### 5.1 Central SQLite Schema Updates (`scifi/literature/store.py`)

Extend `SCHEMA_SQL` in `LiteratureStore` with project scoping and reprint tracking:

```sql
-- 1. Global Projects Registry
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    workspace_path TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Project-Paper Scoping Junction
CREATE TABLE IF NOT EXISTS project_papers (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    graph_id TEXT REFERENCES graphs(id) ON DELETE SET NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    PRIMARY KEY (project_id, paper_id)
);

-- 3. Author Reprint Outreach Registry
CREATE TABLE IF NOT EXISTS reprint_requests (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    author_name TEXT NOT NULL,
    author_email TEXT, -- Nullable: when redacted/omitted by APIs, UI displays "Contact Pending" with manual input field
    author_affiliation TEXT,
    status TEXT NOT NULL DEFAULT 'DRAFT_READY', -- DRAFT_READY, SENT, RECEIVED, DECLINED, SKIPPED
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    mailto_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reprint_status ON reprint_requests(status);
CREATE INDEX IF NOT EXISTS idx_project_papers_proj ON project_papers(project_id);
```

### 5.2 In-Repo Project Manifest (`.scifi/literature_manifest.json`)

To preserve git portability and ensure full offline re-hydration on a fresh clone, SciFi serializes both paper metadata and graph relationships in each project:
```json
{
  "$schema": "https://scifi.dev/schema/literature-manifest.v1.json",
  "project_name": "uav-trajectory-mpc",
  "synced_at": "2026-11-09T20:15:00Z",
  "papers_count": 25,
  "papers": [
    {
      "id": "10.1016/j.neucom.2023.126456",
      "title": "Adaptive Trajectory Tracking for Quadrotors",
      "year": 2023,
      "oa_status": "closed",
      "has_local_pdf": false,
      "reprint_status": "DRAFT_READY"
    }
  ],
  "citations": [
    {
      "source_paper_id": "10.1016/j.neucom.2023.126456",
      "target_paper_id": "10.1109/TRO.2020.12345",
      "is_influential": true
    }
  ],
  "benchmarks": [],
  "gaps": []
}
```
- `sf literature sync`: Reads `.scifi/literature_manifest.json`. On a fresh clone where `~/.scifi/literature_store.db` is empty, it re-hydrates the complete research graph (nodes, edges, gaps, benchmarks) into the central database. When run in an active project, it exports any newly discovered papers from the central DB back into the manifest and updates `references.bib`.

### 5.3 Author Reprint Outreach Engine (`scifi/literature/reprint.py`)

- **Execution Model: Curated / On-Demand**:
  - During batch lineage crawls, paywalled papers are marked as `oa_status = 'closed'` and `has_local_pdf = false`.
  - Crawls remain completely non-blocking: no secondary author queries run during bulk crawling.
  - The researcher or AI agent explicitly triggers a reprint request for specific papers they need full text for (via CLI `sf literature reprint <doi>`, FastMCP `scifi_draft_reprint_request(doi)`, or clicking *"Prepare Reprint"* in the Web UI).
- **Author Discovery & Fallback**:
  - Queries OpenAlex (`authorships` where `is_corresponding = true` or first/last author) and Semantic Scholar.
  - If verified email is found: generates complete RFC email payload and pre-encoded `mailto:` deep link.
  - If email is redacted/unlisted: saves record with `author_email = NULL` and status `DRAFT_READY`. The Web UI displays *"Contact Pending"* with an editable input field allowing the researcher to paste the author's lab email.
- **Draft Generator**: Produces a disciplined, academic-standard request letter:
  - Subject: `Author reprint request: [Title]`
  - Body: Polite greeting, explanation of academic interest, paper citation, standard non-commercial scholarly sharing exemption statement, and signature placeholder.
  - `mailto:` deep link: Pre-encoded URL for instant OS-level mail composition.
- **State Management**: Adds an entry to `reprint_requests` with status `DRAFT_READY`.
- **Ingestion**: When a PDF is provided (`sf literature ingest-pdf --doi ... --pdf path/to/pdf`), the file is moved/linked into central storage, the paper's `paper_locations` is updated, and the reprint status flips to `RECEIVED`.

### 5.4 Local Web Cockpit (`scifi/web/`)

- **Server**: Embedded HTTP/REST API server (`scifi/web/server.py`) using Python's standard `http.server` or a lightweight ASGI/WSGI app.
- **CLI Command**: `sf ui [--port 8080] [--no-browser]` starts the server and opens the browser.
- **Project & Session Scoping**:
  - The UI header contains a **Project Switcher** and a **Session Selector** (`All Sessions / Synthesized DAG` vs specific crawl sessions).
- **Endpoints**:
  - `GET /api/projects`: List all known projects and paper counts.
  - `GET /api/projects/<id>/graph?session_id=<optional>`: Return JSON nodes, edges, and metadata for Vis.js rendering.
  - `GET /api/projects/<id>/papers`: Return table of papers, PDF status, benchmarks, and gaps.
  - `GET /api/reprints`: List pending reprint drafts across all or current projects.
  - `POST /api/reprints/<id>`: Update contact email or outreach status (`SENT`, `SKIPPED`).
  - `POST /api/papers/ingest`: Upload/link a local PDF for a paper.
- **Frontend SPA (`scifi/web/static/index.html`)**:
  - Pure HTML5 + CSS + JavaScript.
  - Responsive tabbed navigation: **Overview / Projects**, **Interactive Citation Graph (Vis.js)**, **Papers & Benchmarks**, **Author Reprints**.
  - No external build step or node dependencies.

### 5.5 FastMCP & CLI Extensions

- **Project Scoping Auto-Discovery**:
  - If a command is run inside a git repo or directory with `.scifi/`, the workspace path is automatically linked.
  - Optional `--project <name>` argument allows explicit project tagging while remaining 100% backward-compatible.
- **CLI Subcommands**:
  - `sf ui`: Start local web dashboard.
  - `sf literature sync`: Bidirectional sync between local workspace manifest and central DB.
  - `sf literature reprint <doi>`: Prepare reprint draft on-demand for a paywalled paper.
  - `sf literature reprints [--project <id>]`: List and inspect author reprint drafts.
  - `sf literature ingest-pdf --doi <doi> --pdf <path>`: Ingest an acquired paper PDF.
- **FastMCP Tools**:
  - `scifi_list_projects()`: List all registered research projects.
  - `scifi_get_project_summary(project_name_or_path=None)`: Return stats on papers, OA status, and gaps.
  - `scifi_draft_reprint_request(identifier, project_name=None)`: Generate draft on-demand and log to queue.
  - `scifi_list_pending_reprints(project_name=None)`: Retrieve all unfulfilled author reprint drafts.
  - `scifi_ingest_paper_pdf(identifier, pdf_path, project_name=None)`: Ingest author copy into project.

---

## 6. What's Left to the Builder

- Default port selection fallback (if port 8080 is busy, automatically try 8081..8089).
- Vis.js canvas color theming and node shape styling.
- Local PDF storage naming convention (`hashlib.sha256(doi.encode()).hexdigest()[:16].pdf`).
- Exact formatting of `mailto:` URLs with proper query string percent-encoding.