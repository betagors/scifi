"""
Tests for Hypatia-backed claim-to-citation entailment audit (Argus / Alex upgrade).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from scifi.argus.cli import main as argus_cli_main
from scifi.argus.entailment import (
    audit_claim_entailment,
    evaluate_claim_entailment,
    extract_cited_metrics,
)
from scifi.argus.models import EntailmentStatus
from scifi.cache import RegistryCache
from scifi.literature.models import PaperIdentifierRecord, PaperRecord


def test_evaluate_claim_supported_with_metric_equivalence() -> None:
    status, conf, reason, overlap, missing, excerpt = evaluate_claim_entailment(
        "Smith et al. achieved 94.2% accuracy on ImageNet classification using residual connections.",
        paper_title="Deep Residual Learning for ImageNet Classification",
        evidence_text=("We evaluate residual connections on ImageNet classification and obtain an accuracy of 0.942."),
    )
    assert status == EntailmentStatus.SUPPORTED
    assert conf > 0.7
    assert overlap > 0.5
    assert missing == []
    assert excerpt is None


def test_evaluate_claim_off_topic() -> None:
    status, conf, reason, overlap, missing, excerpt = evaluate_claim_entailment(
        "AlphaFold predicts protein folding and alpha-helix secondary structures from amino acid sequences.",
        paper_title="ARIMA Models for Stock Market Volatility Forecasting",
        evidence_text=(
            "We apply autoregressive integrated moving average models to forecast daily equity returns "
            "and financial market volatility across European stock exchanges."
        ),
    )
    assert status == EntailmentStatus.OFF_TOPIC
    assert overlap < 0.15
    assert "off-topic" in reason.lower()


def test_evaluate_claim_contradicts_polarity_and_direction() -> None:
    status_neg, _, _, _, _, excerpt_neg = evaluate_claim_entailment(
        "Batch normalization improves gradient convergence in deep recurrent networks.",
        paper_title="Batch Normalization in Recurrent Networks",
        evidence_text=(
            "Our experiments show that batch normalization does not improve gradient convergence "
            "in deep recurrent networks."
        ),
    )
    assert status_neg == EntailmentStatus.CONTRADICTS
    assert excerpt_neg is not None

    status_dir, _, _, _, _, excerpt_dir = evaluate_claim_entailment(
        "Increasing dropout rate increases generalization accuracy on CIFAR-10.",
        paper_title="Dropout Effects on CIFAR-10",
        evidence_text=("We observe that increasing dropout rate decreases generalization accuracy on CIFAR-10."),
    )
    assert status_dir == EntailmentStatus.CONTRADICTS
    assert excerpt_dir is not None


def test_evaluate_claim_missing_metric() -> None:
    status, _, reason, _, missing, _ = evaluate_claim_entailment(
        "Their transformer model achieved 95.4% accuracy on GLUE.",
        paper_title="Transformer Evaluation on GLUE",
        evidence_text=("We evaluate our transformer model on the GLUE benchmark and report an accuracy of 88.1%."),
    )
    assert status == EntailmentStatus.MISSING_METRIC
    assert any("95.4%" in m for m in missing)
    assert "95.4%" in reason


def test_extract_cited_metrics_ignores_years_and_sections() -> None:
    metrics = extract_cited_metrics("As shown in Section 3 (2022), the model achieved 91.5% F1 and 2.4x speedup.")
    labels = [m["label"] for m in metrics]
    assert any("91.5%" in lbl for lbl in labels)
    assert any("2.4x" in lbl for lbl in labels)
    assert not any("2022" in lbl for lbl in labels)
    assert not any("Section 3" in lbl for lbl in labels)


def test_evaluate_claim_insufficient_evidence() -> None:
    status, conf, _, _, _, _ = evaluate_claim_entailment(
        "The optimizer converges linearly under strong convexity.",
        paper_title="Linear Convergence",
        evidence_text="",
    )
    assert status == EntailmentStatus.INSUFFICIENT_EVIDENCE
    assert conf == 0.0


def test_audit_claim_entailment_with_lazy_unpaywall_pdf_fallback(tmp_path: Path) -> None:
    tex_file = tmp_path / "main.tex"
    bib_file = tmp_path / "references.bib"

    tex_file.write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "Our baseline achieves 96.8\\% accuracy on ImageNet \\cite{Smith2022Res}.\n"
        "The optimizer diverges on non-convex losses \\cite{Jones2023Opt}.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    bib_file.write_text(
        "@article{Smith2022Res,\n"
        "  title = {ImageNet Residual Baselines},\n"
        "  author = {Smith, Alice},\n"
        "  year = {2022},\n"
        "  doi = {10.1000/smith2022}\n"
        "}\n"
        "@article{Jones2023Opt,\n"
        "  title = {Quantum Entanglement in Spin Lattices},\n"
        "  author = {Jones, Bob},\n"
        "  year = {2023},\n"
        "  doi = {10.1000/jones2023}\n"
        "}\n",
        encoding="utf-8",
    )

    smith_paper = PaperRecord(
        id="W1",
        title="ImageNet Residual Baselines",
        identifiers=[PaperIdentifierRecord(paper_id="W1", provider="doi", external_id="10.1000/smith2022")],
        abstract="We study residual baseline models on ImageNet classification.",
    )
    jones_paper = PaperRecord(
        id="W2",
        title="Quantum Entanglement in Spin Lattices",
        identifiers=[PaperIdentifierRecord(paper_id="W2", provider="doi", external_id="10.1000/jones2023")],
        abstract="We measure spin-lattice entanglement entropy in cryogenic magnetic materials.",
    )

    def fake_resolve_by_doi(self, doi: str):
        if "smith2022" in doi:
            return smith_paper
        if "jones2023" in doi:
            return jones_paper
        return None

    pdf_file = tmp_path / "smith.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    with (
        patch("scifi.literature.resolver.PaperResolver.resolve_by_doi", fake_resolve_by_doi),
        patch(
            "scifi.literature.fetcher.fetch_paper_pdf",
            return_value={"status": "SUCCESS", "source": "Unpaywall", "file_path": str(pdf_file)},
        ),
        patch(
            "scifi.literature.extractor.extract_pdf_text",
            return_value={
                "status": "SUCCESS",
                "abstract": "",
                "system_model_or_method": "Our baseline achieves 96.8% accuracy on ImageNet.",
                "limitations_and_conclusion": "",
                "raw_sample": "",
            },
        ),
    ):
        report = audit_claim_entailment(
            tex_file,
            bib_path=bib_file,
            fetch_pdf=True,
            cache=RegistryCache(db_path=tmp_path / "cache.db"),
        )

    assert report.total_checked == 2
    assert report.supported_count == 1
    assert report.off_topic_count == 1
    assert report.flagged_count == 1
    assert report.findings[0].status == EntailmentStatus.SUPPORTED
    assert "Unpaywall PDF" in (report.findings[0].evidence_source or "")
    assert report.findings[1].status == EntailmentStatus.OFF_TOPIC


def test_argus_cli_entailment_json(tmp_path: Path, capsys) -> None:
    tex_file = tmp_path / "paper.tex"
    bib_file = tmp_path / "refs.bib"
    tex_file.write_text(
        "The model reaches 99.1\\% BLEU score on translation \\cite{Doe2024}.\n",
        encoding="utf-8",
    )
    bib_file.write_text(
        "@article{Doe2024,\n  title={Neural Translation},\n  doi={10.1000/doe2024}\n}\n",
        encoding="utf-8",
    )

    doe_paper = PaperRecord(
        id="W3",
        title="Neural Translation",
        identifiers=[PaperIdentifierRecord(paper_id="W3", provider="doi", external_id="10.1000/doe2024")],
        abstract="We evaluate neural machine translation and achieve a 32.4 BLEU score.",
    )

    with patch("scifi.literature.resolver.PaperResolver.resolve_by_doi", return_value=doe_paper):
        rc = argus_cli_main(
            [
                "audit",
                str(tex_file),
                "--bib",
                str(bib_file),
                "--entailment",
                "--no-pdf",
                "--no-search",
                "--format",
                "json",
            ]
        )

    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert out["entailment"]["missing_metric_count"] == 1
    assert out["entailment"]["findings"][0]["status"] == "MISSING_METRIC"
