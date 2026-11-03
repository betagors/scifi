import pytest

from scifi.literature.benchmarks import (
    BenchmarkExtractor,
    CANONICAL_BENCHMARKS,
    CANONICAL_METRICS,
)
from scifi.literature.models import (
    BenchmarkRecord,
    BenchmarkResultRecord,
    EvaluationConditionRecord,
    EvaluationMetricRecord,
    EvidenceRecord,
    PaperRecord,
)


def test_extract_reported_results_from_abstract():
    """Verify standard extraction from abstract containing multiple benchmarks and conditions."""
    paper = PaperRecord(
        id="p-eval-1",
        title="Scaling Laws for Code Generation",
        year=2023,
        abstract="Our method achieves 73.4% pass@1 on HumanEval and 85.2 F1 on SQuAD under zero-shot evaluation.",
    )
    extractor = BenchmarkExtractor()
    extracted = extractor.extract_reported_results(paper)
    assert len(extracted) >= 2

    # Verify HumanEval extraction
    he_items = [item for item in extracted if item[0].name == "HumanEval"]
    assert len(he_items) == 1
    bm, metric, cond, res, ev = he_items[0]

    assert isinstance(bm, BenchmarkRecord)
    assert bm.domain == "Code Generation"
    assert bm.name == "HumanEval"

    assert isinstance(metric, EvaluationMetricRecord)
    assert metric.name == "pass@1"
    assert metric.goal == "maximize"

    assert isinstance(cond, EvaluationConditionRecord)
    assert cond.name in ("zero-shot", "0-shot")

    assert isinstance(res, BenchmarkResultRecord)
    assert res.metric_value == 73.4
    assert res.paper_id == "p-eval-1"
    assert res.benchmark_id == bm.id
    assert res.metric_id == metric.id
    assert res.condition_id == cond.id
    assert res.evidence_id == ev.id

    assert isinstance(ev, EvidenceRecord)
    assert ev.evidence_type == "benchmark_claim"
    assert ev.paper_id == "p-eval-1"
    assert "73.4% pass@1 on HumanEval" in ev.extracted_text

    # Verify SQuAD extraction
    squad_items = [item for item in extracted if item[0].name == "SQuAD"]
    assert len(squad_items) == 1
    bm_s, metric_s, cond_s, res_s, ev_s = squad_items[0]
    assert bm_s.name == "SQuAD"
    assert bm_s.domain == "Question Answering"
    assert metric_s.name == "F1"
    assert metric_s.goal == "maximize"
    assert res_s.metric_value == 85.2
    assert res_s.evidence_id == ev_s.id


def test_extract_minimization_metrics():
    """Verify metrics with goal='minimize' such as WER, perplexity, and latency."""
    paper = PaperRecord(
        id="p-audio-1",
        title="Robust Speech Recognition and Modeling",
        year=2024,
        abstract="The system obtains 3.2% WER on LibriSpeech and a perplexity of 14.5 on WikiText-103 with latency of 12.8 ms.",
    )
    extractor = BenchmarkExtractor()
    extracted = extractor.extract_reported_results(paper)

    # 1. LibriSpeech WER
    libri_items = [item for item in extracted if item[0].name == "LibriSpeech"]
    assert len(libri_items) == 1
    bm, metric, cond, res, ev = libri_items[0]
    assert metric.name == "WER"
    assert metric.goal == "minimize"
    assert metric.unit == "%"
    assert res.metric_value == 3.2

    # 2. WikiText-103 Perplexity and Latency
    wt_items = [item for item in extracted if "WikiText" in item[0].name]
    assert len(wt_items) == 2

    perp_items = [item for item in wt_items if item[1].name == "Perplexity"]
    assert len(perp_items) == 1
    bm_wt, metric_wt, cond_wt, res_wt, ev_wt = perp_items[0]
    assert metric_wt.name == "Perplexity"
    assert metric_wt.goal == "minimize"
    assert res_wt.metric_value == 14.5

    lat_items = [item for item in wt_items if item[1].name == "Latency"]
    assert len(lat_items) == 1
    _, metric_lat, _, res_lat, _ = lat_items[0]
    assert metric_lat.name == "Latency"
    assert metric_lat.goal == "minimize"
    assert res_lat.metric_value == 12.8


def test_extract_no_benchmarks_fallback():
    """Verify papers without benchmark mentions or with empty abstracts return empty list."""
    extractor = BenchmarkExtractor()

    # Abstract without benchmarks
    p1 = PaperRecord(
        id="p-no-bm",
        title="Theoretical Bounds on Deep Representations",
        year=2021,
        abstract="We establish new theoretical bounds on generalization under Lipschitz continuity constraints.",
    )
    assert extractor.extract_reported_results(p1) == []

    # None abstract
    p2 = PaperRecord(id="p-none-abs", title="Paper Without Abstract", abstract=None)
    assert extractor.extract_reported_results(p2) == []

    # Empty string abstract
    p3 = PaperRecord(id="p-empty-abs", title="Paper With Empty Abstract", abstract="   ")
    assert extractor.extract_reported_results(p3) == []


def test_extract_with_unparseable_or_irrelevant_numbers():
    """Verify years (2023) and citation numbers ([12]) are not extracted as scores."""
    paper = PaperRecord(
        id="p-citations",
        title="Review of Modern LLMs",
        year=2023,
        abstract="In 2023, Smith et al. [12] evaluated models on HumanEval without reporting quantitative values.",
    )
    extractor = BenchmarkExtractor()
    extracted = extractor.extract_reported_results(paper)
    # Should not extract 2023 or 12 as HumanEval scores
    assert len(extracted) == 0


def test_extract_conditions_detection():
    """Verify various conditions: 0-shot, 5-shot, few-shot, fine-tuned, greedy, and unspecified."""
    extractor = BenchmarkExtractor()

    # 5-shot condition
    p_5s = PaperRecord(
        id="p-5s",
        title="Few-shot reasoning",
        abstract="Our model achieves 78.5% accuracy on GSM8K under 5-shot prompting.",
    )
    res_5s = extractor.extract_reported_results(p_5s)
    assert len(res_5s) == 1
    assert res_5s[0][2].name == "5-shot"

    # fine-tuned condition
    p_ft = PaperRecord(
        id="p-ft",
        title="Fine-tuned reasoning",
        abstract="We reach 91.2% accuracy on MMLU after fine-tuned adaptation.",
    )
    res_ft = extractor.extract_reported_results(p_ft)
    assert len(res_ft) == 1
    assert res_ft[0][2].name == "fine-tuned"

    # unspecified condition default
    p_unspec = PaperRecord(
        id="p-unspec",
        title="Standard evaluation",
        abstract="We achieve 88.5% on HumanEval.",
    )
    res_unspec = extractor.extract_reported_results(p_unspec)
    assert len(res_unspec) == 1
    assert res_unspec[0][2].name == "unspecified"
    # HumanEval default metric is pass@1
    assert res_unspec[0][1].name == "pass@1"
    assert res_unspec[0][3].metric_value == 88.5


def test_extract_variance_and_percentage_stripping():
    """Verify variance notation (92.3 ± 0.4%) and percentage signs are parsed cleanly."""
    paper = PaperRecord(
        id="p-variance",
        title="Image Classification Advances",
        abstract="Our vision transformer scores 92.3 ± 0.4% top-1 accuracy on ImageNet.",
    )
    extractor = BenchmarkExtractor()
    extracted = extractor.extract_reported_results(paper)
    assert len(extracted) == 1
    bm, metric, cond, res, ev = extracted[0]
    assert bm.name in ("ImageNet", "ImageNet-1k")
    assert metric.name == "Top-1 Accuracy"
    assert res.metric_value == 92.3
    assert res.evidence_id == ev.id


def test_extract_from_evidence_items():
    """Verify extraction from passed evidence items with table/figure provenance."""
    paper = PaperRecord(id="p-ev", title="Multimodal Benchmark Results", abstract="")
    ev_item = EvidenceRecord(
        id="ev-source-1",
        paper_id="p-ev",
        evidence_type="table_excerpt",
        extracted_text="Table 2: State of the art comparison. On HumanEval, our model achieves 82.4% pass@1.",
        extraction_method="pdf_table_miner",
        source_section="Results",
        source_location="Table 2",
    )
    extractor = BenchmarkExtractor()
    extracted = extractor.extract_reported_results(paper, evidence_items=[ev_item])

    assert len(extracted) == 1
    bm, metric, cond, res, ev = extracted[0]
    assert bm.name == "HumanEval"
    assert metric.name == "pass@1"
    assert res.metric_value == 82.4
    assert res.table_or_figure == "Table 2"
    assert res.evidence_id == ev.id


def test_custom_benchmarks():
    """Verify custom benchmark registration and extraction."""
    custom_bm = BenchmarkRecord(
        id="bm-custom-agent",
        name="AgentBench",
        domain="Autonomous Agents",
        canonical_url="https://github.com/agentbench",
        description="Evaluating LLMs as autonomous agents in complex environments",
    )
    extractor = BenchmarkExtractor(custom_benchmarks={"AgentBench": custom_bm})
    paper = PaperRecord(
        id="p-agent",
        title="Evaluating LLM Agents",
        abstract="We evaluate across multiple environments, achieving 64.2% accuracy on AgentBench.",
    )
    extracted = extractor.extract_reported_results(paper)
    assert len(extracted) == 1
    bm, metric, cond, res, ev = extracted[0]
    assert bm.id == "bm-custom-agent"
    assert bm.name == "AgentBench"
    assert bm.domain == "Autonomous Agents"
    assert res.metric_value == 64.2


def test_canonical_catalog_completeness():
    """Verify that canonical benchmark catalog includes required benchmarks across domains."""
    required_benchmarks = [
        # Code
        "humaneval",
        "mbpp",
        "swe-bench",
        # NLP/Reasoning
        "mmlu",
        "gsm8k",
        "math",
        "arc",
        "hellaswag",
        "glue",
        "superglue",
        "squad",
        "truthfulqa",
        # Vision
        "imagenet",
        "imagenet-1k",
        "coco",
        "cifar-10",
        "cifar-100",
        # Translation
        "wmt14",
        "wmt16",
        # Audio
        "librispeech",
    ]
    for key in required_benchmarks:
        assert key in CANONICAL_BENCHMARKS, f"Missing required canonical benchmark: {key}"
        bm = CANONICAL_BENCHMARKS[key]
        assert bm.id.startswith("bm-")
        assert len(bm.name) > 0
        assert len(bm.domain) > 0

    required_metrics = [
        ("pass@1", "maximize", "%"),
        ("pass@10", "maximize", "%"),
        ("accuracy", "maximize", "%"),
        ("top-1-accuracy", "maximize", "%"),
        ("top-5-accuracy", "maximize", "%"),
        ("f1", "maximize", "pts"),
        ("bleu", "maximize", "pts"),
        ("perplexity", "minimize", "score"),
        ("wer", "minimize", "%"),
        ("latency", "minimize", "ms"),
    ]
    for m_key, goal, unit in required_metrics:
        assert m_key in CANONICAL_METRICS, f"Missing required canonical metric: {m_key}"
        metric = CANONICAL_METRICS[m_key]
        assert metric.goal == goal
        assert metric.unit == unit


def test_extract_code_and_translation_benchmarks():
    """Verify extraction on MBPP, SWE-bench, and WMT14 benchmarks."""
    paper = PaperRecord(
        id="p-code-trans",
        title="Multi-task Code and Translation Evaluation",
        year=2024,
        abstract="We achieve 65.4% pass@1 on MBPP and 24.5% on SWE-bench. For translation, our system reaches 34.5 BLEU on WMT14.",
    )
    extractor = BenchmarkExtractor()
    extracted = extractor.extract_reported_results(paper)

    mbpp_items = [item for item in extracted if item[0].name == "MBPP"]
    assert len(mbpp_items) == 1
    assert mbpp_items[0][3].metric_value == 65.4
    assert mbpp_items[0][1].name == "pass@1"

    swe_items = [item for item in extracted if item[0].name == "SWE-bench"]
    assert len(swe_items) == 1
    assert swe_items[0][3].metric_value == 24.5

    wmt_items = [item for item in extracted if item[0].name == "WMT14"]
    assert len(wmt_items) == 1
    assert wmt_items[0][3].metric_value == 34.5
    assert wmt_items[0][1].name == "BLEU"
    assert wmt_items[0][1].goal == "maximize"


def test_extract_vision_benchmarks():
    """Verify extraction on CIFAR-100 and COCO object detection."""
    paper = PaperRecord(
        id="p-vis",
        title="Vision Benchmarks",
        abstract="The model obtains 86.4% accuracy on CIFAR-100 and achieves 52.3 mAP on COCO.",
    )
    extractor = BenchmarkExtractor()
    extracted = extractor.extract_reported_results(paper)

    cifar_items = [item for item in extracted if item[0].name == "CIFAR-100"]
    assert len(cifar_items) == 1
    assert cifar_items[0][3].metric_value == 86.4
    assert cifar_items[0][1].name == "Accuracy"

    coco_items = [item for item in extracted if item[0].name == "COCO"]
    assert len(coco_items) == 1
    assert coco_items[0][3].metric_value == 52.3
    assert coco_items[0][1].name == "mAP"
