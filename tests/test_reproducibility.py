"""Tests for scifi.reproducibility conference checklist auditor (bacon/doctor)."""

from pathlib import Path

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


def test_ml_systems_standard_passes_and_catches_missing_items(tmp_path: Path):
    complete = tmp_path / "systems_ok.tex"
    complete.write_text(
        r"""
        \section{Experimental Setup}
        Evaluated across 5 random seeds (seeds 0--4), reporting mean and $\pm$ std.
        Training used 2 NVIDIA A100 GPUs (24 GPU hours) with Adam optimizer, learning rate $10^{-4}$, and batch size 64.
        Simulation parameters span a horizon $T = 200$ time-slots with discount factor $\gamma = 0.99$.
        The solver convergence tolerance is $10^{-6}$ over 500 evaluation rollouts.
        Anonymized code is at \url{https://anonymous.4open.science/r/sys-123}.
        """,
        encoding="utf-8",
    )
    res_ok = audit_reproducibility(complete, standard="ml-systems", double_blind=True)
    assert res_ok.standard == "ml-systems"
    assert res_ok.checklist_items["system_parameters_specified"] is True
    assert res_ok.checklist_items["solver_or_tolerance_specified"] is True
    assert res_ok.score == 100
    assert res_ok.issues == []

    incomplete = tmp_path / "systems_bad.tex"
    incomplete.write_text(
        r"""
        \section{Experiments}
        Evaluated across 5 random seeds with $\pm$ standard deviation on an NVIDIA A100 GPU
        using Adam optimizer and learning rate $10^{-4}$.
        """,
        encoding="utf-8",
    )
    res_bad = audit_reproducibility(incomplete, venue="ieee")
    assert res_bad.standard == "ml-systems"
    assert res_bad.checklist_items["system_parameters_specified"] is False
    assert res_bad.checklist_items["solver_or_tolerance_specified"] is False
    assert res_bad.score < 100

    res_elsevier = audit_reproducibility(complete, venue="elsevier")
    assert res_elsevier.standard == "ml-systems"


def test_statistical_pitfalls_detection_and_suppression(tmp_path: Path):
    # Multiple testing without correction
    mt = tmp_path / "mt.tex"
    mt.write_text(
        "Gene A (p < 0.01), Gene B (p = 0.03), and Gene C (p < 0.04) were significant.",
        encoding="utf-8",
    )
    mt_cats = [i.category for i in audit_reproducibility(mt).issues]
    assert ReproducibilityCategory.MULTIPLE_TESTING in mt_cats

    mt_ok = tmp_path / "mt_ok.tex"
    mt_ok.write_text(
        "Gene A (p < 0.01), Gene B (p = 0.03), Gene C (p < 0.04) after Benjamini-Hochberg FDR.",
        encoding="utf-8",
    )
    mt_ok_cats = [i.category for i in audit_reproducibility(mt_ok).issues]
    assert ReproducibilityCategory.MULTIPLE_TESTING not in mt_ok_cats

    # Data leakage
    leak = tmp_path / "leak.tex"
    leak.write_text(
        "We applied StandardScaler normalization and PCA before the train-test split.",
        encoding="utf-8",
    )
    leak_cats = [i.category for i in audit_reproducibility(leak).issues]
    assert ReproducibilityCategory.DATA_LEAKAGE in leak_cats

    # Nested-variance pseudoreplication: many rollouts from 1 training seed without separating variance
    pseudo = tmp_path / "pseudo.tex"
    pseudo.write_text(
        "We evaluate N = 200 rollout episodes from 1 random seed and report a t-test.",
        encoding="utf-8",
    )
    pseudo_cats = [i.category for i in audit_reproducibility(pseudo).issues]
    assert ReproducibilityCategory.PSEUDOREPLICATION in pseudo_cats

    pseudo_ok = tmp_path / "pseudo_ok.tex"
    pseudo_ok.write_text(
        "We evaluate N = 200 rollout episodes from 1 random seed using mixed-effects separation of N_train and N_eval variance.",
        encoding="utf-8",
    )
    pseudo_ok_cats = [i.category for i in audit_reproducibility(pseudo_ok).issues]
    assert ReproducibilityCategory.PSEUDOREPLICATION not in pseudo_ok_cats


def test_cli_repro_with_standard_flag(tmp_path: Path, capsys) -> None:
    import json

    import scifi.cli

    tex = tmp_path / "sys.tex"
    tex.write_text(r"\section{Experiments} Simulation parameters with time-slot horizon T.", encoding="utf-8")
    code = scifi.cli.main(["repro", str(tex), "--standard", "ml-systems", "--json"])
    assert code in (0, 1)
    payload = json.loads(capsys.readouterr().out)
    assert payload["standard"] == "ml-systems"
    assert "system_parameters_specified" in payload["checklist_items"]
    assert "solver_or_tolerance_specified" in payload["checklist_items"]
