# SciFi Submission Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the SciFi Submission Suite providing four essential submission artifacts across Elsevier, IEEE, Springer, ACM, and double-blind conferences: editorial cover letters, research highlights with venue character validation, standalone unblinded title pages for review fairness, and reproducible anonymous code ZIP archives.

**Architecture:** 
- A dedicated domain package under `scifi/submission/` containing models, venue profiles, individual generators, code packager, and an all-in-one bundler.
- Zero mandatory external C-extensions: pure Python AST/regex parsing, zip packaging, and standard library data structures.
- Unified FastMCP tool registrations in `scifi/server.py` and CLI subcommands in `scifi/cli.py` under `sf submission <subcommand>`.

**Tech Stack:** Python >= 3.12, `pypdf`, `bibtexparser`, standard library (`zipfile`, `re`, `json`, `pathlib`, `dataclasses`).

**Spec:** [`docs/superpowers/specs/2026-11-09-submission-suite-design.md`](file:///C:/Users/Betagors/Code/scifi/docs/superpowers/specs/2026-11-09-submission-suite-design.md)

## Global Constraints

- Python >= 3.12 compatibility.
- Zero mandatory external API keys or heavy binary dependencies.
- Zero tolerance for synthetic AI clichés (*delve*, *pivotal*, *groundbreaking*, *testament*).
- Fast execution (< 1s per audit and zip packaging offline).
- Multi-file LaTeX compatibility via `scifi.latex.project.resolve_latex_project`.

## Review Focus

1. **Highlight character ceiling enforcement**: Elsevier strictly requires <= 85 characters including spaces per bullet; bullets exceeding this must be flagged with length and suggested truncations.
2. **Double-blind code leak protection**: `anonymous_code.zip` must never contain `.git/` histories, `.env` files, or local user paths (`C:\Users\...` or `/home/...`), and must fail the audit gate if author names appear unscrubbed in source text.
3. **Pure theoretical manuscripts**: Running `sf submission bundle` on a paper with no code or with `--no-code` must gracefully succeed with `code_zip_path = None` rather than failing.
4. **Multi-file LaTeX unblinded metadata extraction**: If `main.tex` splits authors/affiliations across subfiles, the metadata resolver must resolve the merged document tree.
5. **Publisher-specific clauses in cover letter**: IEEE must mandate the Prior Conference Extension section (>= 30% new material declaration) when a prior DOI is specified; Elsevier must require the declaration of competing interests and reviewer nominations.

---

### Task 1: Core Models & Publisher Profiles

**Files:**
- Create: `scifi/submission/__init__.py`
- Create: `scifi/submission/models.py`
- Create: `scifi/submission/profiles.py`
- Test: `tests/test_submission.py`

**Interfaces:**
- Produces:
  - `AuthorInfo(name: str, affiliation: str, email: str, orcid: str | None, is_corresponding: bool, credit_role: str | None)`
  - `PublisherProfile(venue_id: str, name: str, max_highlight_chars: int, max_highlights: int, require_credit_statement: bool, require_conference_extension_clause: bool)`
  - `get_publisher_profile(venue: str | None) -> PublisherProfile`

- [ ] **Step 1: Write failing test in `tests/test_submission.py` for profiles and models**

```python
import pytest
from scifi.submission.profiles import get_publisher_profile
from scifi.submission.models import AuthorInfo

def test_publisher_profiles():
    els = get_publisher_profile("elsevier")
    assert els.venue_id == "elsevier"
    assert els.max_highlight_chars == 85
    assert els.require_credit_statement is True

    ieee = get_publisher_profile("ieee")
    assert ieee.venue_id == "ieee"
    assert ieee.max_highlight_chars == 100
    assert ieee.require_conference_extension_clause is True

    gen = get_publisher_profile("unknown_venue")
    assert gen.venue_id == "general"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_submission.py::test_publisher_profiles -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.submission'`

- [ ] **Step 3: Implement `scifi/submission/models.py`, `profiles.py`, and `__init__.py`**
Implement dataclasses for authors, requests, and results, along with `get_publisher_profile(venue: str | None) -> PublisherProfile` covering `elsevier`, `ieee`, `springer`, `acm`, `openreview`, and `general`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_submission.py::test_publisher_profiles -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/submission/ tests/test_submission.py
git commit -m "feat(submission): add submission models and publisher profiles"
```

---

### Task 2: Research Highlights Generator & Validator

**Files:**
- Create: `scifi/submission/highlights.py`
- Modify: `scifi/submission/__init__.py`
- Test: `tests/test_submission.py`

**Interfaces:**
- Consumes: `PublisherProfile`, `HighlightItem`, `HighlightsResult` from Task 1.
- Produces:
  - `generate_highlights(bullets: list[str] | str, venue: str = "general", manuscript_path: str | Path | None = None) -> HighlightsResult`

- [ ] **Step 1: Write failing test in `tests/test_submission.py` for highlights**

```python
def test_highlights_validation_elsevier():
    from scifi.submission.highlights import generate_highlights
    
    # Under 85 chars
    bullets = [
        "Proposes a sub-quadratic attention mechanism for multi-modal transformers.",
        "Demonstrates 4.2x inference speedup across canonical GLUE and SQuAD benchmarks.",
        "Validates mathematical convergence bounds under mild Lipschitz assumptions.",
    ]
    res = generate_highlights(bullets, venue="elsevier")
    assert res.all_valid is True
    assert len(res.highlights) == 3
    assert "\\begin{itemize}" in res.latex_text

    # Over 85 chars for Elsevier
    long_bullets = [
        "This is an excessively long bullet point that provides way too much descriptive background information and easily exceeds the eighty-five character limit."
    ]
    res_invalid = generate_highlights(long_bullets, venue="elsevier")
    assert res_invalid.all_valid is False
    assert res_invalid.highlights[0].is_valid is False
    assert res_invalid.highlights[0].char_count > 85
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_submission.py::test_highlights_validation_elsevier -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.submission.highlights'`

- [ ] **Step 3: Implement `generate_highlights` in `scifi/submission/highlights.py`**
Implement bullet parsing, length calculation against `publisher_profile.max_highlight_chars`, active phrasing cleaner, and Markdown/LaTeX formatting.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_submission.py::test_highlights_validation_elsevier -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/submission/highlights.py tests/test_submission.py
git commit -m "feat(submission): add research highlights validator and generator"
```

---

### Task 3: Standalone Title Page Generator for Review Fairness

**Files:**
- Create: `scifi/submission/title_page.py`
- Modify: `scifi/submission/__init__.py`
- Test: `tests/test_submission.py`

**Interfaces:**
- Consumes: `AuthorInfo`, `TitlePageResult` from Task 1.
- Produces:
  - `generate_title_page(title: str, authors: list[AuthorInfo], venue: str = "general", abstract: str | None = None, funding: str | None = None, conflicts: str | None = None, data_availability: str | None = None, output_path: str | Path | None = None) -> TitlePageResult`

- [ ] **Step 1: Write failing test in `tests/test_submission.py` for title page**

```python
def test_title_page_generation():
    from scifi.submission.title_page import generate_title_page
    from scifi.submission.models import AuthorInfo
    
    authors = [
        AuthorInfo(
            name="Alice Smith",
            affiliation="Department of Computer Science, Stanford University",
            email="alice@stanford.edu",
            orcid="0000-0002-1825-0097",
            is_corresponding=True,
            credit_role="Conceptualization, Methodology, Software",
        ),
        AuthorInfo(
            name="Bob Jones",
            affiliation="Google DeepMind",
            email="bob@deepmind.com",
            orcid=None,
            is_corresponding=False,
            credit_role="Validation, Supervision",
        ),
    ]
    res = generate_title_page(
        title="Scalable Attention Architectures",
        authors=authors,
        venue="elsevier",
        funding="Supported by NSF Award #2041234.",
        conflicts="The authors declare no competing interests.",
    )
    assert res.status == "SUCCESS"
    assert "Alice Smith" in res.latex_text
    assert "Corresponding author: alice@stanford.edu" in res.markdown_text
    assert "CRediT authorship contribution statement" in res.latex_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_submission.py::test_title_page_generation -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.submission.title_page'`

- [ ] **Step 3: Implement `generate_title_page` in `scifi/submission/title_page.py`**
Implement standalone LaTeX and Markdown title page generation with indexed affiliations, corresponding author details, funding acknowledgments, and CRediT contributions for Elsevier.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_submission.py::test_title_page_generation -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/submission/title_page.py tests/test_submission.py
git commit -m "feat(submission): add unblinded title page generator for review fairness"
```

---

### Task 4: Editorial Cover Letter Generator

**Files:**
- Create: `scifi/submission/cover_letter.py`
- Modify: `scifi/submission/__init__.py`
- Test: `tests/test_submission.py`

**Interfaces:**
- Consumes: `AuthorInfo`, `PublisherProfile`, `CoverLetterResult` from Task 1.
- Produces:
  - `generate_cover_letter(manuscript_title: str, journal_name: str, venue: str = "general", editor_name: str | None = None, authors: list[AuthorInfo] | None = None, abstract: str | None = None, contributions: list[str] | None = None, figure_path: str | None = None, prior_doi: str | None = None, code_link: str | None = None, suggested_reviewers: list[dict[str, str]] | None = None, output_path: str | Path | None = None) -> CoverLetterResult`

- [ ] **Step 1: Write failing test in `tests/test_submission.py` for cover letter**

```python
def test_cover_letter_generation():
    from scifi.submission.cover_letter import generate_cover_letter
    from scifi.submission.models import AuthorInfo
    
    res = generate_cover_letter(
        manuscript_title="Robust Symbolic Derivations in Physics",
        journal_name="IEEE Transactions on Pattern Analysis and Machine Intelligence",
        venue="ieee",
        editor_name="Prof. David Forsyth",
        prior_doi="10.1109/CVPR.2024.12345",
        contributions=["Closed-form derivation guarantees", "Evaluated on 500 benchmarks"],
        suggested_reviewers=[{"name": "Dr. Clara Bell", "institution": "MIT", "email": "clara@mit.edu"}],
    )
    assert res.status == "SUCCESS"
    assert "Prof. David Forsyth" in res.markdown_text
    assert "Prior Publication & Significant Extension" in res.markdown_text
    assert "10.1109/CVPR.2024.12345" in res.markdown_text
    assert "Suggested Reviewers" in res.markdown_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_submission.py::test_cover_letter_generation -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.submission.cover_letter'`

- [ ] **Step 3: Implement `generate_cover_letter` in `scifi/submission/cover_letter.py`**
Implement the 5-beat academic cover letter generator supporting LaTeX letter class and Markdown formats, with IEEE conference extension statements, teaser figure callouts, and reviewer nominations.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_submission.py::test_cover_letter_generation -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/submission/cover_letter.py tests/test_submission.py
git commit -m "feat(submission): add editorial cover letter generator"
```

---

### Task 5: Reproducible Anonymous Code Packager

**Files:**
- Create: `scifi/submission/code_packager.py`
- Modify: `scifi/submission/__init__.py`
- Test: `tests/test_submission.py`

**Interfaces:**
- Consumes: `CodePackagerResult` from Task 1.
- Produces:
  - `package_anonymous_code(code_dir: str | Path, output_zip_path: str | Path | None = None, author_names: list[str] | None = None, seeds: list[int] | None = None) -> CodePackagerResult`

- [ ] **Step 1: Write failing test in `tests/test_submission.py` for code packager**

```python
import zipfile
import tempfile
from pathlib import Path

def test_anonymous_code_packager(tmp_path):
    from scifi.submission.code_packager import package_anonymous_code
    
    src = tmp_path / "code_src"
    src.mkdir()
    (src / ".git").mkdir()
    (src / ".git" / "config").write_text("user = Alice Smith", encoding="utf-8")
    (src / ".env").write_text("SECRET_KEY=12345", encoding="utf-8")
    (src / "main.py").write_text("# Author: Alice Smith\nprint('hello')", encoding="utf-8")
    (src / "data.txt").write_text("path = C:\\Users\\Alice\\data.csv", encoding="utf-8")
    
    out_zip = tmp_path / "anonymous_code.zip"
    res = package_anonymous_code(code_dir=src, output_zip_path=out_zip, author_names=["Alice Smith"])
    
    assert res.status == "SUCCESS"
    assert res.audit_passed is True
    assert out_zip.exists()
    
    with zipfile.ZipFile(out_zip, "r") as zf:
        namelist = zf.namelist()
        assert not any(".git" in n for n in namelist)
        assert not any(".env" in n for n in namelist)
        assert "main.py" in namelist
        assert "README.md" in namelist
        # Verify content sanitization
        main_content = zf.read("main.py").decode("utf-8")
        assert "Alice Smith" not in main_content
        data_content = zf.read("data.txt").decode("utf-8")
        assert "C:\\Users\\Alice" not in data_content
        assert "<REPO_ROOT>" in data_content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_submission.py::test_anonymous_code_packager -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.submission.code_packager'`

- [ ] **Step 3: Implement `package_anonymous_code` in `scifi/submission/code_packager.py`**
Implement exclusion filtering, path redaction, file-header author comment stripping, seed-configured reproduction script and `README.md` scaffolding, and `.zip` creation.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_submission.py::test_anonymous_code_packager -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/submission/code_packager.py tests/test_submission.py
git commit -m "feat(submission): add reproducible anonymous code packager"
```

---

### Task 6: Unified Submission Bundler

**Files:**
- Create: `scifi/submission/bundler.py`
- Modify: `scifi/submission/__init__.py`
- Test: `tests/test_submission.py`

**Interfaces:**
- Consumes: Functions from Tasks 1-5.
- Produces:
  - `prepare_submission_bundle(target_dir_or_tex: str | Path, journal_name: str | None = None, venue: str = "general", code_dir: str | Path | None = None, no_code: bool = False, output_dir: str | Path | None = None) -> SubmissionBundleResult`

- [ ] **Step 1: Write failing test in `tests/test_submission.py` for bundler**

```python
def test_submission_bundler(tmp_path):
    from scifi.submission.bundler import prepare_submission_bundle
    
    tex_file = tmp_path / "main.tex"
    tex_file.write_text(r"""
    \documentclass{article}
    \title{Deep Kernel Learning for Dynamics}
    \author{John Doe \and Jane Doe}
    \begin{abstract}This paper proposes deep kernels.\end{abstract}
    \begin{document}
    \maketitle
    \end{document}
    """, encoding="utf-8")
    
    out_dir = tmp_path / "dist" / "submission"
    res = prepare_submission_bundle(
        target_dir_or_tex=tex_file,
        journal_name="Elsevier Pattern Recognition",
        venue="elsevier",
        no_code=True,
        output_dir=out_dir,
    )
    assert res.status == "SUCCESS"
    assert (out_dir / "cover_letter.md").exists()
    assert (out_dir / "highlights.md").exists()
    assert (out_dir / "title_page.tex").exists()
    assert (out_dir / "submission_manifest.json").exists()
    assert res.code_zip_path is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_submission.py::test_submission_bundler -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scifi.submission.bundler'`

- [ ] **Step 3: Implement `prepare_submission_bundle` in `scifi/submission/bundler.py`**
Combine metadata resolution, run all 4 generators, save files to `dist/submission/`, and produce `submission_manifest.json`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_submission.py::test_submission_bundler -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/submission/bundler.py tests/test_submission.py
git commit -m "feat(submission): add all-in-one submission bundler"
```

---

### Task 7: CLI Subcommands & FastMCP Tool Registrations

**Files:**
- Modify: `scifi/cli.py`
- Modify: `scifi/server.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_server.py`

**Interfaces:**
- CLI Commands:
  - `sf submission letter`
  - `sf submission highlights`
  - `sf submission title-page`
  - `sf submission pack-code`
  - `sf submission bundle`
- MCP Tools:
  - `scifi_generate_cover_letter`
  - `scifi_generate_highlights`
  - `scifi_generate_title_page`
  - `scifi_package_anonymous_code`
  - `scifi_prepare_submission_bundle`

- [ ] **Step 1: Write failing tests in `tests/test_cli.py` and `tests/test_server.py`**

Test invoking `scifi submission letter --help`, `scifi submission bundle --help`, and invoking MCP tools in `test_server.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k submission -v`  
Expected: FAIL with unrecognized arguments/command.

- [ ] **Step 3: Wire CLI handlers into `scifi/cli.py` and MCP tools into `scifi/server.py`**

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py tests/test_server.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/cli.py scifi/server.py tests/test_cli.py tests/test_server.py
git commit -m "feat(submission): wire submission suite into CLI and FastMCP server"
```

---

### Task 8: Skills, Rules & End-to-End Verification

**Files:**
- Create: `skills/submission/SKILL.md`
- Modify: `rules/AGENTS.md` and `AGENTS.md`
- Modify: `README.md`

- [ ] **Step 1: Create `skills/submission/SKILL.md` documenting usage and parameters**
- [ ] **Step 2: Update `rules/AGENTS.md` and `AGENTS.md` to reference the submission suite rules**
- [ ] **Step 3: Update `README.md` with CLI examples for `sf submission`**
- [ ] **Step 4: Run full `uv run pytest` to ensure 100% test pass rate across the entire suite**
- [ ] **Step 5: Commit**

```bash
git add skills/submission/ rules/AGENTS.md AGENTS.md README.md
git commit -m "docs(submission): add submission skill, rules, and documentation"
```
