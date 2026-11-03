"""
Tests for 4-Stage Research Gap Extraction and Corroboration Engine (scifi.literature.gaps).
"""

import pytest

from scifi.literature.gaps import GapExtractor
from scifi.literature.models import (
    CitationContextRecord,
    EvidenceRecord,
    PaperGapRecord,
    PaperRecord,
)


def test_extract_abstract_and_corroborate_citation_gaps():
    """Verify primary end-to-end pipeline: abstract extraction, inbound citations, and corroboration."""
    extractor = GapExtractor()
    paper = PaperRecord(
        id="p-target",
        title="Scalable Coordination",
        year=2021,
        abstract="We propose a coordination algorithm. However, this method assumes full channel state information.",
    )

    # 1. Abstract extraction
    abstract_results = extractor.extract_abstract_gaps(paper)
    assert len(abstract_results) >= 1
    ev_abs, gap_abs = abstract_results[0]
    assert isinstance(ev_abs, EvidenceRecord)
    assert isinstance(gap_abs, PaperGapRecord)
    assert ev_abs.paper_id == "p-target"
    assert ev_abs.reporting_paper_id is None
    assert ev_abs.source_section == "Abstract"
    assert gap_abs.gap_type == "unstated_assumption"
    assert "channel state information" in gap_abs.claim_summary

    # 2. Inbound citation extraction
    contexts = [
        CitationContextRecord(
            id="c1",
            source_paper_id="p-src-1",
            target_paper_id="p-target",
            context_text="While Scalable Coordination performs well, it assumes full channel knowledge, limiting deployment.",
            section_name="Related Work",
        ),
        CitationContextRecord(
            id="c2",
            source_paper_id="p-src-2",
            target_paper_id="p-target",
            context_text="Unlike Scalable Coordination, which requires full channel knowledge, our method uses partial states.",
            section_name="Introduction",
        ),
    ]
    citation_results = extractor.extract_citation_context_gaps(paper, contexts)
    assert len(citation_results) == 2
    ev_c1, gap_c1 = citation_results[0]
    assert ev_c1.reporting_paper_id == "p-src-1"
    assert ev_c1.source_section == "Related Work"

    # 3. Corroboration triage
    all_results = extractor.corroborate_gaps(abstract_results + citation_results)
    corroborated = [g for _, g in all_results if g.verification_status == "corroborated"]
    assert len(corroborated) >= 1
    assert corroborated[0].corroborating_count >= 2


def test_abstract_gap_extraction_contrastive_signals():
    """Verify that only contrastive/limitation sentences are extracted from abstracts."""
    extractor = GapExtractor()

    # Abstract with positive sentences and a contrastive limitation
    paper = PaperRecord(
        id="p-1",
        title="Transformer Efficiency",
        abstract=(
            "We propose an efficient transformer model for natural language processing. "
            "Our model achieves state-of-the-art accuracy on translation benchmarks. "
            "However, computing the self-attention map incurs quadratic memory complexity O(N^2)."
        ),
    )
    results = extractor.extract_abstract_gaps(paper)
    assert len(results) == 1
    ev, gap = results[0]
    assert ev.paper_id == "p-1"
    assert ev.reporting_paper_id is None
    assert "quadratic memory complexity" in ev.extracted_text.lower()
    assert gap.gap_type == "computational_complexity"
    assert gap.verification_status == "candidate"

    # Abstract with no limitations
    paper_positive = PaperRecord(
        id="p-pos",
        title="Flawless System",
        abstract="We present an optimal distributed cache. It guarantees zero latency and 100% throughput.",
    )
    assert extractor.extract_abstract_gaps(paper_positive) == []

    # Paper with empty or None abstract
    paper_empty = PaperRecord(id="p-empty", title="No Abstract", abstract=None)
    assert extractor.extract_abstract_gaps(paper_empty) == []


def test_citation_context_gap_extraction_with_attribution():
    """Verify inbound citation context extraction attributes evidence to the citing paper."""
    extractor = GapExtractor()
    target_paper = PaperRecord(id="p-target-1", title="Original Graph Net")

    contexts = [
        CitationContextRecord(
            id="c-att-1",
            source_paper_id="p-citing-99",
            target_paper_id="p-target-1",
            context_text="Original Graph Net degrades significantly when applied to graphs with more than 10k nodes.",
            section_name="Background",
        ),
        # Context targeting a different paper should be ignored
        CitationContextRecord(
            id="c-att-2",
            source_paper_id="p-citing-100",
            target_paper_id="p-other-paper",
            context_text="However, Other Paper fails completely on sparse graphs.",
            section_name="Related Work",
        ),
        # Context without limitation should be ignored
        CitationContextRecord(
            id="c-att-3",
            source_paper_id="p-citing-101",
            target_paper_id="p-target-1",
            context_text="We build upon the excellent representations developed by Original Graph Net.",
            section_name="Methods",
        ),
    ]

    results = extractor.extract_citation_context_gaps(target_paper, contexts)
    assert len(results) == 1
    ev, gap = results[0]
    assert ev.paper_id == "p-target-1"
    assert ev.reporting_paper_id == "p-citing-99"
    assert ev.source_section == "Background"
    assert gap.gap_type == "empirical_limitation"
    assert gap.verification_status == "candidate"


def test_classification_into_five_canonical_gap_categories():
    """Verify that sentences are classified into each of the 5 canonical gap categories."""
    extractor = GapExtractor()

    test_cases = [
        (
            "However, the algorithm suffers from high latency and prohibitive computational complexity O(N^2).",
            "computational_complexity",
        ),
        (
            "However, the theoretical convergence proof relies on the unstated assumption of static topology.",
            "unstated_assumption",
        ),
        (
            "However, the approach fails on large benchmarks and was only evaluated on toy datasets.",
            "empirical_limitation",
        ),
        (
            "However, the representations suffer from severe degradation under out-of-distribution domain shift.",
            "generalization_bound",
        ),
        (
            "However, extending this method to asynchronous environments remains an open problem left for future work.",
            "unresolved_problem",
        ),
    ]

    for sentence, expected_type in test_cases:
        paper = PaperRecord(
            id=f"p-{expected_type}",
            title=f"Paper for {expected_type}",
            abstract=f"We study foundational machine learning. {sentence}",
        )
        results = extractor.extract_abstract_gaps(paper)
        assert len(results) == 1, f"Failed to extract gap for {expected_type}"
        _, gap = results[0]
        assert gap.gap_type == expected_type, (
            f"Expected {expected_type}, got {gap.gap_type} for sentence: {sentence}"
        )


def test_corroboration_clustering_promotes_status():
    """Verify clustering promotes verification_status to 'corroborated' when 2+ citing sources report the same limitation."""
    extractor = GapExtractor()
    target_paper = PaperRecord(id="p-target-2", title="Federated Optimizer")

    # 1. Single citing source: status remains candidate
    single_context = [
        CitationContextRecord(
            id="c-single",
            source_paper_id="p-src-a",
            target_paper_id="p-target-2",
            context_text="Federated Optimizer exhibits high latency bottleneck during client synchronization.",
        ),
    ]
    results_single = extractor.extract_citation_context_gaps(target_paper, single_context)
    assert len(results_single) == 1
    corroborated_single = extractor.corroborate_gaps(results_single)
    assert len(corroborated_single) == 1
    assert corroborated_single[0][1].verification_status == "candidate"
    assert corroborated_single[0][1].corroborating_count == 0

    # 2. Two independent citing sources reporting the same latency limitation: status promoted to corroborated
    two_contexts = [
        CitationContextRecord(
            id="c-src-1",
            source_paper_id="p-src-a",
            target_paper_id="p-target-2",
            context_text="Federated Optimizer exhibits high latency bottleneck during client synchronization.",
        ),
        CitationContextRecord(
            id="c-src-2",
            source_paper_id="p-src-b",
            target_paper_id="p-target-2",
            context_text="Unlike Federated Optimizer which suffers from synchronization latency overhead, our method is async.",
        ),
    ]
    results_two = extractor.extract_citation_context_gaps(target_paper, two_contexts)
    corroborated_two = extractor.corroborate_gaps(results_two)
    for _, gap in corroborated_two:
        assert gap.verification_status == "corroborated"
        assert gap.corroborating_count >= 2

    # 3. Two different gaps for the same paper should NOT cluster together
    diff_contexts = [
        CitationContextRecord(
            id="c-diff-1",
            source_paper_id="p-src-1",
            target_paper_id="p-target-2",
            context_text="Federated Optimizer exhibits high latency bottleneck during synchronization.",
        ),
        CitationContextRecord(
            id="c-diff-2",
            source_paper_id="p-src-2",
            target_paper_id="p-target-2",
            context_text="Federated Optimizer degrades under out-of-distribution client domain shift.",
        ),
    ]
    results_diff = extractor.extract_citation_context_gaps(target_paper, diff_contexts)
    corroborated_diff = extractor.corroborate_gaps(results_diff)
    # Neither should be corroborated since they describe different gap types
    for _, gap in corroborated_diff:
        assert gap.verification_status == "candidate"
        assert gap.corroborating_count == 0


def test_corroboration_contradiction_tracking():
    """Verify that citing papers resolving or refuting a limitation track contradicting_count."""
    extractor = GapExtractor()
    target_paper = PaperRecord(id="p-target-3", title="Prior Work")

    contexts = [
        CitationContextRecord(
            id="c-lim",
            source_paper_id="p-src-lim",
            target_paper_id="p-target-3",
            context_text="Prior Work suffers from quadratic memory complexity O(N^2) bottleneck.",
        ),
        CitationContextRecord(
            id="c-resolv",
            source_paper_id="p-src-res",
            target_paper_id="p-target-3",
            context_text="Our method resolves the quadratic memory complexity bottleneck of Prior Work.",
        ),
    ]
    results = extractor.extract_citation_context_gaps(target_paper, contexts)
    corroborated = extractor.corroborate_gaps(results)
    # The gap should reflect the contradiction
    disputed = [g for _, g in corroborated if g.contradicting_count > 0]
    assert len(disputed) >= 1
    assert disputed[0].contradicting_count >= 1
    assert disputed[0].verification_status == "disputed"


def test_extract_all_gaps_pipeline():
    """Verify extract_all_gaps integrates abstract extraction, citation extraction, and corroboration."""
    extractor = GapExtractor()
    paper = PaperRecord(
        id="p-full",
        title="Neural SDE",
        abstract="We model continuous systems. However, this method assumes ideal synchronization.",
    )
    contexts = [
        CitationContextRecord(
            id="c-full-1",
            source_paper_id="p-c1",
            target_paper_id="p-full",
            context_text="While Neural SDE requires ideal synchronization, our method works asynchronously.",
        ),
    ]
    results = extractor.extract_all_gaps(paper, contexts)
    assert len(results) == 2
    for ev, gap in results:
        assert gap.verification_status == "corroborated"
        assert gap.corroborating_count >= 1
        assert gap.gap_type == "unstated_assumption"
