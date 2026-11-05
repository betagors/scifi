"""
Unit tests for Multi-File LaTeX Project Resolver (scifi.latex.project).
"""

from __future__ import annotations

from pathlib import Path
import pytest

from scifi.latex.project import find_main_tex, resolve_latex_project


def test_multifile_latex_resolution_and_line_mapping(tmp_path: Path):
    """Verify main.tex + \\input{sections/abstract} + \\include{sections/method.tex} resolves in order with exact provenance."""
    sec_dir = tmp_path / "sections"
    sec_dir.mkdir()

    (sec_dir / "abstract.tex").write_text(
        "\\begin{abstract}\n"
        "We propose a distributed consensus algorithm achieving 98.4\\% accuracy.\n"
        "\\end{abstract}\n",
        encoding="utf-8",
    )
    (sec_dir / "intro.tex").write_text(
        "\\section{Introduction}\n"
        "Prior works \\cite{vaswani2017attention,he2016deep} study deep networks.\n"
        "Let $P$ denote the transmit power.\n",
        encoding="utf-8",
    )
    (sec_dir / "method.tex").write_text(
        "\\section{System Model}\n"
        "Here $\\mathbf{P}$ is the matrix and \\cite{missing2026key} is cited.\n",
        encoding="utf-8",
    )
    (tmp_path / "references.bib").write_text(
        "@article{vaswani2017attention,\n  title={Attention is all you need},\n  author={Vaswani, Ashish},\n  year={2017}\n}\n",
        encoding="utf-8",
    )

    main_tex = tmp_path / "main.tex"
    main_tex.write_text(
        "\\documentclass{article}\n"
        "\\title{Distributed Consensus Optimization for Edge Networks}\n"
        "\\begin{document}\n"
        "\\input{sections/abstract}\n"
        "\\input{sections/intro.tex}\n"
        "\\include{sections/method}\n"
        "% \\input{sections/commented_out}\n"
        "\\bibliography{references}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )

    # Resolve by passing the directory directly
    proj = resolve_latex_project(tmp_path)
    assert proj.is_multifile is True
    assert proj.entrypoint == main_tex.resolve()
    assert [f.relative_path for f in proj.files] == [
        "main.tex",
        "sections/abstract.tex",
        "sections/intro.tex",
        "sections/method.tex",
    ]
    assert len(proj.bib_files) == 1
    assert proj.bib_files[0].name == "references.bib"
    assert set(proj.cited_keys) == {"vaswani2017attention", "he2016deep", "missing2026key"}
    assert proj.missing_includes == []

    # Verify line provenance mapping back to sections/method.tex
    merged_lines = proj.merged_text.splitlines()
    target_idx = next(i for i, l in enumerate(merged_lines, start=1) if "missing2026key" in l)
    src_file, src_line = proj.map_merged_line(target_idx)
    assert src_file == "sections/method.tex"
    assert src_line == 2


def test_circular_include_and_missing_subfile_safety(tmp_path: Path):
    """Ensure circular \\input loops terminate cleanly and missing includes are recorded."""
    a_tex = tmp_path / "main.tex"
    b_tex = tmp_path / "sub.tex"

    a_tex.write_text(
        "\\documentclass{article}\n"
        "\\input{sub}\n"
        "\\input{nonexistent_section}\n",
        encoding="utf-8",
    )
    b_tex.write_text(
        "\\section{Sub}\n"
        "\\input{main}\n",
        encoding="utf-8",
    )

    proj = resolve_latex_project(a_tex)
    assert len(proj.files) == 2
    assert "nonexistent_section" in proj.missing_includes


def test_find_main_tex_prioritizes_documentclass(tmp_path: Path):
    """Ensure find_main_tex picks the file with \\documentclass rather than an alphabetical helper file."""
    (tmp_path / "abstract.tex").write_text("Some abstract text without documentclass.", encoding="utf-8")
    paper = tmp_path / "paper.tex"
    paper.write_text("\\documentclass{IEEEtran}\n\\begin{document}\nHi\n\\end{document}", encoding="utf-8")

    found = find_main_tex(tmp_path)
    assert found == paper.resolve()
