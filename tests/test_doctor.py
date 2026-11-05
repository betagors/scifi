"""
Unit tests for End-to-End Multi-File Manuscript Readiness Auditor (scifi.doctor)
and multi-file Shannon extraction (scifi.shannon).
"""

from __future__ import annotations

from pathlib import Path

from scifi.doctor import audit_manuscript
from scifi.shannon import evaluate_manuscript_metadata, extract_latex_metadata


def test_multifile_doctor_pipeline_and_shannon_extraction(tmp_path: Path):
    """
    Create a realistic multi-file LaTeX manuscript:
    - main.tex (contains \\title and \\input{sections/...})
    - sections/abstract.tex (contains \\begin{abstract} and \\begin{IEEEkeywords})
    - sections/intro.tex (contains math symbol $P$ and citation)
    - sections/method.tex (contains math symbol $\\mathbf{P}$ and overclaim)
    - references.bib
    """
    sec_dir = tmp_path / "sections"
    sec_dir.mkdir()

    (sec_dir / "abstract.tex").write_text(
        "\\begin{abstract}\n"
        "Distributed edge inference suffers from severe communication bottlenecks under high mobility. "
        "However, existing static partitioning schemes fail when channel capacity fluctuates rapidly. "
        "In this paper, we propose a Lyapunov-guided adaptive offloading algorithm for distributed edge inference. "
        "Simulations on 500 urban traces demonstrate that our framework reduces tail latency by 38.4\\% "
        "and energy consumption by 24.1\\% compared to state-of-the-art baselines, enabling real-time "
        "distributed edge inference on resource-constrained aerial relays.\n"
        "\\end{abstract}\n"
        "\\begin{IEEEkeywords}\n"
        "Lyapunov optimization, task offloading, mobile edge computing, aerial relays, latency minimization\n"
        "\\end{IEEEkeywords}\n",
        encoding="utf-8",
    )

    (sec_dir / "intro.tex").write_text(
        "\\section{Introduction}\n"
        "Recent studies \\cite{mao2017survey} investigate mobile offloading.\n"
        "Let $P$ denote the scalar transmit power.\n",
        encoding="utf-8",
    )

    (sec_dir / "method.tex").write_text(
        "\\section{Proposed Method}\n"
        "We optimize the matrix $\\mathbf{P}$ using \\cite{missing_ref_2026}.\n"
        "Our method outperforms all existing baselines under perfect CSI.\n",
        encoding="utf-8",
    )

    (tmp_path / "references.bib").write_text(
        "@article{mao2017survey,\n"
        "  title={A Survey on Mobile Edge Computing},\n"
        "  author={Mao, Yuyi},\n"
        "  year={2017}\n"
        "}\n"
        "@article{uncited2020work,\n"
        "  title={Uncited Paper},\n"
        "  author={Doe, John},\n"
        "  year={2020}\n"
        "}\n",
        encoding="utf-8",
    )

    (tmp_path / "main.tex").write_text(
        "\\documentclass[journal]{IEEEtran}\n"
        "\\title{Distributed Edge Inference via Lyapunov-Guided Adaptive Offloading in Aerial Networks}\n"
        "\\author{Anonymous Authors}\n"
        "\\begin{document}\n"
        "\\maketitle\n"
        "\\input{sections/abstract}\n"
        "\\input{sections/intro}\n"
        "\\input{sections/method}\n"
        "\\bibliography{references}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )

    # 1. Test multi-file metadata extraction directly
    meta = extract_latex_metadata(tmp_path)
    assert "Distributed Edge Inference" in meta["title"]
    assert "38.4%" in meta["abstract"]
    assert "Lyapunov optimization" in meta["keywords"]
    assert len(meta["files_scanned"]) == 4

    shannon_res = evaluate_manuscript_metadata(tex_path=tmp_path)
    assert shannon_res["status"] == "SUCCESS"
    assert shannon_res["triage_score"]["total_score"] >= 70

    # 2. Test full 6-stage Doctor audit on the project directory
    report_file = tmp_path / "readiness_report.md"
    doc_res = audit_manuscript(
        tex_or_dir_path=tmp_path,
        venue="ieee",
        double_blind=True,
        live=False,
        output_report=report_file,
    )

    assert doc_res["status"] == "SUCCESS"
    assert report_file.is_file()
    assert doc_res["project"]["is_multifile"] is True
    assert doc_res["project"]["tex_files_count"] == 4

    # Stage 1 (Alex): detects missing_ref_2026 and uncited2020work
    alex = doc_res["stages"]["alex_bibliography"]
    assert "missing_ref_2026" in alex["missing_bib_keys"]
    assert "uncited2020work" in alex["uncited_bib_keys"]

    # Stage 3 (Turing): detects cross-section notation clash (P in intro.tex vs \mathbf{P} in method.tex)
    turing = doc_res["stages"]["turing_notation"]
    assert turing["status"] == "NOTATION_INCONSISTENCY"
    base_syms = [m["base_symbol"] for m in turing["multi_variant_symbols"]]
    assert "p" in base_syms

    # Stage 4 (Popper): detects overclaims in sections/method.tex with file provenance
    popper = doc_res["stages"]["popper_claims"]
    assert popper["total_flags"] >= 2
    assert any(f.get("file") == "sections/method.tex" for f in popper["flags"])


def test_new_cli_subcommands_end_to_end(tmp_path: Path, monkeypatch):
    """Verify sf doctor, sf math, sf stats, sf review, sf shannon, sf table, sf venue, and sf config CLI commands."""
    import scifi.cli

    monkeypatch.setenv("SCIFI_CONFIG_PATH", str(tmp_path / "cfg.json"))

    # 1. sf config set / show / init
    assert scifi.cli.main(["config", "set", "email", "researcher@stanford.edu"]) == 0
    assert scifi.cli.main(["config", "show"]) == 0
    toml_out = tmp_path / "scifi.toml"
    assert scifi.cli.main(["config", "init", "--output", str(toml_out), "--venue", "neurips"]) == 0
    assert toml_out.is_file()

    # 2. sf math derivative & convexity
    assert scifi.cli.main(["math", "derivative", "x**3 + 2*x", "x", "3*x**2 + 2"]) == 0
    assert scifi.cli.main(["math", "convexity", "x**2 + y**2", "x,y"]) == 0

    # 3. sf stats audit
    vals = ",".join(str(10.0 + i * 0.1) for i in range(35))
    assert scifi.cli.main(["stats", "audit", vals]) == 0

    # 4. sf table
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("Method,Acc,Loss\nBase,85.0,0.45\nOurs,92.3,0.18\n", encoding="utf-8")
    assert scifi.cli.main(["table", str(csv_file), "--lower-better", "Loss"]) == 0

    # 5. sf review & sf venue & sf doctor on a clean mini-paper
    tex_file = tmp_path / "main.tex"
    tex_file.write_text(
        "\\documentclass{article}\n"
        "\\title{Distributed Edge Inference Optimization for Low-Power Wireless Sensor Networks}\n"
        "\\author{Anonymous Authors}\n"
        "\\begin{document}\n"
        "\\begin{abstract}\n"
        "Wireless sensor networks face strict energy constraints during distributed edge inference. "
        "However, centralized coordinators introduce single-point bottlenecks under dynamic topology shifts. "
        "We formulate a primal-dual consensus protocol for distributed edge inference over time-varying graphs. "
        "Experiments across 100 sensor nodes show our protocol reduces communication overhead by 41.2\\% "
        "and convergence time by 29.5\\% compared to baseline gossip algorithms, enabling scalable "
        "distributed edge inference on battery-powered IoT nodes.\n"
        "\\end{abstract}\n"
        "\\keywords{primal-dual optimization, consensus protocols, IoT energy efficiency, time-varying graphs}\n"
        "\\section{Introduction}\n"
        "Let $x$ denote the local parameter vector.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    assert scifi.cli.main(["review", str(tex_file)]) == 0
    assert scifi.cli.main(["venue", str(tex_file), "--venue", "neurips"]) == 0
    assert scifi.cli.main(["shannon", str(tex_file)]) == 0
    assert scifi.cli.main(["doctor", str(tmp_path)]) == 0
