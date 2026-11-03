"""
Unit and integration tests for SOTA Evaluator & Frontier Distinction Engine (scifi.literature.sota).
"""

from __future__ import annotations

import pytest

from scifi.literature.models import (
    BenchmarkRecord,
    BenchmarkResultRecord,
    EvaluationConditionRecord,
    EvaluationMetricRecord,
    PaperRecord,
)
from scifi.literature.sota import (
    PerformanceDelta,
    SotaEvaluationReport,
    SotaEvaluationResults,
    SotaEvaluator,
)


def test_sota_evaluator_distinguishes_leader_from_high_citation():
    """
    Distinguish low-citation actual SOTA leader from high-citation influential baselines.
    Paper A: Seminal, 5000 citations, score 78.0 (2017)
    Paper B: Frontier, 300 citations, score 84.0 (2022)
    Paper C: Recent SOTA, 15 citations, score 91.2 (2024)
    """
    p_a = PaperRecord(id="p-a", title="Seminal Transformer", year=2017, citation_count=5000)
    p_b = PaperRecord(id="p-b", title="Improved Attention", year=2022, citation_count=300)
    p_c = PaperRecord(id="p-c", title="Novel Architecture", year=2024, citation_count=15)

    metric = EvaluationMetricRecord(id="m-acc", name="Accuracy", goal="maximize", unit="%")
    results = [
        BenchmarkResultRecord(id="r1", paper_id="p-a", benchmark_id="bm-1", metric_id="m-acc", metric_value=78.0),
        BenchmarkResultRecord(id="r2", paper_id="p-b", benchmark_id="bm-1", metric_id="m-acc", metric_value=84.0),
        BenchmarkResultRecord(id="r3", paper_id="p-c", benchmark_id="bm-1", metric_id="m-acc", metric_value=91.2),
    ]

    evaluator = SotaEvaluator()
    report = evaluator.evaluate_sota_frontier([p_a, p_b, p_c], results, {"m-acc": metric})

    assert report.sota_leader_paper_id == "p-c"
    assert report.high_citation_frontier_paper_id == "p-b"
    assert report.best_metric_value == 91.2
    assert report.baseline_metric_value == 84.0

    delta = report.get_delta("p-c", "p-b")
    assert delta is not None
    assert delta.absolute_delta == pytest.approx(7.2)
    assert delta.is_improvement is True
    assert delta.relative_improvement_pct == pytest.approx(8.5714, rel=1e-3)

    delta_a = report.get_delta("p-c", "p-a")
    assert delta_a is not None
    assert delta_a.absolute_delta == pytest.approx(13.2)
    assert delta_a.is_improvement is True

    # Check that top result record has is_sota = True, others False
    r3 = next(r for r in results if r.id == "r3")
    assert r3.is_sota is True
    assert r3.rank == 1
    r2 = next(r for r in results if r.id == "r2")
    assert r2.is_sota is False
    assert r2.rank == 2


def test_two_paper_sota_leader_vs_high_citation_baseline():
    """
    Direct pair comparison: Low-citation SOTA leader (15 citations, 91.2%)
    vs high-citation baseline (5000 citations, 78.0%).
    """
    p_base = PaperRecord(id="p-base", title="Influential Baseline", year=2020, citation_count=5000)
    p_sota = PaperRecord(id="p-sota", title="Fresh SOTA Method", year=2024, citation_count=15)

    metric = EvaluationMetricRecord(id="m-acc", name="Accuracy", goal="maximize", unit="%")
    results = [
        BenchmarkResultRecord(id="r-base", paper_id="p-base", benchmark_id="bm-glue", metric_id="m-acc", metric_value=78.0),
        BenchmarkResultRecord(id="r-sota", paper_id="p-sota", benchmark_id="bm-glue", metric_id="m-acc", metric_value=91.2),
    ]

    evaluator = SotaEvaluator()
    reports = evaluator.evaluate_sota_frontier([p_base, p_sota], results, {"m-acc": metric})
    report = reports["bm-glue:m-acc"]

    assert report.sota_leader_paper_id == "p-sota"
    assert report.high_citation_frontier_paper_id == "p-base"
    assert report.best_metric_value == 91.2
    assert report.baseline_metric_value == 78.0

    delta = report.get_delta("p-sota", "p-base")
    assert delta is not None
    assert delta.absolute_delta == pytest.approx(13.2)
    assert delta.is_improvement is True


def test_sota_evaluator_minimization_goal():
    """
    Minimization metric goal: Latency, where 15ms beats 45ms.
    """
    p_fast = PaperRecord(id="p-fast", title="Lightning Model", year=2024, citation_count=25)
    p_slow = PaperRecord(id="p-slow", title="Heavyweight Model", year=2022, citation_count=800)
    p_mid = PaperRecord(id="p-mid", title="Standard Model", year=2023, citation_count=200)

    metric = EvaluationMetricRecord(id="m-lat", name="Latency", goal="minimize", unit="ms")
    results = [
        BenchmarkResultRecord(id="r-slow", paper_id="p-slow", benchmark_id="bm-lat", metric_id="m-lat", metric_value=45.0),
        BenchmarkResultRecord(id="r-fast", paper_id="p-fast", benchmark_id="bm-lat", metric_id="m-lat", metric_value=15.0),
        BenchmarkResultRecord(id="r-mid", paper_id="p-mid", benchmark_id="bm-lat", metric_id="m-lat", metric_value=30.0),
    ]

    evaluator = SotaEvaluator()
    report = evaluator.evaluate_sota_frontier([p_slow, p_fast, p_mid], results, {"m-lat": metric})

    assert report.sota_leader_paper_id == "p-fast"
    assert report.best_metric_value == 15.0

    # Delta against mid baseline (30ms -> 15ms is 50% improvement / reduction)
    delta_mid = report.get_delta("p-fast", "p-mid")
    assert delta_mid is not None
    assert delta_mid.absolute_delta == pytest.approx(15.0)
    assert delta_mid.is_improvement is True
    assert delta_mid.relative_improvement_pct == pytest.approx(50.0)

    # Delta against slow baseline (45ms -> 15ms is 66.67% improvement / reduction)
    delta_slow = report.get_delta("p-fast", "p-slow")
    assert delta_slow is not None
    assert delta_slow.absolute_delta == pytest.approx(30.0)
    assert delta_slow.is_improvement is True
    assert delta_slow.relative_improvement_pct == pytest.approx(66.6667, rel=1e-3)


def test_performance_delta_and_condition_mismatch():
    """
    Detect condition mismatch when evaluation setups differ (e.g. 0-shot vs 5-shot).
    """
    p_sota = PaperRecord(id="p-sota", title="Few-Shot Master", year=2024, citation_count=10)
    p_base1 = PaperRecord(id="p-base1", title="Zero-Shot Baseline", year=2023, citation_count=100)
    p_base2 = PaperRecord(id="p-base2", title="Few-Shot Baseline", year=2023, citation_count=90)

    cond_0shot = EvaluationConditionRecord(id="c-0shot", name="0-shot")
    cond_5shot = EvaluationConditionRecord(id="c-5shot", name="5-shot")
    metric = EvaluationMetricRecord(id="m-f1", name="F1", goal="maximize", unit="pts")

    results = [
        BenchmarkResultRecord(
            id="r-sota", paper_id="p-sota", benchmark_id="bm-qa", metric_id="m-f1",
            condition_id="c-5shot", metric_value=88.0,
        ),
        BenchmarkResultRecord(
            id="r-b1", paper_id="p-base1", benchmark_id="bm-qa", metric_id="m-f1",
            condition_id="c-0shot", metric_value=75.0,
        ),
        BenchmarkResultRecord(
            id="r-b2", paper_id="p-base2", benchmark_id="bm-qa", metric_id="m-f1",
            condition_id="c-5shot", metric_value=80.0,
        ),
    ]

    evaluator = SotaEvaluator()
    report = evaluator.evaluate_sota_frontier([p_sota, p_base1, p_base2], results, {"m-f1": metric})

    # Delta vs base1 (0-shot vs 5-shot) -> condition mismatch
    delta_b1 = report.get_delta("p-sota", "p-base1")
    assert delta_b1 is not None
    assert delta_b1.condition_mismatch is True
    assert delta_b1.sota_condition_id == "c-5shot"
    assert delta_b1.baseline_condition_id == "c-0shot"

    # Delta vs base2 (5-shot vs 5-shot) -> matching condition
    delta_b2 = report.get_delta("p-sota", "p-base2")
    assert delta_b2 is not None
    assert delta_b2.condition_mismatch is False
    assert delta_b2.sota_condition_id == "c-5shot"
    assert delta_b2.baseline_condition_id == "c-5shot"


def test_zero_baseline_relative_improvement():
    """
    Verify relative_improvement_pct is None when baseline value is 0.0.
    """
    p_sota = PaperRecord(id="p-sota", title="Working Model", year=2024)
    p_fail = PaperRecord(id="p-fail", title="Failing Model", year=2023)

    metric = EvaluationMetricRecord(id="m-pass", name="pass@1", goal="maximize", unit="%")
    results = [
        BenchmarkResultRecord(id="r-sota", paper_id="p-sota", benchmark_id="bm-code", metric_id="m-pass", metric_value=42.0),
        BenchmarkResultRecord(id="r-fail", paper_id="p-fail", benchmark_id="bm-code", metric_id="m-pass", metric_value=0.0),
    ]

    evaluator = SotaEvaluator()
    report = evaluator.evaluate_sota_frontier([p_sota, p_fail], results, {"m-pass": metric})
    delta = report.get_delta("p-sota", "p-fail")
    assert delta is not None
    assert delta.absolute_delta == 42.0
    assert delta.is_improvement is True
    assert delta.relative_improvement_pct is None


def test_assign_enriched_roles():
    """
    Verify canonical role assignment across topological depths:
    sota_leader, frontier (depth == max_depth > 0), foundational (depth == 0), intermediate.
    """
    p_foundational = PaperRecord(id="p-found", title="Foundational Root", year=2017)
    p_intermediate = PaperRecord(id="p-inter", title="Intermediate Step", year=2020)
    p_frontier = PaperRecord(id="p-front", title="Frontier Work", year=2023)
    p_sota = PaperRecord(id="p-sota", title="SOTA Leader", year=2024)

    depths = {
        "p-found": 0,
        "p-inter": 1,
        "p-front": 2,
        "p-sota": 2,
    }

    report = SotaEvaluationReport(
        benchmark_id="bm-eval",
        metric_id="m-score",
        sota_leader_paper_id="p-sota",
        high_citation_frontier_paper_id="p-front",
        best_metric_value=95.0,
        baseline_metric_value=85.0,
    )

    evaluator = SotaEvaluator()
    roles = evaluator.assign_enriched_roles(
        [p_foundational, p_intermediate, p_frontier, p_sota],
        depths,
        {"bm-eval:m-score": report},
    )

    assert roles["p-sota"] == "sota_leader"
    assert roles["p-front"] == "frontier"
    assert roles["p-inter"] == "intermediate"
    assert roles["p-found"] == "foundational"


def test_assign_enriched_roles_sota_leader_at_depth_zero():
    """
    If a foundational paper at depth 0 holds SOTA, its role is 'sota_leader'.
    """
    p_root_sota = PaperRecord(id="p-root", title="Unbeatable Classical Method", year=2015)
    p_recent = PaperRecord(id="p-rec", title="Recent Attempt", year=2024)

    depths = {"p-root": 0, "p-rec": 1}
    report = SotaEvaluationReport(
        benchmark_id="bm-bench",
        metric_id="m-acc",
        sota_leader_paper_id="p-root",
    )

    evaluator = SotaEvaluator()
    roles = evaluator.assign_enriched_roles([p_root_sota, p_recent], depths, {"bm-bench:m-acc": report})

    assert roles["p-root"] == "sota_leader"
    assert roles["p-rec"] == "frontier"


def test_multiple_benchmarks_and_metrics_grouping():
    """
    Verify grouping across multiple distinct benchmarks and metrics.
    """
    p1 = PaperRecord(id="p-1", title="Model Alpha", year=2024, citation_count=50)
    p2 = PaperRecord(id="p-2", title="Model Beta", year=2024, citation_count=40)

    m_acc = EvaluationMetricRecord(id="m-acc", name="Accuracy", goal="maximize", unit="%")
    m_lat = EvaluationMetricRecord(id="m-lat", name="Latency", goal="minimize", unit="ms")

    results = [
        # Benchmark 1, Metric Accuracy: p1 wins
        BenchmarkResultRecord(id="r1", paper_id="p-1", benchmark_id="bm-1", metric_id="m-acc", metric_value=90.0),
        BenchmarkResultRecord(id="r2", paper_id="p-2", benchmark_id="bm-1", metric_id="m-acc", metric_value=85.0),
        # Benchmark 1, Metric Latency: p2 wins (lower latency)
        BenchmarkResultRecord(id="r3", paper_id="p-1", benchmark_id="bm-1", metric_id="m-lat", metric_value=50.0),
        BenchmarkResultRecord(id="r4", paper_id="p-2", benchmark_id="bm-1", metric_id="m-lat", metric_value=20.0),
    ]

    evaluator = SotaEvaluator()
    reports = evaluator.evaluate_sota_frontier([p1, p2], results, {"m-acc": m_acc, "m-lat": m_lat})

    assert len(reports) == 2
    assert "bm-1:m-acc" in reports
    assert "bm-1:m-lat" in reports

    rep_acc = reports["bm-1:m-acc"]
    assert rep_acc.sota_leader_paper_id == "p-1"
    assert rep_acc.best_metric_value == 90.0

    rep_lat = reports["bm-1:m-lat"]
    assert rep_lat.sota_leader_paper_id == "p-2"
    assert rep_lat.best_metric_value == 20.0


def test_tie_breaking_behavior():
    """
    When scores are identical, tie is broken by year (more recent) then citations.
    """
    p_old = PaperRecord(id="p-old", title="Older Paper", year=2022, citation_count=100)
    p_new = PaperRecord(id="p-new", title="Newer Paper", year=2024, citation_count=10)

    metric = EvaluationMetricRecord(id="m-acc", name="Accuracy", goal="maximize", unit="%")
    results = [
        BenchmarkResultRecord(id="r-old", paper_id="p-old", benchmark_id="bm-tie", metric_id="m-acc", metric_value=90.0),
        BenchmarkResultRecord(id="r-new", paper_id="p-new", benchmark_id="bm-tie", metric_id="m-acc", metric_value=90.0),
    ]

    evaluator = SotaEvaluator()
    report = evaluator.evaluate_sota_frontier([p_old, p_new], results, {"m-acc": metric})

    assert report.sota_leader_paper_id == "p-new"
    assert report.best_metric_value == 90.0


def test_serialization_to_dict():
    """
    Verify to_dict on PerformanceDelta and SotaEvaluationReport.
    """
    delta = PerformanceDelta(
        sota_paper_id="p-sota",
        baseline_paper_id="p-base",
        benchmark_id="bm-1",
        metric_id="m-acc",
        sota_value=90.0,
        baseline_value=80.0,
        absolute_delta=10.0,
        relative_improvement_pct=12.5,
        is_improvement=True,
        condition_mismatch=False,
    )
    d_dict = delta.to_dict()
    assert d_dict["sota_paper_id"] == "p-sota"
    assert d_dict["absolute_delta"] == 10.0
    assert d_dict["relative_improvement_pct"] == 12.5

    report = SotaEvaluationReport(
        benchmark_id="bm-1",
        metric_id="m-acc",
        sota_leader_paper_id="p-sota",
        best_metric_value=90.0,
        deltas=[delta],
        paper_roles={"p-sota": "sota_leader", "p-base": "frontier"},
    )
    r_dict = report.to_dict()
    assert r_dict["benchmark_id"] == "bm-1"
    assert r_dict["sota_leader_paper_id"] == "p-sota"
    assert len(r_dict["deltas"]) == 1
    assert r_dict["deltas"][0]["sota_paper_id"] == "p-sota"
    assert r_dict["paper_roles"]["p-sota"] == "sota_leader"


def test_empty_results_and_missing_metrics():
    """
    Verify empty results list and missing metrics behavior.
    """
    evaluator = SotaEvaluator()
    reports = evaluator.evaluate_sota_frontier([], [], {})
    assert len(reports) == 0
    assert reports.sota_leader_paper_id is None
    assert reports.deltas == []

    # Metric not found in metrics dict falls back to default maximize
    p = PaperRecord(id="p-1", title="Model One", year=2024)
    r = BenchmarkResultRecord(id="r-1", paper_id="p-1", benchmark_id="bm-custom", metric_id="custom-metric", metric_value=99.0)
    reports2 = evaluator.evaluate_sota_frontier([p], [r], {})
    assert "bm-custom:custom-metric" in reports2
    assert reports2["bm-custom:custom-metric"].sota_leader_paper_id == "p-1"


def test_from_dict_roundtrip():
    """
    Verify from_dict reconstitutes objects correctly.
    """
    delta = PerformanceDelta(
        sota_paper_id="p-sota",
        baseline_paper_id="p-base",
        benchmark_id="bm-1",
        metric_id="m-acc",
        sota_value=90.0,
        baseline_value=80.0,
        absolute_delta=10.0,
        relative_improvement_pct=12.5,
        is_improvement=True,
        condition_mismatch=True,
        sota_condition_id="c-sota",
        baseline_condition_id="c-base",
    )
    d2 = PerformanceDelta.from_dict(delta.to_dict())
    assert d2.sota_paper_id == delta.sota_paper_id
    assert d2.condition_mismatch is True

    report = SotaEvaluationReport(
        benchmark_id="bm-1",
        metric_id="m-acc",
        sota_leader_paper_id="p-sota",
        high_citation_frontier_paper_id="p-base",
        best_metric_value=90.0,
        baseline_metric_value=80.0,
        deltas=[delta],
        paper_roles={"p-sota": "sota_leader"},
    )
    r2 = SotaEvaluationReport.from_dict(report.to_dict())
    assert r2.benchmark_id == report.benchmark_id
    assert len(r2.deltas) == 1
    assert r2.deltas[0].sota_paper_id == "p-sota"


def test_get_delta_single_argument_and_missing():
    """
    Verify get_delta works with baseline_id only or returns None if missing.
    """
    delta = PerformanceDelta(
        sota_paper_id="p-sota",
        baseline_paper_id="p-base",
        benchmark_id="bm-1",
        metric_id="m-acc",
        sota_value=90.0,
        baseline_value=80.0,
        absolute_delta=10.0,
    )
    report = SotaEvaluationReport(
        benchmark_id="bm-1",
        metric_id="m-acc",
        sota_leader_paper_id="p-sota",
        deltas=[delta],
    )
    # Single argument (baseline_paper_id)
    assert report.get_delta("p-base") == delta
    # Missing paper
    assert report.get_delta("p-nonexistent") is None

