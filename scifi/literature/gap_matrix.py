"""
Cross-Paper Comparison Matrix & Structural Gap Synthesis Engine.

Synthesizes per-paper gaps, benchmarks, and knowledge-graph facts into a
cross-paper comparison matrix and surfaces structural research gaps:
1. Unexplored Method x Benchmark combinations (missing matrix cells).
2. Shared unrelaxed assumptions across multiple papers.
3. Disputed / contradictory empirical or theoretical claims.
4. Evaluation blind spots where recent frontier papers omit established benchmarks.
"""

from __future__ import annotations

import dataclasses
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from scifi.literature.gaps import _extract_key_tokens
from scifi.literature.models import (
    BenchmarkRecord,
    BenchmarkResultRecord,
    PaperGapRecord,
    PaperRecord,
)


@dataclass
class PaperMatrixRow:
    paper_id: str
    title: str
    year: int | None
    methods: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    benchmarks: list[str] = field(default_factory=list)
    gap_counts: dict[str, int] = field(default_factory=dict)
    corroborated_gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class StructuralGap:
    id: str
    structural_type: (
        str  # unexplored_combination | shared_unrelaxed_assumption | contradictory_evidence | evaluation_blind_spot
    )
    summary: str
    supporting_paper_ids: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    priority_score: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class GapSynthesisReport:
    rows: list[PaperMatrixRow] = field(default_factory=list)
    structural_gaps: list[StructuralGap] = field(default_factory=list)
    coverage_matrix: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_count": len(self.rows),
            "structural_gap_count": len(self.structural_gaps),
            "rows": [r.to_dict() for r in self.rows],
            "structural_gaps": [g.to_dict() for g in self.structural_gaps],
            "coverage_matrix": self.coverage_matrix,
        }

    def to_markdown(self) -> str:
        lines = ["## Cross-Paper Gap Synthesis Matrix", ""]
        if self.rows:
            lines.append("| Paper | Year | Methods | Benchmarks | Assumptions / Gaps |")
            lines.append("| --- | --- | --- | --- | --- |")
            for r in self.rows:
                methods_s = ", ".join(r.methods[:3]) or "-"
                bench_s = ", ".join(r.benchmarks[:3]) or "-"
                gaps_s = ", ".join(f"{k}:{v}" for k, v in sorted(r.gap_counts.items())) or "-"
                title_short = (r.title[:48] + "...") if len(r.title) > 51 else r.title
                lines.append(f"| {title_short} | {r.year or '-'} | {methods_s} | {bench_s} | {gaps_s} |")
            lines.append("")

        lines.append("### Structural Research Gaps")
        if not self.structural_gaps:
            lines.append("No structural cross-paper gaps detected.")
        else:
            for g in self.structural_gaps:
                lines.append(
                    f"- **[{g.structural_type}]** (score={g.priority_score:.2f}) {g.summary} "
                    f"(papers: {', '.join(g.supporting_paper_ids[:5])})"
                )
        return "\n".join(lines)


class GapMatrixBuilder:
    """Builds a cross-paper matrix and synthesizes structural research gaps."""

    def build(
        self,
        papers: list[PaperRecord],
        gaps: list[PaperGapRecord] | None = None,
        benchmarks: list[BenchmarkRecord] | None = None,
        benchmark_results: list[BenchmarkResultRecord] | None = None,
        paper_methods: dict[str, list[str]] | None = None,
        paper_assumptions: dict[str, list[str]] | None = None,
    ) -> GapSynthesisReport:
        gaps = gaps or []
        benchmarks = benchmarks or []
        benchmark_results = benchmark_results or []
        paper_methods = paper_methods or {}
        paper_assumptions = paper_assumptions or {}

        bench_names = {b.id: b.name for b in benchmarks}
        gaps_by_paper: dict[str, list[PaperGapRecord]] = defaultdict(list)
        for g in gaps:
            gaps_by_paper[g.paper_id].append(g)

        benches_by_paper: dict[str, set[str]] = defaultdict(set)
        for br in benchmark_results:
            b_label = bench_names.get(br.benchmark_id, br.benchmark_id)
            benches_by_paper[br.paper_id].add(b_label)

        rows: list[PaperMatrixRow] = []
        # method -> benchmark -> list[paper_id]
        coverage_matrix: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        all_methods: set[str] = set()
        all_benchmarks: set[str] = set()

        for p in papers:
            p_gaps = gaps_by_paper.get(p.id, [])
            p_methods = sorted(set(paper_methods.get(p.id, [])))
            p_benches = sorted(benches_by_paper.get(p.id, set()))
            p_assumptions = list(paper_assumptions.get(p.id, []))

            for g in p_gaps:
                if g.gap_type == "unstated_assumption" and g.claim_summary not in p_assumptions:
                    p_assumptions.append(g.claim_summary)

            counts = dict(Counter(g.gap_type for g in p_gaps))
            corroborated = [
                g.claim_summary for g in p_gaps if g.verification_status == "corroborated" or g.corroborating_count > 0
            ]

            rows.append(
                PaperMatrixRow(
                    paper_id=p.id,
                    title=p.title,
                    year=p.year,
                    methods=p_methods,
                    assumptions=p_assumptions,
                    benchmarks=p_benches,
                    gap_counts=counts,
                    corroborated_gaps=corroborated,
                )
            )

            for m in p_methods:
                all_methods.add(m)
                for b in p_benches:
                    all_benchmarks.add(b)
                    if p.id not in coverage_matrix[m][b]:
                        coverage_matrix[m][b].append(p.id)

        structural_gaps: list[StructuralGap] = []
        sg_idx = 0

        # 1. Unexplored Method x Benchmark combinations
        for m in sorted(all_methods):
            for b in sorted(all_benchmarks):
                if not coverage_matrix.get(m, {}).get(b):
                    sg_idx += 1
                    structural_gaps.append(
                        StructuralGap(
                            id=f"sg-{sg_idx}",
                            structural_type="unexplored_combination",
                            summary=f"Method '{m}' has not been evaluated on benchmark '{b}' in the corpus.",
                            supporting_paper_ids=[r.paper_id for r in rows if m in r.methods or b in r.benchmarks],
                            details={"method": m, "benchmark": b},
                            priority_score=0.75,
                        )
                    )

        # 2. Shared unrelaxed assumptions across >= 2 papers
        assumption_clusters: list[tuple[set[str], str, list[str]]] = []
        for r in rows:
            for a_text in r.assumptions:
                tokens = _extract_key_tokens(a_text)
                if len(tokens) < 2:
                    continue
                placed = False
                for c_tokens, _rep, c_papers in assumption_clusters:
                    union_len = len(c_tokens | tokens)
                    if union_len and len(c_tokens & tokens) / union_len >= 0.45:
                        c_tokens |= tokens
                        if r.paper_id not in c_papers:
                            c_papers.append(r.paper_id)
                        placed = True
                        break
                if not placed:
                    assumption_clusters.append((set(tokens), a_text, [r.paper_id]))

        for c_tokens, rep_text, c_papers in assumption_clusters:
            if len(c_papers) >= 2:
                sg_idx += 1
                structural_gaps.append(
                    StructuralGap(
                        id=f"sg-{sg_idx}",
                        structural_type="shared_unrelaxed_assumption",
                        summary=f"Shared assumption across {len(c_papers)} papers: {rep_text}",
                        supporting_paper_ids=c_papers,
                        details={"shared_tokens": sorted(c_tokens)[:10]},
                        priority_score=min(0.95, 0.65 + 0.08 * len(c_papers)),
                    )
                )

        # 3. Disputed / contradictory claims
        for g in gaps:
            if g.verification_status == "disputed" or g.contradicting_count > 0:
                sg_idx += 1
                structural_gaps.append(
                    StructuralGap(
                        id=f"sg-{sg_idx}",
                        structural_type="contradictory_evidence",
                        summary=f"Disputed finding on {g.paper_id}: {g.claim_summary}",
                        supporting_paper_ids=[g.paper_id],
                        details={
                            "gap_id": g.id,
                            "gap_type": g.gap_type,
                            "contradicting_count": g.contradicting_count,
                        },
                        priority_score=0.90,
                    )
                )

        # 4. Evaluation blind spots (benchmarks used by older papers omitted by recent frontier)
        dated_rows = [r for r in rows if r.year is not None]
        if len(dated_rows) >= 3:
            years_sorted = sorted(r.year for r in dated_rows if r.year is not None)
            cutoff_year = years_sorted[len(years_sorted) // 2]
            older_benches = Counter(
                b for r in dated_rows if r.year is not None and r.year < cutoff_year for b in r.benchmarks
            )
            newer_rows = [r for r in dated_rows if r.year is not None and r.year >= cutoff_year]
            newer_benches = {b for r in newer_rows for b in r.benchmarks}
            for b, count in older_benches.items():
                if count >= 2 and b not in newer_benches and newer_rows:
                    sg_idx += 1
                    structural_gaps.append(
                        StructuralGap(
                            id=f"sg-{sg_idx}",
                            structural_type="evaluation_blind_spot",
                            summary=f"Benchmark '{b}' was used in {count} earlier papers (<{cutoff_year}) but omitted in all {len(newer_rows)} recent papers.",
                            supporting_paper_ids=[r.paper_id for r in newer_rows],
                            details={"benchmark": b, "cutoff_year": cutoff_year, "prior_count": count},
                            priority_score=0.70,
                        )
                    )

        structural_gaps.sort(key=lambda g: g.priority_score, reverse=True)
        plain_matrix = {m: dict(b_map) for m, b_map in coverage_matrix.items()}
        return GapSynthesisReport(rows=rows, structural_gaps=structural_gaps, coverage_matrix=plain_matrix)
