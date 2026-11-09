"""Tests for scifi.rebuttal author rebuttal and diff suite (socrates/rebuttal)."""

from pathlib import Path
import pytest

from scifi.rebuttal.differ import diff_manuscript
from scifi.rebuttal.formatter import format_rebuttal_scaffold


def test_format_rebuttal_scaffold_parses_reviewers():
    reviews_input = """
    Reviewer 1:
    The computational complexity of Algorithm 1 is unclear. What is the Big-O bound?
    Additionally, how sensitive is the model to learning rate variance?

    Reviewer 2:
    The baseline in Table 1 is outdated (2018). Please compare against SOTA (2023).
    """

    scaffold = format_rebuttal_scaffold(reviews_input, venue="openreview")
    assert scaffold.total_critiques_parsed >= 3
    assert "Reviewer 1" in scaffold.reviewers
    assert "Reviewer 2" in scaffold.reviewers
    assert "Action Taken" in scaffold.markdown_template
    assert "Empirical / Theoretical Evidence" in scaffold.markdown_template
    # Anti-sycophancy check: no excessive groveling in the template
    assert "magnificent" not in scaffold.markdown_template.lower()


def test_diff_manuscript_tracks_section_changes(tmp_path: Path):
    old_tex = tmp_path / "old.tex"
    new_tex = tmp_path / "new.tex"

    old_content = r"""
    \section{Introduction}
    Federated learning enables edge computing without sharing raw data.
    Our convergence rate is O(1/T).
    """

    new_content = r"""
    \section{Introduction}
    Federated learning enables edge computing without sharing raw data across heterogeneous nodes.
    Our convergence rate is O(1/\sqrt{T}), achieving optimal minimax rates.
    \section{Computational Complexity}
    The per-iteration runtime scales linearly with N.
    """

    old_tex.write_text(old_content, encoding="utf-8")
    new_tex.write_text(new_content, encoding="utf-8")

    diff_res = diff_manuscript(old_tex_path=old_tex, new_tex_path=new_tex)
    assert diff_res.status == "SUCCESS"
    assert diff_res.added_lines > 0
    assert len(diff_res.modified_sections) >= 1
    assert "Introduction" in [s["section"] for s in diff_res.modified_sections]
    assert len(diff_res.diff_ledger_markdown) > 0
