# Design Specification: SciFi Local Zotero 10 Integration & Bi-Directional Intelligence Hub

**Status:** Draft Specification (Awaiting Builder Review & Approval)  
**Date:** 2026-11-10  
**Target Module:** `scifi.literature.zotero`  
**Command / Interface:** `sf zotero` CLI & FastMCP Tools (`scifi/server.py`)  

---

## 1. Intent & Product Vision

Academic researchers frequently face a severe friction between their literature management tools and their coding/agent workflows:
1. **Repository Bloat & Redundancy:** Agents typically download PDFs directly into project directories (e.g. `workspace/papers/`), polluting Git histories with tens or hundreds of megabytes of binary blobs that already exist on the user's hard drive.
2. **Context Silos:** Researchers meticulously curate papers, collections, highlights, and tags inside Zotero, but their coding agents operate in a disconnected vacuum, ignorant of what the human has already reviewed, organized, or prioritized.
3. **Lost Agentic Intelligence:** When an agent conducts an adversarial paper audit (hunting for unstated assumptions with Popper, verifying optimality proofs with Turing, or extracting empirical SOTA tables with Hypatia), those hard-won insights remain trapped in ephemeral terminal outputs or temporary chat sessions rather than being saved in the researcher's permanent academic memory.

**Product Vision:** A seamless, zero-copy local bridge uniting Zotero (the researcher's personal knowledge repository) and SciFi (the autonomous scientific verification engine). Each SciFi project binds directly to a scoped Zotero collection. SciFi reads local PDFs directly from Zotero's disk storage without copying files, ingests the researcher's personal PDF highlights from Zotero's database, audits the literature, and writes structured **"SciFi Audit Cards"** and color-coded status tags directly back into the user's Zotero desktop app.

---

## 2. Goals, Non-Goals & Anti-Goals

### Goals
- **Zero-Copy Local Reading:** Connect directly to local `zotero.sqlite` using SQLite URI read-only mode (`mode=ro` / `immutable=1`) to resolve bibliographic metadata and resolve full-text PDFs directly from `~/Zotero/storage/<key>/<filename>.pdf` with sub-millisecond latency and zero file duplication.
- **Collection-Scoped Project Binding:** Bind each SciFi workspace to a specified Zotero collection (e.g., `UAV`, `NN Verification`) defined in `.scifi/config.json`. Queries, audits, and citekey lookups prioritize this collection before querying the broader library.
- **Bi-Directional Intelligence Dispatch (Audit Cards):** Generate structured, interactive HTML child notes attached under parent items in Zotero via the local HTTP server (`http://127.0.0.1:23119`), documenting:
  - Key Contribution & Novelty Delta
  - Extracted Baselines & SOTA Benchmarks (with datasets and exact metrics)
  - Flagged Unstated Physical/Computational Assumptions
  - Verified Mathematical Optimality & Proof Status
  - Retraction & Publisher Concern Alerts
- **Visual Status Tagging Taxonomy:** Apply Zotero color-coded quick tags:
  - 🟩 `#scifi-verified`: Proofs checked, assumptions documented, citation valid.
  - 🟨 `#unstated-assumption`: Implicit ideal assumptions detected by Popper.
  - 🟥 `#retraction-or-concern`: Errata or retraction flagged on Crossref/Retraction Watch.
  - 🟦 `#benchmark-sota`: Verified empirical performance numbers extracted.
- **Human PDF Annotation Ingestion:** Query Zotero's `itemAnnotations` table to read user highlights, sticky notes, and comments, allowing human annotations to guide SciFi's auditing priorities.
- **Dynamic Smart Folder Generation (Saved Searches):** Provide commands to generate project-scoped Saved Searches in Zotero:
  - `SciFi: Pending Audit` (papers in collection missing SciFi audit notes)
  - `SciFi: Flagged Assumptions` (papers in collection tagged with unstated assumptions)
  - `SciFi: SOTA Benchmarks` (papers with extracted quantitative metrics)
- **Deterministic BibTeX Synchronization:** Export project references directly from the Zotero collection to `references.bib` with deterministic citation keys conforming to SciFi Rule 1 (`[Author][Year][Word]`).
- **Automated Project Scaffolding (`sf init` / `sf scaffold`):** Bootstrap new research repositories into the standard 2-pillar architecture (`paper/` + `code/` orchestrated by `.scifi/`), auto-detecting the user's local Zotero library and linking or creating a dedicated collection.
- **Legacy Project Migration (`sf adapt`):** Scan and reorganize existing, messy, or monolithic academic repositories into standard SciFi structure, extracting citations from legacy `.bib` files, cross-referencing them against Zotero items, and binding a project collection.
- **Graceful Self-Healing UX & Zero-Friction Prerequisites:** Automatically handle tooling requirements (`uv`, Zotero paths, LaTeX toolchains) on behalf of the user. Never crash on missing dependencies; auto-install `uv` or fall back to system Python, auto-detect Zotero data directories, and seamlessly queue writes when Zotero is closed without interrupting the user.
- **Resilient Fallback:** If Zotero is not installed or the local HTTP server is closed, read operations succeed offline via direct SQLite queries, write operations stage safely to a local cache, and standard non-Zotero SciFi workflows remain fully functional.

### Non-Goals
- Building an independent PDF viewer or trying to replicate Zotero's desktop GUI.
- Supporting third-party reference managers (Mendeley, EndNote) in this milestone.
- Overwriting the user's manual notes, tags, or file attachments.

### Anti-Goals
- **Raw Concurrency Database Writes:** Never perform direct SQL `INSERT` or `UPDATE` queries on `zotero.sqlite` while Zotero is running. All write operations must pass through Zotero's local HTTP API / Connector endpoint (`127.0.0.1:23119`) or stage safely.
- **Hard Runtime Blockers:** Never fail a build or crash SciFi commands because Zotero is closed; degrade gracefully to read-only SQLite or cached metadata.
- **Unsolicited Library Pollution:** Never modify, tag, or attach notes to papers outside the project's configured collection unless explicitly targeted by the user.

---

## 3. Constraints & Operating Environment

- **Host Environment:** Windows (current host: `C:\Users\Betagors\Zotero`), with portable path resolution for Linux/macOS.
- **Zotero Compatibility:** Zotero 7 through 10 compatibility.
- **Concurrency & Locking:** `zotero.sqlite` queries must use `file:///...?immutable=1` (or `mode=ro` with URI syntax) to prevent SQLite `database is locked` errors while Zotero is actively running.
- **Port:** Local HTTP server on `127.0.0.1:23119` (Zotero's built-in connector & API endpoint).
- **Python Version:** Python >= 3.10 (tested under Python 3.12).

---

## 4. Evaluated Approaches & Selected Architecture

### Approach 1: Direct Local SQLite Reader + Local Server HTTP Writer (Selected)
- **Architecture:** 
  - **Reads:** Direct connection to `zotero.sqlite` using `immutable=1` URI mode. Resolves item metadata, collection hierarchies, annotations, and local attachment paths directly from disk.
  - **Writes:** HTTP `POST` requests to `http://127.0.0.1:23119/connector/...` or local API to create child notes and apply tags.
- **Trade-offs:** 
  - Sub-millisecond reads with zero CPU/network overhead.
  - Works offline even when the Zotero desktop application is closed.
  - Guarantees 100% database safety by delegating writes to Zotero's native server.
- **Verdict:** Selected as the optimal approach for performance, safety, and reliability.

### Approach 2: Pure Local HTTP API (Zotero 7/10 / Better BibTeX)
- **Architecture:** All queries and mutations route through `127.0.0.1:23119`.
- **Trade-offs:** Clean client-server separation, but fails completely when Zotero is closed. Offline CLI builds or fast citation checks would hang or fail.
- **Verdict:** Rejected due to offline fragility.

### Approach 3: Direct SQLite Read-Write
- **Architecture:** Performing SQL `INSERT` into `itemNotes` directly.
- **Trade-offs:** No dependency on Zotero running, but carries high risk of database corruption, SQLite WAL write lock contention, and cache desynchronization with the running Zotero GUI.
- **Verdict:** Strictly rejected as unsafe.

---

## 5. Architectural Components

```
+---------------------------------------------------------------------------------+
|                                 SciFi CLI / MCP                                 |
|         (sf zotero sync | sf zotero audit | scifi_zotero_push_audit_note)        |
+----------------------------------------+----------------------------------------+
                                         |
                                         v
+---------------------------------------------------------------------------------+
|                       scifi.literature.zotero Package                          |
|                                                                                 |
|   +------------------------------------+   +--------------------------------+   |
|   |         ZoteroLocalReader          |   |       ZoteroLocalWriter        |   |
|   |   (Direct SQLite, immutable=1)     |   |   (HTTP to 127.0.0.1:23119)    |   |
|   | - get_collections()                |   | - push_audit_card_note()       |   |
|   | - get_collection_items(col_id)     |   | - apply_tags(item_key, tags)   |   |
|   | - get_pdf_path(item_key)           |   | - stage_offline_writes()       |   |
|   | - get_user_annotations(item_key)   |   +--------------------------------+   |
|   +-----------------+------------------+                                        |
+---------------------|-----------------------------------------------------------+
                      |
                      v
+---------------------------------------------------------------------------------+
|                         Local Storage & Desktop App                             |
|                                                                                 |
|   +-----------------------------------+    +--------------------------------+   |
|   |   C:\Users\...\Zotero             |    |     Zotero Desktop App         |   |
|   |   - zotero.sqlite (read-only)     |    |     - Running on port 23119    |   |
|   |   - storage/<key>/paper.pdf       |    |     - GUI reflects sync notes  |   |
|   +-----------------------------------+    +--------------------------------+   |
+---------------------------------------------------------------------------------+
```

### 5.1 Configuration (`.scifi/config.json`)
The project workspace configures the link to Zotero:
```json
{
  "zotero": {
    "enabled": true,
    "data_dir": "C:/Users/Betagors/Zotero",
    "collection": "UAV",
    "port": 23119,
    "api_key": null,
    "auto_tag": true,
    "sync_bib": "references.bib"
  }
}
```
*Note on Auth:* The local API (`http://127.0.0.1:23119/api/users/0/...`) will attempt requests without an API key first (supported when local third-party communication is enabled in Zotero Preferences). If an API key is required by Zotero, it can be provided via `"api_key"` in config or the `ZOTERO_API_KEY` environment variable. `sf zotero status` validates this auth handshake.

### 5.2 Reader Subsystem (`reader.py`)
Queries `zotero.sqlite` using:
```python
db_uri = f"file:///{data_dir}/zotero.sqlite?immutable=1"
conn = sqlite3.connect(db_uri, uri=True, timeout=10.0)
```
- **Collection Scoping:** Resolves `collectionID` from `collections` matching the configured name, and joins `collectionItems` to retrieve active paper keys.
- **PDF Resolution:** Queries `itemAttachments` for the item's attachment record where `contentType = 'application/pdf'`. Strips the `storage:` prefix and resolves the absolute path:
  `Path(data_dir) / "storage" / attachment_key / filename`.
- **Annotation Extraction:** Queries `itemAnnotations` for highlights (`type=1`) and comments on the PDF attachment, extracting `text`, `comment`, `color`, and `pageLabel`.

### 5.3 Writer Subsystem & Mutation Semantics (`writer.py`)
Communicates with Zotero's local server (`http://127.0.0.1:23119`):
- **Ping / Health Check:** Verifies server availability and authorization on port 23119.
- **Upsert Child Note Lifecycle:** Every SciFi audit card contains an embedded HTML marker: `<div class="scifi-audit-card" data-scifi-version="1.0">`. Before creating a new note, `writer.py` queries existing child notes under the parent item. If an existing SciFi audit card note is found, it issues a `PATCH` request with `If-Unmodified-Since-Version` to update the note in place. If none exists, it issues a `POST` request. This guarantees deduplication and clean library hygiene.
- **Parent Item Tagging Semantics:** Status tags (`#scifi-audited`, `#scifi-verified`, `#unstated-assumption`, `#retraction-or-concern`, `#benchmark-sota`) are applied directly to the **top-level parent item** (not the child note) so they render as visual color-coded badges in the main Zotero table. When updating tags:
  1. Retrieves existing parent item tags via `GET /api/users/0/items/<key>`.
  2. Preserves all user-authored tags.
  3. Replaces outdated SciFi tags (e.g. removes `#unstated-assumption` if the audit now passes as `#scifi-verified`).
  4. Patches the parent item with the merged tag set.
- **Offline Staging Queue:** When Zotero is closed or port 23119 is unreachable:
  - Unsent audit notes and tag updates are persisted to `.scifi/zotero_write_queue.json`.
  - Staged mutations are automatically replayed and flushed whenever `sf zotero sync`, `sf zotero audit`, or `sf zotero flush` runs with Zotero active.

### 5.4 Dynamic Smart Folders (Saved Searches)
Saved Searches are provisioned via `sf zotero init-searches` or during `sf zotero sync`:
- `SciFi: Pending Audit`: `collection is <name>` AND `tag isNot #scifi-audited`
- `SciFi: Flagged Assumptions`: `collection is <name>` AND `tag is #unstated-assumption`
- `SciFi: SOTA Benchmarks`: `collection is <name>` AND `tag is #benchmark-sota`
- `SciFi: Verified Complete`: `collection is <name>` AND `tag is #scifi-verified`

### 5.5 Scaffolding & Legacy Migration Engine (`scifi/scaffold.py` & `scifi/adapt.py`)
Provides one-command project initialization and legacy codebase onboarding:
- **`sf init` / `sf scaffold` (New Projects):**
  1. Bootstraps the standardized 2-pillar project structure:
     - `paper/` (`main.tex`, `macros.tex`, `references.bib`, `sections/`, `figures/`, `tables/`)
     - `code/` (`src/`, `scripts/`, `data/`, `results/`, `pyproject.toml`)
     - `.scifi/` (`config.toml`, `literature.db`, `reviews/`, `submissions/`)
  2. Auto-detects local Zotero installation (`~/Zotero`).
  3. Interactive/CLI selection of Zotero collection: lists existing collections (e.g. `UAV`, `NN Verification`) or creates a new collection matching the project title.
  4. Generates `.scifi/config.toml` binding the project to the selected venue and Zotero collection.
- **`sf adapt` (Legacy Project Migration):**
  1. Scans existing repository (flat, messy, or monolithic).
  2. Safely categorizes files into publication artifacts (`paper/`) and computational artifacts (`code/`) with dry-run verification.
  3. Parses existing `.bib` files, extracts cited DOIs, arXiv IDs, and titles.
  4. Queries local `zotero.sqlite` to cross-reference legacy references against the user's Zotero library, reporting matched vs. missing papers.
  5. Links the migrated repository to the matched or newly created Zotero collection and synchronizes `paper/references.bib`.

### 5.6 Graceful Self-Healing & Prerequisite Manager (`scifi/env.py`)
Ensures zero-friction developer experience across all environments:
- **`uv` Management:** Checks if `uv` is installed and on PATH. If missing:
  - Offers to auto-install `uv` using the official standalone installer.
  - If network or permissions prevent installation, falls back seamlessly to `python -m venv` and standard `pip` without failing or crashing.
- **Zotero Path Auto-Discovery:** Automatically inspects standard platform directories:
  - Windows: `~/Zotero` or registry lookup.
  - macOS: `~/Zotero` or `~/Library/Application Support/Zotero`.
  - Linux: `~/Zotero` or `~/.zotero`.
  If found, zero manual path entry is needed.
- **Offline & Graceful Zotero Degradation:**
  - If Zotero is not running: read operations use zero-copy SQLite (`immutable=1`) without interruption; write operations append silently to `.scifi/zotero_write_queue.json` and report "Audited locally; 1 note staged to sync on next Zotero launch."
  - If Zotero is not installed: literature commands fall back to direct web resolution (Unpaywall, arXiv API, OpenAlex) without breaking the workflow.
- **`sf doctor --fix`:** Diagnoses all local tools (TeX compiler, `uv`, Python environment, Zotero database, port 23119) and applies automatic remediation wherever possible.

### 5.4 Literature Fetcher Integration (`scifi/literature/fetcher.py`)
Update `find_local_pdf(paper, ...)`:
Before searching local project workspace directories, if `zotero` is enabled, query `ZoteroLocalReader` by DOI, arXiv ID, or title. If a matching PDF exists in `storage/`, return that path immediately. This achieves zero-copy, instantaneous PDF access.

---

## 6. Data Models (`scifi/literature/zotero/models.py`)

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

@dataclass
class ZoteroAnnotation:
    id: int
    parent_item_key: str
    type: int  # 1: highlight, 2: note, 3: image
    text: Optional[str]
    comment: Optional[str]
    color: Optional[str]
    page_label: Optional[str]

@dataclass
class ZoteroItem:
    item_id: int
    key: str
    title: str
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    year: Optional[int] = None
    abstract: Optional[str] = None
    publication_title: Optional[str] = None
    pdf_path: Optional[Path] = None
    annotations: List[ZoteroAnnotation] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

@dataclass
class ZoteroAuditCard:
    item_key: str
    contribution: str
    assumptions_flagged: List[str]
    benchmarks_extracted: List[dict]
    math_verified: bool
    retraction_status: str
```

---

## 7. Command-Line & Tool Interface

### Project Onboarding & Scaffolding Commands
- `sf init` / `sf scaffold [--venue VENUE] [--collection NAME] [--title TITLE]`: Bootstraps the standardized 2-pillar project structure and configures Zotero collection binding.
- `sf adapt [--dry-run] [--venue VENUE] [--collection NAME]`: Migrates a legacy messy or flat academic repository into standard `paper/` and `code/` layout, cross-referencing `.bib` files against Zotero.
- `sf doctor [--fix]`: Diagnoses environment dependencies (`uv`, LaTeX toolchain, Zotero database, port 23119) with one-click automatic fixes.

### Zotero Literature Commands (`sf zotero`)
- `sf zotero status`: Checks local SQLite existence, counts items, verifies port 23119 & auth, and checks the configured collection.
- `sf zotero sync [--create-searches]`: Scans the collection, reconciles new papers with SciFi's internal SQLite store, updates `references.bib`, flushes staged writes, and identifies papers pending audit.
- `sf zotero audit [--key KEY] [--all]`: Runs SciFi audits (assumptions, benchmarks, proofs) on papers in the collection and pushes formatted audit notes back to Zotero (in-place upsert).
- `sf zotero init-searches`: Generates dynamic project-scoped Saved Searches in Zotero (`Pending Audit`, `Flagged Assumptions`, etc.).
- `sf zotero flush`: Explicitly replays and flushes any staged offline writes to Zotero when the desktop app is opened.
- `sf zotero annotations [--key KEY]`: Dumps human highlights and comments extracted from the PDF in Zotero.

### FastMCP Tools (`scifi/server.py`)
- `scifi_zotero_status() -> dict`: Returns health status and collection summary.
- `scifi_zotero_get_collection_papers(collection: str = None) -> list`: Retrieves papers in the collection with local PDF paths.
- `scifi_zotero_get_annotations(item_key: str) -> list`: Returns user highlights and notes.
- `scifi_zotero_push_audit_note(item_key: str, audit_data: dict) -> dict`: Pushes an audit card child note.

---

## 8. Verification & Test Plan

1. **Unit Tests (`tests/test_zotero.py`):**
   - Test SQLite connection with `immutable=1` against mock SQLite fixtures.
   - Test extraction of DOIs, arXiv IDs, and attachment paths from schema.
   - Test HTML formatting of `ZoteroAuditCard`.
   - Test graceful fallback when Zotero path is missing or port 23119 is unreachable.
2. **Integration Verification:**
   - Execute `sf zotero status` against actual local `C:\Users\Betagors\Zotero`.
   - Confirm collection `UAV` is recognized with all member papers.
   - Confirm PDF resolution correctly resolves `Zhang et al. - 2020` without copying.
3. **Regression Safety:**
   - Run `pytest tests/test_literature.py` to ensure `find_local_pdf` and existing literature tools maintain 100% backward compatibility.
