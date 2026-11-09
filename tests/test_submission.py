"""Tests for the SciFi Academic Submission Suite."""

from __future__ import annotations

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
    assert "CRediT Authorship Contribution Statement" in res.latex_text


def test_cover_letter_generation():
    from scifi.submission.cover_letter import generate_cover_letter

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


def test_anonymous_code_packager(tmp_path):
    import zipfile
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




