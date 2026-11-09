"""Tests for scifi.reproducibility conference checklist auditor (bacon/doctor)."""

from pathlib import Path
import pytest

from scifi.reproducibility.auditor import audit_reproducibility
from scifi.reproducibility.models import ReproducibilityCategory


def test_reproducibility_catches_missing_compute_and_seeds(tmp_path: Path):
    tex_content = r"""
    \documentclass{article}
    \begin{document}
    \section{Experiments}
    We train our neural network model on the CIFAR-10 dataset.
    Our model achieves 94.2% test accuracy outperforming the baseline.
    \end{document}
    """
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(tex_content, encoding="utf-8")

    result = audit_reproducibility(tex_path=tex_file, venue="neurips")
    assert result.status == "SUCCESS"
    assert result.checklist_items["seeds_specified"] is False
    assert result.checklist_items["compute_specified"] is False
    assert result.checklist_items["error_bars_specified"] is False
    assert result.score < 60
    assert len(result.issues) >= 3


def test_reproducibility_passes_complete_specifications(tmp_path: Path):
    tex_content = r"""
    \documentclass{article}
    \begin{document}
    \section{Experimental Setup}
    All experiments are averaged across 10 random seeds (seeds 0 through 9).
    We report the mean accuracy with $\pm$ standard deviation.
    Training is conducted using 4 NVIDIA A100 GPUs for a total of 120 GPU hours.
    The learning rate is tuned via grid search in $\{10^{-4}, 10^{-3}\}$ with batch size 64.
    Anonymized source code is available at \url{https://anonymous.4open.science/r/project-123}.
    \end{document}
    """
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(tex_content, encoding="utf-8")

    result = audit_reproducibility(tex_path=tex_file, venue="neurips", double_blind=True)
    assert result.status == "SUCCESS"
    assert result.checklist_items["seeds_specified"] is True
    assert result.checklist_items["compute_specified"] is True
    assert result.checklist_items["error_bars_specified"] is True
    assert result.checklist_items["hyperparameters_specified"] is True
    assert result.checklist_items["code_link_anonymized"] is True
    assert result.score >= 90
    assert len(result.issues) == 0


def test_reproducibility_flags_unblinded_github(tmp_path: Path):
    tex_content = r"""
    \documentclass{article}
    \begin{document}
    Source code is available at \url{https://github.com/johndoe/cool-repo}.
    \end{document}
    """
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(tex_content, encoding="utf-8")

    result = audit_reproducibility(tex_path=tex_file, double_blind=True)
    categories = [i.category for i in result.issues]
    assert ReproducibilityCategory.DOUBLE_BLIND_CODE in categories
