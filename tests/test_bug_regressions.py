"""
Regression tests for latent runtime bugs uncovered during static analysis audit.
"""

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

from scifi.cli import cmd_math, cmd_stats
from scifi.doctor import audit_manuscript
from scifi.literature.lineage import LineageCrawler
from scifi.literature.models import PaperRecord
from scifi.orwell import audit_orwell_prose
from scifi.rebuttal.differ import diff_manuscript


def test_doctor_calls_audit_bib_file_with_valid_keyword(tmp_path: Path):
    """Ensure doctor does not pass invalid 'search_missing_doi' to audit_bib_file."""
    tex_file = tmp_path / "main.tex"
    tex_file.write_text(
        r"\documentclass{article}\begin{document}\cite{Knuth1984}\bibliography{ref}\end{document}", encoding="utf-8"
    )
    bib_file = tmp_path / "ref.bib"
    bib_file.write_text("@article{Knuth1984, title={Literate Programming}, year={1984}}", encoding="utf-8")

    from scifi.citation_verifier.models import BibAuditReport

    mock_report = BibAuditReport(file_path=str(bib_file), total_entries=1, verified_count=1)

    with patch("scifi.doctor.audit_bib_file", return_value=mock_report) as mock_audit:
        res = audit_manuscript(tmp_path, live=True)
        assert mock_audit.called
        # Check call kwargs: must NOT contain 'search_missing_doi'
        _, kwargs = mock_audit.call_args
        assert "search_missing_doi" not in kwargs
        assert kwargs.get("search_missing") is True
        # Verify live bib reports is not empty
        alex_stage = res.get("stages", {}).get("alex_bibliography", {})
        assert len(alex_stage.get("live_audit", [])) == 1


def test_lineage_crawler_calls_extract_reported_results():
    """Ensure LineageCrawler calls BenchmarkExtractor.extract_reported_results, not extract_benchmarks."""
    store = MagicMock()
    crawler = LineageCrawler(store=store)
    paper = PaperRecord(
        id="test-p1",
        title="Deep Learning Benchmark",
        abstract="We achieve 98.5% accuracy on ImageNet.",
        year=2024,
    )
    with patch(
        "scifi.literature.benchmarks.BenchmarkExtractor.extract_reported_results", return_value=[MagicMock()]
    ) as mock_extractor:
        # Before fix, is_paper_accepted attempts to call extract_benchmarks which fails and falls back
        crawler.is_paper_accepted(paper, require_evidence=True)
        assert mock_extractor.called


def test_differ_handles_compile_latex_dict_result(tmp_path: Path):
    """Ensure differ accesses dictionary keys from compile_latex instead of attributes."""
    old_tex = tmp_path / "old.tex"
    new_tex = tmp_path / "new.tex"
    old_tex.write_text("Old content", encoding="utf-8")
    new_tex.write_text("New content", encoding="utf-8")

    fake_dict = {"status": "SUCCESS", "pdf_path": str(tmp_path / "diff.pdf")}
    with (
        patch("shutil.which", return_value="latexdiff"),
        patch("subprocess.run") as mock_run,
        patch("scifi.rebuttal.differ.compile_latex", return_value=fake_dict),
    ):
        mock_run.return_value = MagicMock(stdout=r"\documentclass{article}\begin{document}diff\end{document}")
        summary = diff_manuscript(old_tex, new_tex, generate_pdf=True)
        assert summary.diff_pdf_path == str(tmp_path / "diff.pdf")


def test_cli_math_units_and_limits_arg_dispatch():
    """Ensure cli.cmd_math dispatches check_mode and point/claimed properly."""
    with patch("scifi.math.check_units") as mock_units:
        mock_units.return_value = {"is_correct": True, "status": "VALID"}
        args_units = argparse.Namespace(
            math_command="units",
            expression="m/s",
            mode="add",
        )
        rc = cmd_math(args_units)
        assert rc == 0
        mock_units.assert_called_once_with("m/s", check_mode="add")

    with patch("scifi.math.check_limits") as mock_limits:
        mock_limits.return_value = {"is_correct": True, "status": "VALID"}
        args_limits = argparse.Namespace(
            math_command="limits",
            expression="1/x",
            variable="x",
            tends_to="0",
            expected="inf",
            direction="+",
        )
        rc = cmd_math(args_limits)
        assert rc == 0
        mock_limits.assert_called_once_with("1/x", "x", point="0", claimed="inf", direction="+")


def test_cli_stats_curve_arg_dispatch(tmp_path: Path):
    """Ensure cli.cmd_stats curve dispatches arguments matching verify_curve signature."""
    with patch("scifi.stats.verify_curve") as mock_curve:
        mock_curve.return_value = {"is_correct": True, "status": "VALID"}
        args_curve = argparse.Namespace(
            stats_command="curve",
            formula="y = 2*x",
            var_name="x",
            data_path=str(tmp_path / "data.csv"),
            x_col="x",
            y_col="y",
            tolerance=0.05,
        )
        rc = cmd_stats(args_curve)
        assert rc == 0
        mock_curve.assert_called_once_with(
            "y = 2*x",
            "x",
            sim_data_path=str(tmp_path / "data.csv"),
            x_col="x",
            y_col="y",
            rtol=0.05,
        )


def test_orwell_trapped_punctuation_checks_islower():
    """Ensure audit_orwell_prose does not use broken isLower check that treats symbols as word starts."""
    latex = r"""
    \documentclass{article}
    \begin{document}
    The value is $(x, y.)$ 123 followed by number.
    \end{document}
    """
    res = audit_orwell_prose(latex)
    flags = res.get("flags", [])
    trapped_flags = [
        f
        for f in flags
        if f.get("dimension") == "math_syntax" and "trapped inside inline math" in f.get("explanation", "")
    ]
    # Because '1' is not upper and not lower, it should not be treated as a clause transition
    assert len(trapped_flags) == 0
