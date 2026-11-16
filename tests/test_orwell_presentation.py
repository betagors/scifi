"""Tests for the 7th Orwell forensic dimension: presentation & reviewer red flags."""

from scifi.orwell import audit_orwell_prose
from scifi.orwell_presentation import evaluate_presentation_fingerprint


def test_compound_method_names_and_texttt():
    tex = r"""
    \begin{document}
    We propose \texttt{Lya-BiMAPPO} and compare against \texttt{Penalty-BiMAPPO},
    \texttt{Safe-Pure-MAPPO}, \texttt{Lya-BiMAPPO-MaxSNR}, and \texttt{Centralized-Oracle}.
    Karush--Kuhn--Tucker conditions and BCD-SCA are standard baselines.
    \end{document}
    """
    metrics, flags = evaluate_presentation_fingerprint(tex)
    assert metrics["naming"]["distinct_compound_names"] >= 4
    assert "Lya-BiMAPPO-MaxSNR" in metrics["naming"]["three_plus_segment_names"]
    assert metrics["naming"]["texttt_method_count"] >= 4
    assert any(f["dimension"] == "presentation_naming" and f["severity"] == "MEDIUM" for f in flags)
    assert any(f["dimension"] == "presentation_naming" and f["severity"] == "LOW" for f in flags)


def test_compound_names_clean_negative():
    tex = r"""
    \begin{document}
    We propose L-MAPPO and compare it against standard MAPPO, BCD-SCA, and a centralized oracle.
    The closed-form solution uses Karush--Kuhn--Tucker conditions under Gauss--Markov mobility.
    \end{document}
    """
    metrics, flags = evaluate_presentation_fingerprint(tex)
    assert metrics["naming"]["distinct_compound_names"] == 0
    assert not any(f["dimension"] == "presentation_naming" for f in flags)


def test_abstract_overload_and_ieeetran_info():
    # IEEEtran journal with concise abstract -> INFO only, no HIGH bold flag
    tex_clean = r"""
    \documentclass[journal]{IEEEtran}
    \begin{document}
    \begin{abstract}
    We study multi-UAV edge offloading under stochastic arrivals.
    We propose L-MAPPO with closed-form resource allocation and a CBF safety filter.
    Simulations show a 25.7\% energy reduction over block coordinate descent.
    \end{abstract}
    \end{document}
    """
    m1, f1 = evaluate_presentation_fingerprint(tex_clean)
    assert any(f["dimension"] == "presentation_abstract" and f["severity"] == "INFO" for f in f1)
    assert not any(f["dimension"] == "presentation_abstract" and f["severity"] == "HIGH" for f in f1)

    # Explicit bold + overloaded abstract -> HIGH + MEDIUM
    long_words = " ".join(["network"] * 230)
    tex_bad = rf"""
    \documentclass[journal]{{IEEEtran}}
    \begin{{document}}
    \begin{{abstract}}
    \textbf{{We propose a system with $a=1$, $b=2$, $c=3$, $d=4$, $e=5$, $f=6$, $g=7$, $\mathcal{{O}}(K)$, and $\mathcal{{O}}(UK^2)$ achieving 1.1\%, 2.2\%, 3.3\%, 4.4\%, 5.5\%, 6.6\%, 7.7\%, 8.8\%, 9.9\%. {long_words}}}
    \end{{abstract}}
    \end{{document}}
    """
    m2, f2 = evaluate_presentation_fingerprint(tex_bad)
    assert m2["abstract"]["explicit_bold"] is True
    assert any(f["severity"] == "HIGH" and f["dimension"] == "presentation_abstract" for f in f2)
    assert any(f["severity"] == "MEDIUM" and f["dimension"] == "presentation_abstract" for f in f2)


def test_inline_math_density_and_multi_def():
    tex = r"""
    \begin{document}
    Let $a \triangleq 1$, $b \triangleq 2$, $c \triangleq 3$, and $d \triangleq 4$ denote the system weights.
    Also $x_1 = 1$, $x_2 = 2$, $x_3 = 3$, $x_4 = 4$, $x_5 = 5$, $x_6 = 6$, $x_7 = 7$, $x_8 = 8$,
    $x_9 = 9$, $x_{10} = 10$, $x_{11} = 11$, $x_{12} = 12$ hold across slots $t$ and devices $k$
    in this short paragraph.
    \end{document}
    """
    m, flags = evaluate_presentation_fingerprint(tex)
    assert m["inline_math"]["dense_paragraphs"] >= 1
    assert m["inline_math"]["multi_def_sentences"] >= 1
    assert any(f["dimension"] == "presentation_inline_math" and f["severity"] == "MEDIUM" for f in flags)


def test_heading_complexity():
    tex = r"""
    \begin{document}
    \subsection{Backlog-Clipped Service Deficit Bound, Translational-Lift Stability, and Conditional Bounds (Theorem~3)}
    \begin{enumerate}
    \item \emph{Exact Two-Tier Conservation, KKT Water-Filling, and Greedy Association (Lemma~1, Theorem~1):} Details.
    \end{enumerate}
    \section{System Model}
    \end{document}
    """
    m, flags = evaluate_presentation_fingerprint(tex)
    assert m["headings"]["chained_or_ref_titles"] == 2
    assert any(f["dimension"] == "presentation_headings" and f["severity"] == "MEDIUM" for f in flags)


def test_absolutist_adjectives():
    tex = r"""
    \begin{document}
    \section{Exact Unconditional Analytical Framework}
    We provide an exact, explicit, unconditional, analytical, assumption-free, strictly convex,
    zero-duality-gap, deterministic, closed-form guarantee that certifies the rigorous system.
    \end{document}
    """
    m, flags = evaluate_presentation_fingerprint(tex)
    assert m["absolutist"]["density_per_1k_words"] > 6.0
    assert m["absolutist"]["visible_zone_hits"] >= 1
    assert any(f["dimension"] == "presentation_absolutist" and f["severity"] == "MEDIUM" for f in flags)


def test_transition_repetition_and_repeated_sentences():
    s1 = "The proposed controller stabilizes the edge queues across all simulated network topologies."
    filler = " ".join(
        [
            "Furthermore, the queue stays bounded.",
            "Furthermore, the energy drops.",
            "Furthermore, the delay improves.",
            "To quantify the gain, we run tests.",
            "To isolate the effect, we ablate.",
            "To evaluate scalability, we sweep.",
            "To assess safety, we check collisions.",
        ]
        + ["Normal empirical sentences vary naturally in structure and length."] * 20
        + [s1, s1]
    )
    tex = f"\\begin{{document}}\n{filler}\n\\end{{document}}"
    m, flags = evaluate_presentation_fingerprint(tex)
    assert m["transitions"]["formulaic_opener_count"] >= 7
    assert m["repetition"]["repeated_sentence_count"] >= 1
    assert any(f["dimension"] == "presentation_transitions" for f in flags)
    assert any(f["dimension"] == "presentation_repetition" and f["severity"] == "MEDIUM" for f in flags)


def test_font_pairing_positive_and_negative():
    tex_mismatch = r"""
    \documentclass[journal]{IEEEtran}
    \usepackage{amsmath,amssymb}
    \begin{document}
    Hello $x = 1$.
    \end{document}
    """
    m1, f1 = evaluate_presentation_fingerprint(tex_mismatch)
    assert m1["fonts"]["mismatch"] is True
    assert any(f["dimension"] == "presentation_fonts" and f["severity"] == "LOW" for f in f1)

    tex_matched = r"""
    \documentclass[journal]{IEEEtran}
    \usepackage{amsmath}
    \usepackage{newtxtext,newtxmath}
    \begin{document}
    Hello $x = 1$.
    \end{document}
    """
    m2, f2 = evaluate_presentation_fingerprint(tex_matched)
    assert m2["fonts"]["mismatch"] is False
    assert not any(f["dimension"] == "presentation_fonts" for f in f2)


def test_integration_audit_orwell_prose():
    tex = r"""
    \documentclass[journal]{IEEEtran}
    \usepackage{amsmath}
    \begin{document}
    \begin{abstract}
    We study UAV edge computing with L-MAPPO.
    \end{abstract}
    \section{Introduction}
    We propose \texttt{Lya-BiMAPPO-MaxSNR} and \texttt{Penalty-BiMAPPO}.
    \end{document}
    """
    res = audit_orwell_prose(tex)
    assert res["status"] == "SUCCESS"
    assert "presentation" in res["dimensions"]
    assert "7. Presentation & Reviewer Flags" in res["report_markdown"]
    assert "7-Dimension" in res["report_markdown"]
