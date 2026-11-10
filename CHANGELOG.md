# Changelog

All notable changes to the SciFi project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-10

### Added
- **Unified Academic CLI & FastMCP Daemon**:
  - `sf verify` / `alex`: Automated citation verification against Crossref, OpenAlex, arXiv, and DataCite.
  - `sf audit`: Retraction and errata detection across `.bib` bibliographies.
  - `sf argus`: Academic attribution sentinel, uncredited algorithm detection, and plagiarism auditing.
  - `sf math` / `turing`: Symbolic calculus, Pint physical dimensional homogeneity, matrix shapes, limits, and convexity verification via SymPy.
  - `sf stats` / `gauss`: Closed-form theoretical formula vs. empirical simulation verification, CLT sample size auditing ($N \ge 30$).
  - `sf review` / `popper`: Adversarial peer-review scanner for unstated assumptions and fragile baselines.
  - `sf shannon`: Title engineering, 5-beat dual-audience abstract evaluation, and SEO keyword non-redundancy scoring on a 100-point rubric.
  - `sf human`: Master academic humanizer protocol eradicating synthetic AI vocabulary, em dashes, bold-colon list clones, and flattened burstiness.
  - `sf table`: Publication-grade LaTeX `booktabs` generation with bolded state-of-the-art metrics.
  - `sf venue`: Multi-file LaTeX manuscript auditing for conference compliance and double-blind identity leaks.
  - `sf figures` / `da-vinci`: DPI verification ($\ge 300\text{ DPI}$), vector plot checking, subfigure parity, and colorblind-safe palette analysis.
  - `sf trim` / `layout`: Page budget slack analysis, orphan/widow line pruning, and ISO-4/IEEE BibTeX venue abbreviation.
  - `sf proofs` / `euclid`: Theorem-proof completeness auditing and appendix label resolution.
  - `sf repro` / `bacon`: Conference reproducibility checklist auditing (seeds, trial repetitions, compute accelerators, and repository anonymization).
  - `sf rebuttal`: Point-by-point 4-beat rebuttal response scaffolding and manuscript diff tracking via `latexdiff`.
  - `sf submission`: Academic paper packaging suite (cover letters, character-capped research highlights, standalone unblinded title pages, and reproducible anonymous code packaging).
- **Zotero 10 Integration & Scaffolding**:
  - Zero-copy local SQLite reader (`zotero.sqlite` with `immutable=1` URI mode).
  - Local HTTP note and tag dispatcher with offline staging (`.scifi/zotero_write_queue.json`).
  - Standardized 2-pillar project scaffolding (`paper/` + `code/` via `sf scaffold`/`sf init`).
  - Legacy codebase adaptation engine (`sf adapt`).
- **Web Research Cockpit**:
  - Embedded local dashboard (`sf ui` / `sf cockpit`) for real-time visualization of literature graphs, SOTA leaderboards, and audit cards.
- **Dual-Channel Distribution & Release Suite**:
  - `sf package`: Automated generation of PyPI wheels/sdists and standalone AI Agent Plugin zip (`scifi-plugin-v1.0.0.zip`).
  - Embedded canonical academic rules in package resources (`scifi.resources/AGENTS.md`).
  - Zero-install `uvx scifi server` configuration option for global MCP clients via `sf setup --use-uvx`.
  - GitHub Actions CI matrix with Python 3.12 and 3.13 and tag-triggered OIDC release workflow.
