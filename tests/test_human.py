"""
Unit tests for the SciFi Master Academic Humanizer & LaTeX Forensic Stylometry Engine (scifi.human).
"""

from __future__ import annotations

from pathlib import Path

from scifi.human import (
    audit_human_prose,
    evaluate_list_fingerprints,
    evaluate_macro_abstraction,
    evaluate_math_syntax_quirks,
    evaluate_preamble_fingerprint,
    evaluate_stylometric_profile,
    evaluate_tabular_fingerprint,
)
from scifi.server import scifi_audit_human


SYNTHETIC_LATEX_SAMPLE = r"""
\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{microtype}
\usepackage{geometry}
\geometry{margin=1in}
\usepackage{hyperref}
\hypersetup{
    colorlinks=true,
    linkcolor=blue,
    citecolor=blue,
    urlcolor=blue
}
\begin{document}
\section{Introduction}
In the ever-evolving landscape of machine learning, this groundbreaking framework delves into intricate optimization dynamics — serving as a testament to pivotal algorithmic design. It is crucial to note that our architecture underscores seamless scalability across distributed nodes.

\begin{itemize}
    \item \textbf{Computational Scalability}: The proposed architecture processes large datasets with minimal computational overhead across nodes.
    \item \textbf{Gradient Regularization}: The loss formulation ensures stable parameter updates under extreme perturbation regimes.
    \item \textbf{Empirical Verification}: Comprehensive benchmarking across three tasks indicates marked improvements over baselines.
\end{itemize}

Let the input space be $\mathbb{R}^{d}$, the latent space be $\mathbb{R}^{k}$, the parameter space be $\mathbb{R}^{p}$, the weight matrix be $\mathbf{W} \in \mathbb{R}^{d \times k}$, the loss be $\mathcal{L}_{loss}$, the regularizer be $\mathcal{L}_{reg}$, the training set be $\mathcal{D}_{train}$, and the distribution be $\mathcal{N}(0, \mathbf{I})$. For the $i$-th iteration, we evaluate $(x, y, z.)$ Moreover, the objective satisfies:
\begin{equation}
    \mathcal{J}(\theta) = \int P(\tau; \theta) R(\tau) d\tau + \gamma \|\theta\|_2^2 \quad \text{where } \gamma > 0 \text{ is the regularization weight.}
\end{equation}

\begin{table}[htbp]
\centering
\begin{tabular}{lcccc}
\toprule
Architecture & Acc & Prec & Rec & F1 \\
\midrule
ResNet-50 & 84.1 & 0.83 & 0.82 & 0.82 \\
\bottomrule
\end{tabular}
\end{table}

\subsection{Optimization Dynamics}
The model updates parameters at every step using gradient steps on the loss manifold.
In summary, this subsection demonstrated how the optimization dynamics converge rapidly.
\end{document}
"""


AUTHENTIC_HUMAN_LATEX_SAMPLE = r"""
\documentclass[journal,twocolumn,10pt]{IEEEtran}
\usepackage{amsmath,amssymb}
\usepackage{xcolor}
\definecolor{darknavy}{rgb}{0.0, 0.1, 0.4}
\usepackage[colorlinks=true,allcolors=darknavy,pdfborder={0 0 0}]{hyperref}
\newcommand{\R}{\mathbb{R}}
\newcommand{\E}{\mathbb{E}}
\newcommand{\D}{\mathcal{D}}
\DeclareMathOperator*{\argmax}{arg\,max}

\begin{document}
\section{Introduction}
Channel estimation error degrades spatial multiplexing gains in millimeter-wave arrays. Although pilot contamination has been analyzed extensively under static block-fading assumptions, rapid vehicular mobility introduces non-stationary Doppler spreads that invalidate time-invariant covariance priors, particularly when the coherence interval falls below the number of transmit antennas.

\begin{itemize}
    \item Robustness under heavy tail interference ($\alpha < 1.5$).
    \item Runtime latency: an average reduction from 4.2 hours to approximately 75 minutes was recorded across an 8-GPU cluster during training.
    \item Minimal sensitivity to step-size initialization, as confirmed by the perturbation bounds in Appendix A across 12 synthetic topologies and 3 hardware testbeds.
\end{itemize}

Let the input manifold be denoted by $\R^d$ and the latent projection by $\R^k$. For the $i$th iteration ($i \in \{1, \dots, N\}$), the empirical risk $W_{\mathrm{loss}}$ over $\D$ is minimized via
\begin{equation}
    \min_{\theta \in \R^p} \E_{\tau \sim \D} \!\left[ \int \! P(\tau; \theta) R(\tau)\, d\tau \right], \label{eq:obj}
\end{equation}
where $\theta$ denotes the transceiver parameter vector.

\begin{table}[t]
\centering
\setlength{\tabcolsep}{3.5pt}
\begin{tabular*}{\columnwidth}{@{\extracolsep{\fill}} l r r r r @{}}
\hline
Configuration & Top-1 & Top-5 & Param. & Latency \\
\hline
Full Pipeline & 82.4 & 95.1 & 28.2 & 14.1 \\
\hline
\end{tabular*}
\end{table}
\end{document}
"""


def test_list_fingerprint_detection():
    syn_metrics, syn_flags = evaluate_list_fingerprints(SYNTHETIC_LATEX_SAMPLE)
    assert syn_metrics["total_lists"] == 1
    assert syn_metrics["anomalous_lists_count"] == 1
    blk = syn_metrics["anomalous_lists"][0]
    assert blk["bold_ratio"] == 1.0
    assert blk["length_cv"] < 0.15
    assert blk["is_cardinality_3_or_5"] is True
    assert len(syn_flags) == 1

    hum_metrics, hum_flags = evaluate_list_fingerprints(AUTHENTIC_HUMAN_LATEX_SAMPLE)
    assert hum_metrics["total_lists"] == 1
    assert hum_metrics["anomalous_lists_count"] == 0
    assert hum_metrics["all_lists"][0]["length_cv"] > 0.35
    assert len(hum_flags) == 0


def test_preamble_and_tabular_fingerprints():
    pre_syn, pre_flags = evaluate_preamble_fingerprint(SYNTHETIC_LATEX_SAMPLE)
    assert pre_syn["has_preamble"] is True
    assert len(pre_syn["kitchen_sink_overlap"]) == 8
    assert "graphicx" in pre_syn["unused_packages"]
    assert pre_syn["stereotypical_hyperref"] is True
    assert len(pre_flags) >= 2

    tab_syn, tab_flags = evaluate_tabular_fingerprint(SYNTHETIC_LATEX_SAMPLE)
    assert tab_syn["total_tables"] == 1
    assert tab_syn["rigid_tables_count"] == 1
    assert len(tab_flags) == 1

    pre_hum, _ = evaluate_preamble_fingerprint(AUTHENTIC_HUMAN_LATEX_SAMPLE)
    assert pre_hum["unused_packages"] == []
    assert pre_hum["stereotypical_hyperref"] is False

    tab_hum, _ = evaluate_tabular_fingerprint(AUTHENTIC_HUMAN_LATEX_SAMPLE)
    assert tab_hum["rigid_tables_count"] == 0


def test_macro_abstraction_and_math_syntax():
    mac_syn, mac_flags = evaluate_macro_abstraction(SYNTHETIC_LATEX_SAMPLE)
    assert mac_syn["custom_macro_count"] == 0
    assert mac_syn["canonical_expansion_count"] >= 8
    assert mac_syn["macro_abstraction_ratio"] == 0.0
    assert len(mac_flags) == 1

    mth_syn, mth_flags = evaluate_math_syntax_quirks(SYNTHETIC_LATEX_SAMPLE)
    assert mth_syn["in_math_commentary_count"] >= 1
    assert mth_syn["rho_math_text"] >= 1.0
    assert mth_syn["inline_kth_count"] >= 1
    assert mth_syn["trapped_punctuation_count"] >= 1
    assert mth_syn["unscoped_subscript_count"] >= 3
    assert mth_syn["unspaced_integral_differentials"] >= 1
    assert len(mth_flags) >= 4

    mac_hum, _ = evaluate_macro_abstraction(AUTHENTIC_HUMAN_LATEX_SAMPLE)
    assert mac_hum["custom_macro_count"] >= 4
    assert mac_hum["macro_abstraction_ratio"] >= 1.0

    mth_hum, mth_hum_flags = evaluate_math_syntax_quirks(AUTHENTIC_HUMAN_LATEX_SAMPLE)
    assert mth_hum["in_math_commentary_count"] == 0
    assert mth_hum["trapped_punctuation_count"] == 0
    assert mth_hum["unscoped_subscript_count"] == 0
    assert len(mth_hum_flags) == 0


def test_stylometric_profile_and_full_audit(tmp_path: Path):
    sty_syn, _ = evaluate_stylometric_profile(SYNTHETIC_LATEX_SAMPLE)
    assert sty_syn["excess_style_word_count"] >= 6
    assert sty_syn["em_dash_count"] >= 1
    assert sty_syn["pre_equation_scaffolding_count"] >= 1
    assert sty_syn["redundant_subsection_summaries"] == 1

    # End-to-end audit on synthetic vs authentic human files
    syn_file = tmp_path / "synthetic.tex"
    syn_file.write_text(SYNTHETIC_LATEX_SAMPLE, encoding="utf-8")
    report_out = tmp_path / "human_report.md"

    res_syn = audit_human_prose(syn_file, output_report=report_out)
    assert res_syn["status"] == "SUCCESS"
    assert res_syn["human_score"] < 50
    assert res_syn["classification"] == "STRONG_SYNTHETIC_SIGNATURE"
    assert report_out.is_file()
    assert "SciFi Humanizer & LaTeX Stylometric Forensic Report" in res_syn["report_markdown"]

    hum_file = tmp_path / "human.tex"
    hum_file.write_text(AUTHENTIC_HUMAN_LATEX_SAMPLE, encoding="utf-8")
    res_hum = scifi_audit_human(str(hum_file))
    assert res_hum["status"] == "SUCCESS"
    assert res_hum["human_score"] >= 85
    assert res_hum["classification"] == "AUTHENTIC_HUMAN_BASELINE"


def test_cli_and_skill_script_execution(tmp_path: Path):
    import scifi.cli
    from skills.human.scripts.audit_human import main as script_main

    hum_file = tmp_path / "clean_paper.tex"
    hum_file.write_text(AUTHENTIC_HUMAN_LATEX_SAMPLE, encoding="utf-8")

    assert scifi.cli.main(["human", str(hum_file)]) == 0
    assert scifi.cli.main(["human", str(hum_file), "--json"]) == 0
    assert script_main([str(hum_file), "--json"]) == 0
