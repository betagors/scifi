"""
Unit tests for LaTeX booktabs table generator (scifi.latex.tables)
and multi-file venue & double-blind compliance checker (scifi.latex.venue).
"""

from __future__ import annotations

from pathlib import Path

from scifi.latex.tables import generate_latex_table
from scifi.latex.venue import check_venue_compliance


def test_generate_latex_table_bold_underline_and_std(tmp_path: Path):
    rows = [
        {"Method": "Baseline A", "Accuracy": 88.2, "Accuracy_std": 0.5, "Latency": 14.2},
        {"Method": "Baseline B", "Accuracy": 91.5, "Accuracy_std": 0.3, "Latency": 11.8},
        {"Method": "Proposed (Ours)", "Accuracy": 94.8, "Accuracy_std": 0.2, "Latency": 9.4},
    ]
    out_tex = tmp_path / "tables" / "results.tex"
    res = generate_latex_table(
        data_input=rows,
        caption="Main benchmark comparison.",
        label="tab:main",
        lower_is_better=["Latency"],
        precision=1,
        output_path=out_tex,
    )

    assert res["status"] == "SUCCESS"
    assert out_tex.is_file()
    latex = res["latex"]
    assert "\\toprule" in latex
    assert "\\midrule" in latex
    assert "\\bottomrule" in latex
    # Best Accuracy (94.8 ± 0.2) bolded
    assert "$\\mathbf{94.8 \\pm 0.2}$" in latex
    # Second-best Accuracy (91.5 ± 0.3) underlined
    assert "\\underline{$91.5 \\pm 0.3$}" in latex
    # Best Latency (lowest: 9.4) bolded
    assert "\\textbf{9.4}" in latex
    # Second-best Latency (11.8) underlined
    assert "\\underline{11.8}" in latex


def test_multifile_venue_compliance_and_double_blind(tmp_path: Path):
    sec_dir = tmp_path / "sections"
    sec_dir.mkdir()

    (tmp_path / "main.tex").write_text(
        "\\documentclass{article}\n"
        "\\author{Jane Doe and John Smith}\n"
        "\\begin{document}\n"
        "\\input{sections/experiments}\n"
        "\\section*{Acknowledgments}\n"
        "Funded by NSF Grant 12345.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )

    (sec_dir / "experiments.tex").write_text(
        "\\section{Experiments}\n"
        "\\vspace{-4mm}\n"
        "Code is at https://github.com/janedoe/secret-repo.\n"
        "\\begin{figure}\\caption{A}\\label{fig:unreferenced}\\end{figure}\n",
        encoding="utf-8",
    )

    res = check_venue_compliance(
        tmp_path,
        venue="neurips",
        author_names=["Jane Doe"],
    )
    assert res["status"] == "VIOLATIONS_FOUND"
    assert res["is_compliant"] is False
    assert res["double_blind"] is True
    assert res["is_multifile"] is True

    categories = {i["category"] for i in res["issues"]}
    assert "ANONYMIZATION_LEAK" in categories
    assert "LAYOUT_HACK" in categories
    assert "UNREFERENCED_FLOAT" in categories

    # Verify exact file provenance for the \vspace hack in sections/experiments.tex
    vspace_issue = next(i for i in res["issues"] if i["category"] == "LAYOUT_HACK")
    assert vspace_issue["file"] == "sections/experiments.tex"
    assert vspace_issue["line"] == 2
