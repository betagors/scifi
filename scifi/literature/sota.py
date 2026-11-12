"""
SOTA Evaluator & Frontier Distinction Engine.

Evaluates benchmark performance across graph papers, cleanly distinguishing
Most Influential Recent Research (high citation velocity) from Actual SOTA
(best verified benchmark metric), computing performance deltas (Δ_SOTA),
and assigning enriched node roles (sota_leader, frontier, foundational, intermediate).
"""

from __future__ import annotations

import dataclasses
import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Union

from scifi.literature.benchmarks import CANONICAL_METRICS
from scifi.literature.models import (
    BenchmarkRecord,
    BenchmarkResultRecord,
    EvaluationMetricRecord,
    PaperRecord,
)


@dataclass
class PerformanceDelta:
    """
    Empirical performance difference between SOTA leader and a baseline paper on a metric.
    """

    sota_paper_id: str
    baseline_paper_id: str
    benchmark_id: str
    metric_id: str
    sota_value: float
    baseline_value: float
    absolute_delta: float
    relative_improvement_pct: Optional[float] = None
    is_improvement: bool = True
    condition_mismatch: bool = False
    sota_condition_id: Optional[str] = None
    baseline_condition_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PerformanceDelta:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class SotaEvaluationReport:
    """
    Structured benchmark evaluation report comparing SOTA leader against baseline frontier.
    """

    benchmark_id: str
    metric_id: str
    sota_leader_paper_id: Optional[str] = None
    high_citation_frontier_paper_id: Optional[str] = None
    best_metric_value: Optional[float] = None
    baseline_metric_value: Optional[float] = None
    deltas: list[PerformanceDelta] = field(default_factory=list)
    paper_roles: dict[str, str] = field(default_factory=dict)

    def get_delta(
        self, sota_paper_id: str, baseline_paper_id: Optional[str] = None
    ) -> Optional[PerformanceDelta]:
        """
        Retrieve performance delta between SOTA paper and baseline paper.
        Supports both get_delta(sota_id, baseline_id) and get_delta(baseline_id).
        """
        if baseline_paper_id is None:
            baseline_paper_id = sota_paper_id
            sota_paper_id = self.sota_leader_paper_id or ""

        for d in self.deltas:
            if d.sota_paper_id == sota_paper_id and d.baseline_paper_id == baseline_paper_id:
                return d

        # Secondary match by baseline_paper_id only if sota_leader matches
        for d in self.deltas:
            if d.baseline_paper_id == baseline_paper_id:
                return d

        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "metric_id": self.metric_id,
            "sota_leader_paper_id": self.sota_leader_paper_id,
            "high_citation_frontier_paper_id": self.high_citation_frontier_paper_id,
            "best_metric_value": self.best_metric_value,
            "baseline_metric_value": self.baseline_metric_value,
            "deltas": [d.to_dict() for d in self.deltas],
            "paper_roles": dict(self.paper_roles),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SotaEvaluationReport:
        deltas = [
            PerformanceDelta.from_dict(d) if isinstance(d, dict) else d
            for d in data.get("deltas", [])
        ]
        return cls(
            benchmark_id=data["benchmark_id"],
            metric_id=data["metric_id"],
            sota_leader_paper_id=data.get("sota_leader_paper_id"),
            high_citation_frontier_paper_id=data.get("high_citation_frontier_paper_id"),
            best_metric_value=data.get("best_metric_value"),
            baseline_metric_value=data.get("baseline_metric_value"),
            deltas=deltas,
            paper_roles=dict(data.get("paper_roles", {})),
        )


class SotaEvaluationResults(dict[str, SotaEvaluationReport]):
    """
    Container mapping benchmark-metric keys to SotaEvaluationReport records.
    Provides transparent attribute delegation to the primary report for single-metric calls.
    """

    def __getitem__(self, key: Union[str, tuple[str, str]]) -> SotaEvaluationReport:
        if isinstance(key, tuple):
            key = f"{key[0]}:{key[1]}"
        if key in self:
            return super().__getitem__(key)
        # Search by benchmark_id if unique
        matches = [r for k, r in self.items() if r.benchmark_id == key or k.startswith(f"{key}:")]
        if len(matches) == 1:
            return matches[0]
        return super().__getitem__(key)

    def __getattr__(self, name: str) -> Any:
        if self:
            first = next(iter(self.values()))
            if hasattr(first, name):
                return getattr(first, name)
        if name in (
            "sota_leader_paper_id",
            "high_citation_frontier_paper_id",
            "best_metric_value",
            "baseline_metric_value",
            "deltas",
            "paper_roles",
        ):
            return None if "value" in name or "id" in name else ([] if name == "deltas" else {})
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


class SotaEvaluator:
    """
    Evaluator for goal-aware benchmark ranking, tie-breaking, delta calculation,
    and node role assignment.
    """

    def evaluate_sota_frontier(
        self,
        papers: list[PaperRecord],
        benchmark_results: list[BenchmarkResultRecord],
        metrics: dict[str, EvaluationMetricRecord],
        benchmarks: Optional[dict[str, BenchmarkRecord]] = None,
        depths: Optional[dict[str, int]] = None,
    ) -> SotaEvaluationResults:
        """
        Evaluate benchmark results grouped by (benchmark_id, metric_id).
        Ranks papers by metric goal (maximize vs minimize), marks top result as is_sota=True,
        distinguishes high-citation frontier baselines, and computes performance deltas.
        """
        paper_map = {p.id: p for p in papers}
        ref_year = max(
            (p.year for p in papers if p and p.year is not None),
            default=datetime.date.today().year,
        )

        groups: dict[tuple[str, str], list[BenchmarkResultRecord]] = defaultdict(list)
        for res in benchmark_results:
            groups[(res.benchmark_id, res.metric_id)].append(res)

        reports = SotaEvaluationResults()

        for (bm_id, metric_id), res_list in groups.items():
            metric = metrics.get(metric_id)
            if not metric:
                # Fallback search by id/name
                for m in metrics.values():
                    if m.id == metric_id or m.name == metric_id:
                        metric = m
                        break
            canonical_metric = CANONICAL_METRICS.get(metric_id) or CANONICAL_METRICS.get(
                metric_id.lower()
            )

            goal = "maximize"
            if metric and hasattr(metric, "goal") and metric.goal:
                goal = str(metric.goal).lower()
            elif canonical_metric and hasattr(canonical_metric, "goal") and canonical_metric.goal:
                goal = str(canonical_metric.goal).lower()

            def sort_key(r: BenchmarkResultRecord) -> tuple[float, int, float, int, str]:
                p = paper_map.get(r.paper_id)
                year = p.year if p and p.year is not None else 0
                growth = (
                    p.recent_citation_growth
                    if p and p.recent_citation_growth is not None
                    else 0.0
                )
                citations = p.citation_count if p and p.citation_count is not None else 0
                if goal == "minimize":
                    val_key = r.metric_value
                else:
                    val_key = -r.metric_value
                return (val_key, -year, -growth, -citations, r.id)

            sorted_results = sorted(res_list, key=sort_key)
            if not sorted_results:
                continue

            top_result = sorted_results[0]
            top_result.is_sota = True
            top_result.rank = 1

            for rank_idx, r in enumerate(sorted_results[1:], start=2):
                r.is_sota = False
                r.rank = rank_idx

            sota_leader_id = top_result.paper_id
            best_val = top_result.metric_value

            # Identify unique non-winning papers
            non_winning_pids = [
                r.paper_id for r in sorted_results if r.paper_id != sota_leader_id
            ]
            unique_non_winning_ids = list(dict.fromkeys(non_winning_pids))

            non_winning_papers = [
                paper_map.get(pid) or PaperRecord(id=pid, title=f"Paper {pid}")
                for pid in unique_non_winning_ids
            ]

            # Frontier distinction: prefer recent works (<= 3 years relative to corpus ref_year)
            recent_candidates = [
                p
                for p in non_winning_papers
                if p.year is not None and (ref_year - p.year) <= 3
            ]
            frontier_candidates = recent_candidates if recent_candidates else non_winning_papers

            def frontier_rank_key(p: PaperRecord) -> tuple[float, float, int, int]:
                pyear = p.year if p.year is not None else ref_year
                velocity = float(p.citation_count) / max(0.5, float(ref_year - pyear + 1))
                return (p.recent_citation_growth, velocity, p.citation_count, p.year or 0)

            high_citation_frontier_id: Optional[str] = None
            if frontier_candidates:
                ranked_frontiers = sorted(frontier_candidates, key=frontier_rank_key, reverse=True)
                high_citation_frontier_id = ranked_frontiers[0].id

            # Best baseline value from high citation frontier
            baseline_val: Optional[float] = None
            if high_citation_frontier_id:
                frontier_res = next(
                    (r for r in sorted_results if r.paper_id == high_citation_frontier_id),
                    None,
                )
                if frontier_res:
                    baseline_val = frontier_res.metric_value

            # Calculate PerformanceDeltas for each non-winning paper
            deltas: list[PerformanceDelta] = []
            for b_pid in unique_non_winning_ids:
                b_res = next(r for r in sorted_results if r.paper_id == b_pid)
                b_val = b_res.metric_value
                abs_delta = abs(best_val - b_val)

                if goal == "maximize":
                    is_imp = best_val > b_val
                    rel_imp = (
                        ((best_val - b_val) / abs(b_val)) * 100.0 if b_val != 0.0 else None
                    )
                else:
                    is_imp = best_val < b_val
                    rel_imp = (
                        ((b_val - best_val) / abs(b_val)) * 100.0 if b_val != 0.0 else None
                    )

                cond_mismatch = top_result.condition_id != b_res.condition_id

                delta = PerformanceDelta(
                    sota_paper_id=sota_leader_id,
                    baseline_paper_id=b_pid,
                    benchmark_id=bm_id,
                    metric_id=metric_id,
                    sota_value=best_val,
                    baseline_value=b_val,
                    absolute_delta=abs_delta,
                    relative_improvement_pct=rel_imp,
                    is_improvement=is_imp,
                    condition_mismatch=cond_mismatch,
                    sota_condition_id=top_result.condition_id,
                    baseline_condition_id=b_res.condition_id,
                )
                deltas.append(delta)

            report = SotaEvaluationReport(
                benchmark_id=bm_id,
                metric_id=metric_id,
                sota_leader_paper_id=sota_leader_id,
                high_citation_frontier_paper_id=high_citation_frontier_id,
                best_metric_value=best_val,
                baseline_metric_value=baseline_val,
                deltas=deltas,
            )

            # Assign roles for this report
            if depths:
                report.paper_roles = self.assign_enriched_roles(
                    papers, depths, {f"{bm_id}:{metric_id}": report}
                )
            else:
                report.paper_roles[sota_leader_id] = "sota_leader"
                if high_citation_frontier_id:
                    report.paper_roles[high_citation_frontier_id] = "frontier"
                for pid in unique_non_winning_ids:
                    if pid != high_citation_frontier_id:
                        report.paper_roles[pid] = "baseline"

            reports[f"{bm_id}:{metric_id}"] = report

        return reports

    def assign_enriched_roles(
        self,
        papers: list[PaperRecord],
        depths: dict[str, int],
        reports: Union[
            dict[str, SotaEvaluationReport],
            Iterable[SotaEvaluationReport],
            SotaEvaluationReport,
        ],
    ) -> dict[str, str]:
        """
        Assign canonical enriched node roles:
        - 'sota_leader': Paper holds verified SOTA on at least one benchmark.
        - 'frontier': Depth is max_depth (> 0).
        - 'foundational': Depth is 0.
        - 'intermediate': All other topological depths.
        """
        if isinstance(reports, SotaEvaluationReport):
            report_list = [reports]
        elif isinstance(reports, dict):
            report_list = list(reports.values())
        elif isinstance(reports, Iterable):
            report_list = list(reports)
        else:
            report_list = []

        sota_leader_ids: set[str] = set()
        for rep in report_list:
            leader_id = getattr(rep, "sota_leader_paper_id", None)
            if leader_id:
                sota_leader_ids.add(str(leader_id))

        max_depth = max(depths.values()) if depths else 0
        roles: dict[str, str] = {}

        for p in papers:
            if p.id in sota_leader_ids:
                roles[p.id] = "sota_leader"
            else:
                d = depths.get(p.id, 0)
                if d == max_depth and max_depth > 0:
                    roles[p.id] = "frontier"
                elif d == 0:
                    roles[p.id] = "foundational"
                else:
                    roles[p.id] = "intermediate"

        return roles


__all__ = [
    "PerformanceDelta",
    "SotaEvaluationReport",
    "SotaEvaluationResults",
    "SotaEvaluator",
]
