# SciFi Submission Suite Design Document

**Date:** 2026-11-09  
**Author:** Antigravity  
**Status:** In Review  
**Target Module:** `scifi/submission/`  

---

## 1. Intent & Context

When submitting an academic manuscript to journals (Elsevier, IEEE, Springer, Nature, ACM) or conferences (NeurIPS, ICML, CVPR, ACL), authors must prepare a battery of specialized artifacts beyond the main paper text:
1. **Editorial Cover Letter**: A professional letter addressed to the Editor-in-Chief highlighting paper significance, relevance to the journal's scope, ethical/originality declarations, and reviewer suggestions.
2. **Research Highlights**: 3–5 punchy bullet points encapsulating novel findings and methodology, subject to strict length constraints (e.g. Elsevier's 85-character ceiling per bullet).
3. **Dedicated Title Page ("Title Paper")**: An unblinded metadata document (authors, affiliations, corresponding author details, funding acknowledgments, conflicts of interest) required when the main manuscript is submitted blinded to ensure double-blind review fairness.
4. **Reproducible Anonymous Code Package**: An anonymized `.zip` archive stripped of all git history, commit IDs, author names, local path leaks (`C:\Users\...`), and environment secrets, bundled with a turnkey reproduction script.

Currently, SciFi audits double-blind compliance (`sf venue`) and reproducibility checklists (`sf repro`), but offers zero tooling to synthesize or package these four essential submission artifacts.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- **Automated Metadata Extraction**: Extract manuscript title, abstract, authors, and affiliations directly from `main.tex` (or markdown) via `resolve_latex_project`.
- **Editorial Cover Letter Generator**: Generate disciplined, publication-ready cover letters in Markdown and LaTeX format, parameterized by journal name, ISSN, or URL, with optional teaser figure callouts and prior conference DOI/extension statements.
- **Highlights Generator & Validator**: Generate and validate 3–5 bullet points against venue constraints (Elsevier 85 characters, IEEE, Nature), checking character counts and active phrasing.
- **Review Fairness Title Page**: Generate a clean `title_page.tex` and Markdown file with complete unblinded author and institutional disclosures, allowing the primary manuscript to remain strictly anonymized.
- **Reproducible Anonymous Code Packager**: Audit and bundle code into `anonymous_code.zip`, scrubbing `.git`, author usernames, local user paths, OS junk, and sensitive files, and adding a reproduction template (`reproduce.py` / `run.sh` + environment manifest).
- **All-in-One Submission Bundler**: Provide a single command (`sf submission bundle`) that generates a clean `dist/submission/` directory containing all four artifacts and a manifest.
- **FastMCP & CLI Integration**: Expose both individual CLI subcommands (`sf submission letter`, `sf submission highlights`, `sf submission title-page`, `sf submission pack-code`) and FastMCP tools.

### Non-Goals
- Web-scraping journal submission portals or automated submission uploads (SciFi prepares the files on disk for author upload).
- Cloud storage uploads or third-party anonymous hosting accounts (Anonymous GitHub, Zenodo); output is local `.zip` and LaTeX/Markdown files.

### Anti-Goals
- **Zero AI Clichés / Slop**: No marketing buzzwords (*delve*, *pivotal*, *groundbreaking*, *testament*) in cover letter templates.
- **Zero Accidental Leaks in Code Zip**: Never include `.git` objects, author git config, or un-scrubbed local user paths in the anonymized code archive.

---

## 3. Constraints

- **Python Runtime**: Python >= 3.12.
- **Dependencies**: Use existing project dependencies (`pypdf`, `bibtexparser`, standard library `zipfile`, `re`, `json`, `pathlib`). No heavy C-extensions or mandatory network calls.
- **Execution Speed**: Offline artifact generation and zip packaging must complete in < 1 second for standard repositories.
- **Multi-File LaTeX Compatibility**: Seamlessly integrate with `scifi.latex.project.resolve_latex_project` to handle split manuscript architectures.

---

## 4. Approaches Considered

### Approach A: Dedicated Submission Suite (`scifi/submission/`) *(Selected)*
Create a dedicated subpackage `scifi/submission/` housing:
- `cover_letter.py`
- `highlights.py`
- `title_page.py`
- `code_packager.py`
- `models.py`
- `bundler.py`
CLI exposed via `sf submission <subcommand>` (with convenient top-level aliases like `sf letter`, `sf highlights`, `sf title-page`, `sf pack-code`).
*Why chosen:* Clean modular boundary, cohesive submission artifact lifecycle, easily testable in isolation without cluttering `reproducibility/` or `latex/`.

### Approach B: Dispersed into Existing Modules
Spread `code_packager.py` into `reproducibility/`, `highlights.py` into `shannon.py`, and `cover_letter.py`/`title_page.py` into `latex/`.
*Rejected:* Fragments pre-submission workflows across unrelated modules and prevents a unified submission bundle workflow.

### Approach C: Template-Only Static Scaffolds
Supply barebones text templates with prompt placeholders.
*Rejected:* Cannot parse `main.tex`, cannot validate character constraints, and cannot safely scrub repository files for anonymous double-blind code packages.

---

## 5. Detailed Architecture & Components

### 5.0 Publisher Profiles (`scifi/submission/profiles.py`)
To handle distinct requirements across publishers, the suite defines tailored venue profiles:
- **`elsevier`**:
  - Highlights: Strictly 3–5 bullets, rigid **85 characters including spaces** limit per bullet, active verb enforcement.
  - Title Page: Includes CRediT authorship contribution taxonomy, corresponding author phone/email, and Declaration of Competing Interests.
  - Cover Letter: Formal Elsevier editorial salutation, statement of novelty, and mandatory reviewer nominations.
- **`ieee`**:
  - Highlights: Optional/flexible (100 char limit).
  - Cover Letter: Tailored for IEEE Transactions; includes the mandatory **Prior Conference Extension** section certifying >= 30–60% significant new technical material and citing the original conference paper.
  - Title Page: Standard IEEE unblinded header with author affiliations, member grades (IEEE Student/Member/Senior Member), and EDAS/ScholarOne paper tracking IDs.
- **`springer` / `nature`**:
  - Cover Letter & Title Page: Emphasizes Springer Nature standard ethical disclosures (Data Availability Statement, Code Availability, Human/Animal ethics approval, Competing Interests).
- **`acm`**:
  - Title Page & Packager: Formatted with ACM Computing Classification System (CCS) tags and Artifact Badging readiness (Available, Evaluated, Replicated).
- **`openreview` / `neurips` / `icml` / `cvpr`**:
  - Double-Blind Conference mode: Focuses on the anonymous reproducible code package and blinded submission checks.
- **`general`**: Balanced academic defaults for general journals and venues.

### 5.1 Metadata Resolution Hierarchy
Where author and submission metadata is obtained:
1. **`scifi.toml` `[submission]` (Primary & Recommended)**: Stored in project config for repeatable, version-controlled packaging. Supports `journal`, `venue`, `issn`, `editor`, `prior_doi`, and `[[submission.authors]]` with `name`, `affiliation`, `email`, `orcid`, `is_corresponding`, `credit_roles`.
2. **CLI Flags / JSON File (Override)**: Pass `--metadata submission.json` or CLI flags (`--journal`, `--authors`, `--funding`).
3. **Manuscript Extraction (Fallback)**: When `main.tex` is single-blind/unblinded, extracts title, abstract, authors, and affiliations automatically via `resolve_latex_project`. If double-blind and no config exists, outputs clean placeholder tokens (`<INSERT CORRESPONDING AUTHOR EMAIL>`).

### 5.2 Models (`scifi/submission/models.py`)
- `AuthorInfo`: `name`, `affiliation`, `email`, `orcid`, `is_corresponding`, `credit_role`.
- `CoverLetterRequest`: `venue`, `journal_name`, `issn`, `editor_name`, `manuscript_title`, `authors`, `abstract`, `contributions`, `figure_path`, `prior_doi`, `code_link`, `suggested_reviewers`, `opposed_reviewers`.
- `CoverLetterResult`: `markdown_text`, `latex_text`, `output_path`.
- `HighlightItem`: `text`, `char_count`, `max_allowed`, `is_valid`, `issue`.
- `HighlightsResult`: `highlights`, `venue`, `max_chars`, `all_valid`, `markdown_text`, `latex_text`.
- `TitlePageResult`: `latex_text`, `markdown_text`, `output_path`.
- `CodePackagerResult`: `zip_path`, `files_included`, `files_excluded`, `scrubbed_leaks`, `audit_passed`, `audit_report`.
- `SubmissionBundleResult`: `output_dir`, `venue`, `cover_letter_path`, `highlights_path`, `title_page_path`, `code_zip_path`, `manifest_path`.

### 5.3 Cover Letter Generator (`scifi/submission/cover_letter.py`)
- Resolves journal profile (Elsevier, IEEE, Springer, ACM, General).
- Formats letter in both Markdown and LaTeX letter class:
  1. Editor & Journal Heading (auto-populated by ISSN or journal name).
  2. Core hook & manuscript type.
  3. Novelty & alignment with journal scope.
  4. Publisher-specific mandatory clauses (e.g. IEEE conference extension clause, Springer ethics statements, Elsevier originality declaration).
  5. Graphical Abstract / Teaser figure callout and Data/Code availability links.
  6. Suggested & Opposed Reviewers table.

### 5.4 Highlights Generator & Validator (`scifi/submission/highlights.py`)
- Extracts or parses 3–5 bullet points.
- Validates each bullet against publisher ceiling:
  - `elsevier`: 85 characters max.
  - `ieee` / `springer` / `general`: 100 characters max.
- Highlights violations with exact character counts and suggested concise rephrasing (stripping filler like "In this paper we present...").
- Emits Markdown, plain text, and LaTeX `\begin{itemize}`.

### 5.5 Title Page Generator (`scifi/submission/title_page.py`)
- Generates a standalone, unblinded `title_page.tex` (and markdown) with:
  - Matching manuscript title.
  - Author roster with indexed departmental/institutional affiliations.
  - Corresponding author block (email, telephone, postal address, ORCID).
  - CRediT authorship statement (Elsevier mode) or standard author contributions.
  - Funding acknowledgments, grant numbers, and conflict of interest disclosures.
  - Data and code availability statements.
- Guarantees review fairness: authors submit this file separately, keeping `main.tex` completely blinded.

### 5.6 Anonymous Code Packager (`scifi/submission/code_packager.py`)
- Archives target code repository into `anonymous_code.zip`.
- **Directory Resolution**:
  - Accepts `--code-dir` (default: checks `scifi.toml`, then auto-detects `code/`, `src/`, or repository root while excluding manuscript files).
  - Optional: if `--no-code` is passed or no code directory exists (e.g. purely theoretical papers), code packaging is gracefully skipped (`code_zip_path = None`).
- **Exclusion Filters**:
  - Always excludes: `.git`, `.github`, `.gitattributes`, `.gitignore`.
  - Always excludes secrets & configs: `.env`, `*.key`, `*.pem`, `credentials.json`, `token*`.
  - Always excludes build caches: `__pycache__`, `*.pyc`, `.pytest_cache`, `.venv`, `venv`, `node_modules`, `dist/`.
  - Always excludes OS metadata: `.DS_Store`, `Thumbs.db`.
  - Excludes manuscript artifacts: `*.pdf`, `*.aux`, `*.synctex.gz`.
- **Content Sanitization & Audit**:
  - Scans and redacts absolute user paths (e.g. `C:\Users\username\...` or `/home/username/...` replaced with `<REPO_ROOT>/...`).
  - Strips standard file header author comments (`# Author: ...`).
  - Scans for unblinded git remote URLs (`github.com/username/...`).
  - Audits text files against the author list: flags detections as warnings and sets `audit_passed = False` if direct personal author leaks remain. Does NOT aggressively rewrite code variable names or keywords to prevent breaking runtime execution.
- **Turnkey Reproduction Template**:
  - If a reproduction script (`reproduce.py` or `run.sh`) is missing, scaffolds a clean template setting random seed configurations (e.g. seeds `[42, 1337, 2024]`).
  - Emits a sanitized `README.md` detailing dependencies, hardware requirements, and reproduction commands.

### 5.7 Submission Bundler (`scifi/submission/bundler.py`)
- Executes the generators in sequence, collecting outputs into a dedicated directory (default: `dist/submission/`).
- Supports theoretical / non-code submissions cleanly (`--no-code` or when no codebase is present).
- Writes a machine-readable `submission_manifest.json` detailing MD5 checksums, file paths, and venue checklist compliance.

---

## 6. CLI & FastMCP Tool Surface

### CLI Commands (`sf submission ...`)
- `sf submission letter [--target main.tex] [--journal "..."] [--venue elsevier|ieee|springer|acm|general] [--issn "..."] [--figure "..."] [--prior-doi "..."] [--output dist/cover_letter.md]`
- `sf submission highlights [--target main.tex] [--bullets "..."] [--venue elsevier|ieee|springer|acm|general] [--output dist/highlights.md]`
- `sf submission title-page [--target main.tex] [--venue elsevier|ieee|springer|acm|general] [--authors "..."] [--output dist/title_page.tex]`
- `sf submission pack-code [code_dir] [--output dist/anonymous_code.zip] [--authors "..."]`
- `sf submission bundle [--target main.tex] [--journal "..."] [--venue elsevier|ieee|springer|acm|general] [--code-dir "..."] [--no-code] [--output dist/submission/]`

### FastMCP Tools (`scifi/server.py`)
1. `scifi_generate_cover_letter`
2. `scifi_generate_highlights`
3. `scifi_generate_title_page`
4. `scifi_package_anonymous_code`
5. `scifi_prepare_submission_bundle`

### FastMCP Tools (`scifi/server.py`)
1. `scifi_generate_cover_letter`
2. `scifi_generate_highlights`
3. `scifi_generate_title_page`
4. `scifi_package_anonymous_code`
5. `scifi_prepare_submission_bundle`

---

## 7. Testing Strategy
- `tests/test_submission.py`:
  - Unit tests for cover letter generation (Markdown & LaTeX) with and without prior DOI / teaser figures.
  - Unit tests for highlights validation (verifies 85-char ceiling and truncation/recommendation).
  - Unit tests for title page generation (proper LaTeX formatting and author affiliation indexing).
  - Unit tests for code packager (proves `.git`, secrets, and author names are scrubbed from zip).
  - Unit tests for submission bundle (verifies all files created and manifest generated).
- `tests/test_cli.py`: CLI subcommands dispatch verification.
- `tests/test_server.py`: FastMCP tools response format verification.

---

## 8. What's Left to the Builder
- Selection of exact regex heuristics for extracting candidate contribution bullets from manuscript text if bullets are not passed explicitly.
- Default ISSN/journal template mappings for prominent publishers (Elsevier, IEEE, Springer, Nature, ACM).
