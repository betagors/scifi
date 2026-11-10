# SciFi Project Scaffolding, Adaptation & Multi-Venue Variance Design Document

**Date:** 2026-11-09  
**Status:** In Review  
**Topic:** Scaffolding fresh academic projects, adapting existing mixed repositories, standardizing `.scifi/` project state, and managing multi-venue LaTeX template variance.

---

## 1. Intent & The Why

Academic researchers frequently face two related bottlenecks:
1. **Repository Disorganization & Friction:** Code, LaTeX files, raw data, and experiment output logs get jumbled in a single repository without clean boundaries. Onboarding SciFi's auditing, attribution, and reproducibility tools on messy or legacy codebases requires significant manual restructuring.
2. **Venue Transition Hell:** Manuscripts submitted to one venue (e.g., NeurIPS) frequently need adaptation for another (e.g., IEEE Transactions or ACM Conference) after peer review or scoping changes. Each venue has radically conflicting documentclasses, author/affiliation syntaxes, bibliography engines, and column formats. Researchers often duplicate the entire project or create fragmented branches, leading to synchronization drift, outdated equations, and broken cross-references.

This project delivers:
- A standardized **2-pillar research repository structure** (`paper/` + `code/` orchestrated by `.scifi/`).
- Automated project scaffolding (`sf scaffold` / `sf init`) for bootstrapping new papers.
- Intelligent project adaptation (`sf adapt`) for reorganizing existing mixed repositories and decomposing monolithic LaTeX files into modular sections.
- A decoupled **Multi-Venue Variance Engine** (`sf venue add`, `sf venue switch`, `sf venue list`, `sf authors sync`) that allows compiling multiple venue targets from shared content without clobbering LaTeX files or maintaining diverged forks.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- **Standardized 2-Pillar Layout:** Establish a consistent layout across all SciFi projects:
  - `paper/` holds publication artifacts (LaTeX sections, figures, tables, macros, bib).
  - `code/` holds computational artifacts (src, scripts, data, results).
  - `.scifi/` holds workflow orchestration, metadata (`config.toml`), local literature DB, review reports, and submission bundles.
- **Automated Scaffolding (`sf scaffold` / `sf init`):** Generate a publication-ready paper skeleton in seconds, pre-configured for target venues (IEEE, ACM, NeurIPS, Springer, Elsevier, or general journal) with verified booktabs, vector figure stubs, and semantic macros.
- **Intelligent Project Adaptation (`sf adapt`):** Scan an existing repository (whether flat, messy, or monolithic), identify code vs. LaTeX files, safely reorganize them into `paper/` and `code/`, extract monolithic `\section` blocks into `sections/*.tex`, isolate math definitions into `macros.tex`, and initialize `.scifi/`.
- **Decoupled Multi-Venue Variance:** Enable researchers to target multiple venues simultaneously. Provide thin entrypoint wrappers (`paper/main_ieee.tex`, `paper/main_neurips.tex`) that include shared `paper/sections/`, while syncing author metadata from `.scifi/config.toml` via `sf authors sync`.
- **Targeted Compilation:** Support compiling specific venue targets directly (`sf compile --venue neurips` or `sf compile --all`).
- **Complete Offline Independence:** The resulting LaTeX project in `paper/` must be 100% standard LaTeX. It must compile cleanly on Overleaf, arXiv, or vanilla TeX Live without requiring SciFi or Python to be installed.

### Non-Goals
- Building a LaTeX-to-Word or LaTeX-to-HTML transpiler.
- Hosting an online template repository; bundled standard templates (IEEE, ACM, NeurIPS, Springer, Elsevier) and local custom templates will be supported.
- Modifying or executing arbitrary user training code during `sf adapt`.

### Anti-Goals
- **No In-Place Template Clobbering:** Never rewrite an author's custom LaTeX preamble or hand-tuned styling without explicit flags.
- **No Monolithic Conditional Macros:** Never inject brittle `\ifvenue` conditional preambles that break documentclass parsing or conflict with package loading orders (e.g. `hyperref` vs `natbib`).
- **No Data Loss during Adaptation:** Never delete, overwrite, or destructively move uncommitted user code or text without dry-run confirmation and backup safeguards.

---

## 3. Constraints

- **Python Compatibility:** Python >= 3.12, strict type hints, dataclasses.
- **Zero Mandatory External C-Extensions or Compilers:** Scaffolding and adaptation must execute offline in pure Python with standard libraries and existing project dependencies (`bibtexparser`, `pypdf`, `tomllib`).
- **Compatibility with Existing SciFi Modules:**
  - Multi-file project resolver (`scifi.latex.project.resolve_latex_project`).
  - Venue compliance auditor (`scifi.latex.venue.check_venue_compliance`).
  - Publisher profiles (`scifi.submission.profiles.PUBLISHER_PROFILES`).
  - Reproducibility auditor (`scifi.reproducibility.auditor.audit_reproducibility`).
  - Submission packaging suite (`scifi.submission.bundler.prepare_submission_bundle`).
- **Standard LaTeX Ergonomics:** All generated templates must follow SciFi academic rules (e.g., `booktabs` tables, vector figures, `\xspace` macro definitions, upright math subscripts `$W_{\mathrm{loss}}$`).

---

## 4. Approaches Considered

| Approach | Description | Trade-offs & Evaluation | Decision |
|---|---|---|---|
| **1. Decoupled Venue Entrypoints with Shared Sections** | Core manuscript lives venue-agnostically in `paper/sections/`, `paper/tables/`, `paper/figures/`, and `paper/macros.tex`. Each target venue has a lightweight entrypoint wrapper (`paper/main_neurips.tex`, `paper/main_ieee.tex`) importing venue styles and `\input{sections/...}`. `main.tex` links to the active venue. `sf authors sync` writes venue-specific `\author` blocks from `.scifi/config.toml`. | **Pros:** 100% standard LaTeX, zero fragile AST transpilation, both versions can be compiled and reviewed side-by-side, Overleaf/arXiv compatible.<br>**Cons:** Multiple entrypoint wrappers in `paper/`. | **SELECTED (User approved)** |
| **2. Single Entrypoint In-Place Transformation** | Only `paper/main.tex` exists. Running `sf venue switch ieee` rewrites the preamble and author block of `main.tex` using an internal template engine. | **Pros:** Single file.<br>**Cons:** High risk of clobbering manual edits, package configurations, or custom tweaks when switching back and forth. Hard to diff venues side-by-side. | Rejected |
| **3. Conditional Compilation Preambles (`\ifvenue`)** | Single `main.tex` wrapping competing documentclasses and author blocks in TeX conditionals. | **Pros:** Single file, native TeX.<br>**Cons:** Incompatible documentclasses and package collisions (e.g. `acmart` vs `IEEEtran`) cause catastrophic compilation errors in TeX parsers. | Rejected |

---

## 5. System Architecture & Detailed Design

### 5.1 Standard Project Layout

When a research project is scaffolded or adapted, it adheres to:

```text
<project-root>/
├── .scifi/
│   ├── config.toml             # Project manifest (metadata, active & target venues, authors)
│   ├── literature.db           # SQLite citation & benchmark cache
│   ├── reviews/                # Reviewer feedback, rebuttal letters, diffs
│   ├── submissions/            # Generated anonymous submission bundles
│   └── cache/                  # Fast API caches & downloaded preprints
├── paper/                      # Primary LaTeX manuscript directory
│   ├── main.tex                # Symlink or active copy pointing to active venue entrypoint
│   ├── main_ieee.tex           # Target wrapper: IEEE Transactions
│   ├── main_neurips.tex        # Target wrapper: NeurIPS Conference
│   ├── macros.tex              # Reusable mathematical and semantic macros
│   ├── references.bib          # Bibliography file
│   ├── sections/               # Modular manuscript text
│   │   ├── 01_abstract.tex
│   │   ├── 02_introduction.tex
│   │   ├── 03_related_work.tex
│   │   ├── 04_methodology.tex
│   │   ├── 05_experiments.tex
│   │   └── 06_conclusion.tex
│   ├── figures/                # Vector PDF/SVG figures and scripts
│   └── tables/                 # Standalone modular LaTeX tables
└── code/                       # Complete computational artifact
    ├── src/                    # Model and algorithm implementations
    ├── scripts/                # Experiment execution and evaluation scripts
    ├── data/                   # Benchmark datasets, sample inputs, downloaders
    ├── results/                # Raw metric outputs (CSV, JSON, checkpoints)
    └── pyproject.toml          # Or environment.yml / requirements.txt
```

### 5.2 The `.scifi/config.toml` Schema

```toml
[project]
name = "adaptive-distributed-optimization"
title = "Provably Robust Optimization for Constrained Wireless Fleets"
active_venue = "neurips"
target_venues = ["neurips", "ieee"]
double_blind = true

[[authors]]
name = "Jane Doe"
email = "jane.doe@university.edu"
affiliation = "Department of Computer Science, University of Science"
orcid = "0000-0002-1825-0097"
corresponding = true

[[authors]]
name = "John Smith"
email = "jsmith@institute.org"
affiliation = "AI Research Institute"
orcid = "0000-0001-5109-3700"
corresponding = false

[manuscript]
paper_dir = "paper"
main_entrypoint = "main.tex"
bib_file = "references.bib"
macros_file = "macros.tex"

[code]
code_dir = "code"
data_dir = "code/data"
results_dir = "code/results"
```

### 5.3 Author Metadata Transformer (`scifi/venue/authors.py`)

Different venues require wildly disparate author block formats:
- **IEEE:**
  ```latex
  \author{Jane~Doe,~\IEEEmembership{Member,~IEEE,} and John~Smith%
  \thanks{Jane Doe is with the Department of Computer Science...}%
  \thanks{John Smith is with AI Research Institute...}}
  ```
- **ACM (`acmart`):**
  ```latex
  \author{Jane Doe}
  \email{jane.doe@university.edu}
  \orcid{0000-0002-1825-0097}
  \affiliation{%
    \institution{University of Science}
    \department{Department of Computer Science}
  }
  ```
- **NeurIPS / OpenReview:**
  ```latex
  % When anonymous:
  \author{Anonymous Authors\\Paper ID 1234}
  % When camera-ready:
  \author{Jane Doe\\University of Science\\\texttt{jane.doe@university.edu}\And John Smith\\AI Research Institute\\\texttt{jsmith@institute.org}}
  ```
- **Elsevier (`elsarticle`):**
  ```latex
  \author[inst1]{Jane Doe\corref{cor1}}
  \ead{jane.doe@university.edu}
  \affiliation[inst1]{organization={University of Science}, department={Department of Computer Science}}
  ```

The author transformer reads `[[authors]]` from `.scifi/config.toml` and generates the exact TeX block for the given venue. `sf authors sync` updates these blocks across all `main_<venue>.tex` files or writes an included `authors_<venue>.tex`.

### 5.4 Scaffolding Engine (`scifi/scaffold/`)

- Command: `sf scaffold [PATH] [--venue VENUE] [--title TITLE]`
- Creates the standardized directory tree.
- Copies clean, verified venue entrypoint templates, standard `macros.tex`, and sample `sections/`.
- Initializes `.scifi/config.toml` and `.scifi/literature.db`.
- Sets up `.gitignore` ignoring build artifacts (`*.aux`, `*.bbl`, `*.fls`, `.scifi/cache/`, `code/data/large_files`).
- Automatically installs agent rules (`AGENTS.md`, `.cursorrules`, etc.) via existing `sync_all_rules`.

### 5.5 Adaptation Engine (`scifi/adapt/`)

- Command: `sf adapt [PATH] [--venue VENUE] [--dry-run]`
- **Inspection Phase:**
  1. Recursively scans the directory.
  2. Categorizes files into:
     - LaTeX sources (`.tex`, `.bib`, `.sty`, `.cls`, `.bst`).
     - Figures (`.pdf`, `.png`, `.jpg`, `.svg`).
     - Code files (`.py`, `.sh`, `.cpp`, `.cu`, `requirements.txt`, `pyproject.toml`).
     - Data files (`.csv`, `.json`, `.h5`, `.parquet`).
  3. Detects if code and paper are already split or mixed at root.
- **Decomposition Phase:**
  1. If a monolithic `main.tex` exists with inline `\section{...}`:
     - Parses sections and extracts each into `paper/sections/XX_<slug>.tex`.
     - Replaces inline sections with `\input{sections/XX_<slug>}`.
  2. Extracts `\newcommand`, `\DeclareMathOperator`, and `\def` blocks into `paper/macros.tex`.
  3. Detects current document class (e.g. `\documentclass{IEEEtran}` -> venue `ieee`) and renames `main.tex` to `paper/main_<venue>.tex`, symlinking/copying to `paper/main.tex`.
- **Migration & Reorganization:**
  1. Moves code files to `code/`, data to `code/data/`.
  2. Moves LaTeX, bib, and figures to `paper/`.
  3. Creates `.scifi/` and populates `config.toml` with inferred authors (from `\author{...}`) and venue.
  4. Provides `--dry-run` to preview all proposed file moves and modifications before writing.

### 5.6 Venue Switcher & Multi-Compile (`scifi/venue/`)

- `sf venue list`: Lists configured target venues, active venue, and compliance status.
- `sf venue add <name>`: Adds a new venue entrypoint wrapper (`paper/main_<name>.tex`), pulling necessary style templates.
- `sf venue switch <name>`: Switches the active target in `.scifi/config.toml` and updates `paper/main.tex`.
- `sf compile [--venue <name>] [--all]`: Invokes `compiler.py` on the specified venue wrapper (or all target wrappers in sequence), verifying that each compiles without errors and saving the resulting PDFs to `.scifi/build/` or `paper/`.

---

## 6. What's Left to the Builder

- Exact list of bundled starter templates: IEEE (`IEEEtran`), ACM (`acmart`), NeurIPS (`neurips_2024`), Elsevier (`elsarticle`), Springer (`sn-jnl`), and General Journal.
- Heuristic logic for parsing monolithic `.tex` files in `sf adapt` (handling comments, appendices, and starred sections).
- Command-line flag parsing nuances in `scifi/cli.py` and FastMCP tool registrations in `scifi/server.py`.
- Comprehensive automated test suite in `tests/test_scaffold.py`, `tests/test_adapt.py`, and `tests/test_venue_variance.py`.

---
