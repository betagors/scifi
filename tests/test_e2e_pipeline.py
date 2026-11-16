"""End-to-end offline integration smoke tests for SciFi's parallel audit, config validation, and submission bundle."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scifi.citation_verifier.bib_auditor import audit_bib_content
from scifi.citation_verifier.models import Author, CitationMetadata, VerificationStatus
from scifi.config import validate_workspace_config
from scifi.doctor import audit_manuscript
from scifi.submission import prepare_submission_bundle


def _write_sample_project(root: Path) -> Path:
    """Create a minimal multi-file LaTeX manuscript fixture with bib, figure, and scifi.toml."""
    (root / "sections").mkdir(parents=True, exist_ok=True)
    (root / "figures").mkdir(parents=True, exist_ok=True)

    (root / "scifi.toml").write_text(
        "[manuscript]\n"
        'main_tex = "main.tex"\n'
        'bib_file = "references.bib"\n'
        'target_venue = "ieee"\n'
        "double_blind = true\n"
        'author_whitelist = ["Jane Doe"]\n',
        encoding="utf-8",
    )

    (root / "references.bib").write_text(
        "@article{vaswani2017attention,\n"
        "  title = {Attention Is All You Need},\n"
        "  author = {Vaswani, Ashish and Shazeer, Noam},\n"
        "  year = {2017},\n"
        "  journal = {Advances in Neural Information Processing Systems},\n"
        "  doi = {10.48550/arXiv.1706.03762}\n"
        "}\n",
        encoding="utf-8",
    )

    # Minimal valid PDF header for vector figure detection
    (root / "figures" / "arch.pdf").write_bytes(b"%PDF-1.4\n%EOF\n")

    main_tex = root / "main.tex"
    main_tex.write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\title{Efficient Sparse Attention Mechanisms for Edge Inference}\n"
        "\\begin{abstract}\n"
        "Edge devices require low-latency sequence models under strict memory budgets. "
        "Standard self-attention scales quadratically with sequence length, limiting deployment. "
        "We introduce a block-sparse attention kernel that reduces memory traffic by 3.2x "
        "across three public benchmarks while preserving 99.1\\% of baseline accuracy. "
        "Evaluated across five random seeds on an NVIDIA A100 GPU, the approach achieves "
        "consistent throughput gains with bounded approximation error.\n"
        "\\end{abstract}\n"
        "\\input{sections/method}\n"
        "\\bibliographystyle{IEEEtran}\n"
        "\\bibliography{references}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )

    (root / "sections" / "method.tex").write_text(
        "\\section{Methodology}\n"
        "Building on Transformer attention~\\cite{vaswani2017attention}, we partition tokens into blocks. "
        "Figure~\\ref{fig:arch} illustrates the dataflow across memory banks.\n"
        "\\begin{figure}[t]\n"
        "  \\centering\n"
        "  \\includegraphics{figures/arch.pdf}\n"
        "  \\caption{Block-sparse attention architecture.}\n"
        "  \\label{fig:arch}\n"
        "\\end{figure}\n",
        encoding="utf-8",
    )

    return main_tex


def test_validate_workspace_config_valid_and_invalid(tmp_path: Path) -> None:
    """validate_workspace_config catches type errors and unknown keys while accepting valid scifi.toml."""
    _write_sample_project(tmp_path)
    valid = validate_workspace_config(tmp_path)
    assert valid["valid"] is True
    assert valid["toml_found"] is True
    assert valid["errors"] == []

    (tmp_path / "scifi.toml").write_text(
        '[manuscript]\ndouble_blind = "yes"\nunknown_flag = 1\n',
        encoding="utf-8",
    )
    invalid = validate_workspace_config(tmp_path)
    assert invalid["valid"] is False
    assert any("double_blind" in err for err in invalid["errors"])
    assert any("unknown_flag" in warn for warn in invalid["warnings"])


def test_concurrent_bib_audit_preserves_order_and_tallies() -> None:
    """audit_bib_content with max_workers > 1 preserves exact entry order and status counts."""
    bib_text = (
        "@article{first2020,\n  title={First Paper},\n  author={Doe, Jane},\n  year={2020},\n  doi={10.1000/1}\n}\n\n"
        "@article{second2021,\n  title={Second Paper},\n  author={Smith, John},\n  year={2021},\n  doi={10.1000/2}\n}\n\n"
        "@article{third2022,\n  title={Third Paper},\n  author={Lee, Ada},\n  year={2022},\n  doi={10.1000/3}\n}\n"
    )

    def _fake_resolve(id_type: str, id_val: str, extra: dict, **kwargs) -> CitationMetadata:
        year_map = {"10.1000/1": 2020, "10.1000/2": 2021, "10.1000/3": 2022}
        title_map = {"10.1000/1": "First Paper", "10.1000/2": "Second Paper", "10.1000/3": "Third Paper"}
        author_map = {"10.1000/1": "Jane Doe", "10.1000/2": "John Smith", "10.1000/3": "Ada Lee"}
        return CitationMetadata(
            identifier_type=id_type,
            identifier_value=id_val,
            status=VerificationStatus.VERIFIED,
            title=title_map[id_val],
            authors=[Author(name=author_map[id_val])],
            year=year_map[id_val],
            source_registry="Crossref",
        )

    with patch("scifi.citation_verifier.bib_auditor.resolve_citation", side_effect=_fake_resolve):
        report = audit_bib_content(bib_text, search_missing=False, max_workers=3)

    assert report.total_entries == 3
    assert report.verified_count == 3
    assert [e.identifier_value for e in report.entries] == ["10.1000/1", "10.1000/2", "10.1000/3"]


def test_e2e_offline_manuscript_audit_parallel_matches_sequential_and_bundles(tmp_path: Path) -> None:
    """Full offline project audit produces identical results in parallel vs sequential mode and bundles cleanly."""
    main_tex = _write_sample_project(tmp_path)

    par = audit_manuscript(main_tex, live=False, persist_history=False, parallel=True)
    seq = audit_manuscript(main_tex, live=False, persist_history=False, parallel=False)

    assert par["config_validation"]["valid"] is True
    assert par["readiness_score"] == seq["readiness_score"]
    assert par["stages"]["alex_bibliography"]["missing_bib_keys"] == []
    assert set(par["stages"].keys()) == set(seq["stages"].keys())

    bundle = prepare_submission_bundle(
        target_dir_or_tex=main_tex,
        venue="ieee",
        output_dir=tmp_path / "submission_bundle",
        no_code=True,
        authors=[{"name": "Jane Doe", "affiliation": "Example University", "email": "jane@example.edu"}],
    )
    assert bundle.to_dict().get("status") in {"SUCCESS", "PARTIAL"}
    assert (tmp_path / "submission_bundle" / "submission_manifest.json").is_file()
