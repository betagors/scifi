"""Tests for scifi.proofs theorem-proof sentinel (theorist/euclid)."""

from pathlib import Path

from scifi.proofs.auditor import audit_latex_proofs
from scifi.proofs.models import ProofIssueCategory


def test_detects_orphan_theorem(tmp_path: Path):
    tex_content = r"""
    \documentclass{article}
    \begin{document}
    \begin{theorem}
    \label{thm:main_bound}
    Under bounded variance, the empirical loss converges to zero with probability 1.
    \end{theorem}

    Section 4 discusses empirical validation.
    \end{document}
    """
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(tex_content, encoding="utf-8")

    result = audit_latex_proofs(tex_path=tex_file)
    assert result.status == "SUCCESS"
    assert result.total_theorems == 1
    assert result.orphan_theorems == 1
    assert len(result.issues) == 1
    assert result.issues[0]["category"] == ProofIssueCategory.ORPHAN_THEOREM.value


def test_inline_proof_passes(tmp_path: Path):
    tex_content = r"""
    \documentclass{article}
    \begin{document}
    \begin{lemma}
    \label{lem:smoothness}
    The loss gradient is $L$-Lipschitz continuous.
    \end{lemma}
    \begin{proof}
    By Cauchy-Schwarz inequality, $\| \nabla f(x) - \nabla f(y) \| \le L \| x - y \|$.
    \end{proof}
    \end{document}
    """
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(tex_content, encoding="utf-8")

    result = audit_latex_proofs(tex_path=tex_file)
    assert result.status == "SUCCESS"
    assert result.total_theorems == 1
    assert result.orphan_theorems == 0
    assert len(result.issues) == 0


def test_appendix_proof_pointer_verified(tmp_path: Path):
    tex_content = r"""
    \documentclass{article}
    \begin{document}
    \begin{proposition}
    \label{prop:stability}
    The queue remains strongly stable under condition C.
    \end{proposition}
    The proof is deferred to Appendix~\ref{app:prop_proof}.

    \appendix
    \section{Proofs}
    \label{app:prop_proof}
    \begin{proof}
    Construct the Lyapunov function $V(x) = x^2$.
    \end{proof}
    \end{document}
    """
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(tex_content, encoding="utf-8")

    result = audit_latex_proofs(tex_path=tex_file)
    assert result.status == "SUCCESS"
    assert result.total_theorems == 1
    assert result.orphan_theorems == 0
    assert len(result.issues) == 0
    assert result.theorems[0].appendix_verified is True


def test_unresolved_appendix_proof_flagged(tmp_path: Path):
    tex_content = r"""
    \documentclass{article}
    \begin{document}
    \begin{theorem}
    \label{thm:optimality}
    The policy achieves asymptotic optimality.
    \end{theorem}
    The detailed proof is left to Appendix~\ref{app:missing_label}.
    \end{document}
    """
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(tex_content, encoding="utf-8")

    result = audit_latex_proofs(tex_path=tex_file)
    assert result.status == "SUCCESS"
    assert len(result.issues) == 1
    assert result.issues[0]["category"] == ProofIssueCategory.UNRESOLVED_APPENDIX_PROOF.value
