"""Unit tests for the SciFi manuscript abbreviation & acronym hygiene auditor (scifi.abbreviations)."""

from __future__ import annotations

from scifi.abbreviations import evaluate_abbreviation_hygiene
from scifi.orwell import audit_orwell_prose

CLEAN_MANUSCRIPT = r"""
\documentclass{IEEEtran}
\begin{document}
\begin{abstract}
We optimize Unmanned Aerial Vehicle (UAV) trajectory planning in Mobile Edge Computing (MEC) networks using Multi-Agent Proximal Policy Optimization (MAPPO). Extensive simulations confirm that UAV-assisted MEC improves throughput under Line of Sight (LoS) links.
\end{abstract}

\section{Introduction}
An Unmanned Aerial Vehicle (UAV) can act as an aerial relay for Mobile Edge Computing (MEC) workloads. We train decentralized actors via Multi-Agent Proximal Policy Optimization (MAPPO). Under Line of Sight (LoS) propagation, the UAV schedules tasks to the MEC server. Furthermore, MAPPO stabilizes policy updates when LoS conditions fluctuate across UAV trajectories.
\end{document}
"""


def test_clean_manuscript_has_zero_abbreviation_issues():
    metrics, flags = evaluate_abbreviation_hygiene(CLEAN_MANUSCRIPT)
    assert metrics["issue_count"] == 0
    assert flags == []
    assert metrics["undefined_in_abstract"] == []
    assert metrics["undefined_in_body"] == []
    assert metrics["low_use_abbreviations"] == []
    assert metrics["invented_algorithm_acronyms"] == []
    assert metrics["compound_algorithm_variants"] == []
    assert metrics["overloaded_sentences_count"] == 0


def test_invented_and_compound_algorithm_names_flagged():
    tex = r"""
\begin{document}
\section{Methodology}
We propose Lya-BiMAPPO for constrained control. In our ablation study, we compare against Penalty-BiMAPPO, Safe-Pure-MAPPO, Pure-MAPPO, Lya-BiMAPPO-MaxSNR, and Lya-BiMAPPO-EqualCPU.
\end{document}
"""
    metrics, flags = evaluate_abbreviation_hygiene(tex)
    assert "Lya-BiMAPPO" in metrics["invented_algorithm_acronyms"]
    for variant in (
        "Penalty-BiMAPPO",
        "Safe-Pure-MAPPO",
        "Pure-MAPPO",
        "Lya-BiMAPPO-MaxSNR",
        "Lya-BiMAPPO-EqualCPU",
    ):
        assert variant in metrics["compound_algorithm_variants"]
    assert any("Simplify 'Lya-BiMAPPO'" in f["remedy"] for f in flags)
    assert any("descriptive experimental label" in f["remedy"] for f in flags)


def test_first_occurrence_abstract_and_body_audit():
    tex = r"""
\begin{document}
\begin{abstract}
We use MAPPO for Unmanned Aerial Vehicle (UAV) control.
\end{abstract}
\section{Introduction}
The UAV executes MAPPO policies. Later we define Multi-Agent Proximal Policy Optimization (MAPPO) and Control Barrier Function (CBF).
\end{document}
"""
    metrics, flags = evaluate_abbreviation_hygiene(tex)
    # MAPPO is undefined in abstract; UAV is defined in abstract but not re-defined in body
    assert "MAPPO" in metrics["undefined_in_abstract"]
    assert "UAV" in metrics["undefined_in_body"]
    # MAPPO is used in body before its definition in body
    assert any(
        "used in the main text before its definition" in f["explanation"] and f["matched_text"] == "MAPPO"
        for f in flags
    )


def test_low_use_one_time_abbreviations_flagged():
    tex = r"""
\begin{document}
\section{Analysis}
We derive the Physical Energy Lower Bound (PELB) and the Capped-Service Drift Deficit (CSDD).
We also evaluate the Signal-to-Noise Ratio (SNR) across three topologies, where SNR remains above 10 dB and SNR scales linearly.
\end{document}
"""
    metrics, flags = evaluate_abbreviation_hygiene(tex)
    assert "PELB" in metrics["low_use_abbreviations"]
    assert "CSDD" in metrics["low_use_abbreviations"]
    assert "SNR" not in metrics["low_use_abbreviations"]
    assert any("PELB" in f["matched_text"] and "1 time(s)" in f["explanation"] for f in flags)


def test_abbreviation_overload_in_single_sentence():
    tex = r"""
\begin{document}
\section{Architecture}
The CTDE architecture employs MAPPO with GAE and BC warm-starting, while the CBF-QCQP safety filter uses SLSQP.
\end{document}
"""
    metrics, flags = evaluate_abbreviation_hygiene(tex)
    assert metrics["overloaded_sentences_count"] == 1
    assert any("stacks" in f["explanation"] and "CTDE" in f["explanation"] for f in flags)


def test_orwell_integration_includes_abbreviations_dimension():
    tex = r"""
\begin{document}
\section{Method}
We propose Lya-BiMAPPO and compare it with Safe-Pure-MAPPO.
The CTDE architecture employs MAPPO with GAE and BC warm-starting, while the CBF-QCQP safety filter uses SLSQP.
\end{document}
"""
    res = audit_orwell_prose(tex)
    assert res["status"] == "SUCCESS"
    assert "abbreviations" in res["dimensions"]
    abr = res["dimensions"]["abbreviations"]
    assert abr["issue_count"] >= 3
    assert "8. Abbreviation Hygiene" in res["report_markdown"]
    assert any("Abbreviation hygiene issues" in d for d in res["deductions"])


def test_figure_label_consistency_flags_awkward_names_in_svg_tikz_and_caption(tmp_path):
    from scifi.figures.auditor import audit_latex_figures
    from scifi.figures.models import FigureIssueCategory

    svg_path = tmp_path / "convergence.svg"
    svg_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><text>Lya-BiMAPPO</text><text>Safe-Pure-MAPPO</text></svg>',
        encoding="utf-8",
    )

    tex_path = tmp_path / "paper.tex"
    tex_path.write_text(
        r"""
\documentclass{article}
\usepackage{graphicx}
\begin{document}
\begin{figure}
\includegraphics{convergence.svg}
\caption{Reward comparison of Lya-BiMAPPO-MaxSNR across episodes.}
\label{fig:reward}
\end{figure}
\begin{tikzpicture}
\node {Penalty-BiMAPPO};
\end{tikzpicture}
\end{document}
""",
        encoding="utf-8",
    )

    res = audit_latex_figures(tex_path, base_dir=tmp_path, render_previews=False)
    label_issues = [i for i in res.issues if i.category == FigureIssueCategory.LABEL_CONSISTENCY]
    messages = " ".join(i.message for i in label_issues)
    assert "Lya-BiMAPPO" in messages
    assert "Safe-Pure-MAPPO" in messages
    assert "Lya-BiMAPPO-MaxSNR" in messages
    assert "Penalty-BiMAPPO" in messages
