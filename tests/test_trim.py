"""Tests for scifi.layout page budget and trimming assistant (scribe/layout)."""

from pathlib import Path

from scifi.layout.abbreviations import abbreviate_bib_string, abbreviate_venue
from scifi.layout.models import TrimSuggestionType
from scifi.layout.trim import audit_trim_budget, detect_paragraph_slack


def test_abbreviate_venue_known_venues():
    assert abbreviate_venue("Advances in Neural Information Processing Systems") == "Proc. NeurIPS"
    assert (
        abbreviate_venue("Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition")
        == "Proc. IEEE/CVF CVPR"
    )
    assert (
        abbreviate_venue("IEEE Transactions on Pattern Analysis and Machine Intelligence")
        == "IEEE Trans. Pattern Anal. Mach. Intell."
    )
    assert abbreviate_venue("International Conference on Machine Learning") == "Proc. ICML"
    assert abbreviate_venue("Random Obscure Workshop on AI") == "Random Obscure Workshop on AI"  # Unchanged fallback


def test_abbreviate_bib_string():
    bib_input = """
    @inproceedings{vaswani2017attention,
      author = {Vaswani, Ashish and others},
      title = {Attention Is All You Need},
      booktitle = {Advances in Neural Information Processing Systems},
      year = {2017}
    }
    """
    condensed_bib, count = abbreviate_bib_string(bib_input)
    assert count == 1
    assert "Proc. NeurIPS" in condensed_bib


def test_detect_paragraph_slack():
    # Multi-line paragraph ending in a single-word orphan line: "convergence."
    para = (
        "We evaluate our proposed optimization framework across several benchmark networks and distributed clusters.\n"
        "Under high variance and packet loss, our algorithm maintains stable consensus and achieves rapid\n"
        "convergence."
    )
    suggestions = detect_paragraph_slack(para)
    assert len(suggestions) == 1
    assert suggestions[0].suggestion_type == TrimSuggestionType.WIDOW_LINE
    assert "convergence." in suggestions[0].target
    assert suggestions[0].potential_savings_lines == 1


def test_audit_trim_budget_full(tmp_path: Path):
    tex_file = tmp_path / "paper.tex"
    bib_file = tmp_path / "refs.bib"

    tex_content = r"""
    \documentclass{article}
    \begin{document}
    We evaluate our proposed optimization framework across several benchmark networks and distributed clusters.
    Under high variance and packet loss, our algorithm maintains stable consensus and achieves rapid
    convergence.

    \begin{table}[h]
    \centering
    \begin{tabular}{cc}
    A & B \\
    1 & 2 \\
    \end{tabular}
    \caption{Experimental results}
    \end{table}

    \end{document}
    """
    bib_content = """
    @inproceedings{doe2023,
      author = {Doe, Jane},
      title = {Great Title},
      booktitle = {International Conference on Machine Learning},
      year = {2023}
    }
    """
    tex_file.write_text(tex_content, encoding="utf-8")
    bib_file.write_text(bib_content, encoding="utf-8")

    result = audit_trim_budget(tex_path=tex_file, bib_path=bib_file)
    assert result.status == "SUCCESS"
    assert result.total_potential_lines_saved >= 2
    assert result.bibtex_condensed_entries == 1
