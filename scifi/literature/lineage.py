"""
Multi-signal lineage traversal, cycle detection, and topological depth engine.
Discovers seminal foundations, intermediate iterations, and recent frontier papers
from a query or seed paper, detects and rectifies apparent citation cycles, computes
intellectual topological depths, and populates the graph-scoped SQLite knowledge store.
"""

from __future__ import annotations

import datetime
import math
import re
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from scifi.literature.benchmarks import BenchmarkExtractor
from scifi.literature.gaps import GapExtractor
from scifi.literature.sota import SotaEvaluator
from scifi.literature.models import (
    CitationContextRecord,
    CitationRecord,
    EvidenceRecord,
    PaperGapRecord,
    PaperRecord,
)
from scifi.literature.resolver import PaperResolver, clean_arxiv_id, clean_doi
from scifi.literature.semantic_scholar import SemanticScholarClient
from scifi.literature.store import LiteratureStore


def _extract_external_id_for_s2(paper: PaperRecord) -> Optional[str]:
    """
    Find best external identifier (DOI or arXiv ID) for Semantic Scholar citation context lookup.
    """
    # 1. Check identifiers list
    for ident in paper.identifiers:
        prov = (ident.provider or "").lower()
        if prov == "doi" and ident.external_id:
            c = clean_doi(ident.external_id)
            if c:
                return f"DOI:{c}"
        elif prov == "arxiv" and ident.external_id:
            c = clean_arxiv_id(ident.external_id)
            if c:
                return f"ARXIV:{c}"

    # 2. Check versions for DOI
    for v in paper.versions:
        if v.doi:
            c = clean_doi(v.doi)
            if c:
                return f"DOI:{c}"

    # 3. Check paper.id directly
    c_doi = clean_doi(paper.id)
    if c_doi and ("10." in c_doi or "doi.org" in paper.id.lower()):
        return f"DOI:{c_doi}"
    c_arx = clean_arxiv_id(paper.id)
    if c_arx and (paper.id.lower().startswith("arxiv:") or re.match(r"^\d{4}\.\d{4,5}(?:v\d+)?$", paper.id)):
        return f"ARXIV:{c_arx}"

    return None


def _extract_year_and_date(paper: PaperRecord | None) -> Tuple[int, str]:
    """
    Extract best available publication year and ISO date string from a PaperRecord.
    Returns (year, date_string). Defaults to (9999, "") if unknown.
    """
    if paper is None:
        return (9999, "")
    year = paper.year
    date_str = (paper.publication_date or "").strip()
    if year is None and date_str:
        m = re.search(r"\b(19\d\d|20\d\d)\b", date_str)
        if m:
            year = int(m.group(1))
    if year is None:
        year = 9999
    return (year, date_str)


class LineageCrawler:
    """
    Lineage traversal crawler implementing multi-signal ranking, cycle detection
    via publication year hierarchy rectification, topological depth assignment,
    and graph-scoped persistence.
    """

    def __init__(
        self,
        resolver: Optional[PaperResolver] = None,
        store: Optional[LiteratureStore] = None,
        max_request_budget: int = 25,
        s2_client: Optional[SemanticScholarClient] = None,
        gap_extractor: Optional[GapExtractor] = None,
        benchmark_extractor: Optional[BenchmarkExtractor] = None,
        sota_evaluator: Optional[SotaEvaluator] = None,
    ) -> None:
        self.resolver = resolver or PaperResolver()
        self.store = store
        self.max_request_budget = max_request_budget
        self.request_count = 0
        self.s2_client = s2_client
        self.gap_extractor = gap_extractor
        self.benchmark_extractor = benchmark_extractor
        self.sota_evaluator = sota_evaluator

    def _can_request(self) -> bool:
        """Check whether the crawler has remaining request budget."""
        return self.request_count < self.max_request_budget

    def _record_request(self) -> bool:
        """Record an API request; return True if within budget, False if exhausted."""
        if self.request_count >= self.max_request_budget:
            return False
        self.request_count += 1
        return True

    def _get_openalex_id(self, paper: PaperRecord) -> Optional[str]:
        """Extract OpenAlex work ID from a paper's identifiers or canonical id."""
        for ident in paper.identifiers:
            if ident.provider.lower() == "openalex" and ident.external_id:
                return ident.external_id.strip().rstrip("/").split("/")[-1]
        clean_id = paper.id.strip().rstrip("/").split("/")[-1]
        if clean_id.upper().startswith("W") and clean_id[1:].isdigit():
            return clean_id
        return None

    def resolve_seed(self, query: str | PaperRecord) -> Optional[PaperRecord]:
        """
        Resolve a seed paper from a query string (title, DOI, arXiv ID, OpenAlex ID)
        or pass through if already a PaperRecord.
        """
        if isinstance(query, PaperRecord):
            return query
        if not isinstance(query, str):
            return None

        clean_q = query.strip()
        if not clean_q:
            return None

        # 1. Check OpenAlex ID
        openalex_match = re.match(r"^(?:https?://openalex\.org/)?(W\d+)$", clean_q, re.IGNORECASE)
        if openalex_match:
            if not self._record_request():
                return None
            if hasattr(self.resolver, "resolve_by_openalex_id"):
                p = self.resolver.resolve_by_openalex_id(openalex_match.group(1))
                if p:
                    return p

        # 2. Check DOI
        clean_d = clean_doi(clean_q)
        if clean_d and ("10." in clean_d or "doi.org" in clean_q.lower()):
            if not self._record_request():
                return None
            if hasattr(self.resolver, "resolve_by_doi"):
                p = self.resolver.resolve_by_doi(clean_d)
                if p:
                    return p

        # 3. Check arXiv ID
        if (
            clean_q.lower().startswith("arxiv:")
            or "arxiv.org" in clean_q.lower()
            or re.match(r"^\d{4}\.\d{4,5}(?:v\d+)?$", clean_q)
        ):
            clean_arx = clean_arxiv_id(clean_q)
            if clean_arx:
                if not self._record_request():
                    return None
                if hasattr(self.resolver, "resolve_by_arxiv_id"):
                    p = self.resolver.resolve_by_arxiv_id(clean_arx)
                    if p:
                        return p

        # 4. Resolve by title
        if not self._record_request():
            return None
        return self.resolver.resolve_by_title(clean_q)

    def rank_foundations(
        self, candidate_refs: List[PaperRecord], top_k: int = 5
    ) -> List[PaperRecord]:
        """
        Backward (Foundations) ranking:
        Seed references ranked by composite weight: log(1 + C_global) + 2.0 * I_influential.
        Select top_k per expansion.
        """
        scored: List[Tuple[float, PaperRecord]] = []
        for p in candidate_refs:
            c_global = max(0, p.citation_count)
            is_influential = 1.0 if (
                p.influential_citation_count > 0 or getattr(p, "is_influential", False)
            ) else 0.0
            weight = math.log1p(c_global) + (2.0 * is_influential)
            scored.append((weight, p))

        # Sort descending by composite weight, tie-breaking by year and id
        scored.sort(key=lambda item: (item[0], item[1].year or 0, item[1].id), reverse=True)
        return [p for _, p in scored[:top_k]]

    def rank_frontier(
        self, candidate_citing: List[PaperRecord], top_k: int = 5
    ) -> List[PaperRecord]:
        """
        Forward (Frontier) ranking:
        Papers citing seed ranked by annualized velocity: C / max(0.5, CurrentYear - Year + 1).
        Filter to recent works (<= 3 years old). Select top_k per expansion.
        """
        cur_year = datetime.date.today().year
        scored: List[Tuple[float, PaperRecord]] = []

        for p in candidate_citing:
            year, _ = _extract_year_and_date(p)
            if year == 9999:
                year = cur_year

            age = cur_year - year
            if age > 3:
                # Exclude works older than 3 years from frontier
                continue

            c = max(0, p.citation_count)
            velocity = c / max(0.5, float(cur_year - year + 1))
            scored.append((velocity, p))

        # Sort descending by velocity, tie-breaking by year and citation_count
        scored.sort(key=lambda item: (item[0], item[1].year or 0, item[1].citation_count), reverse=True)
        return [p for _, p in scored[:top_k]]

    def detect_and_rectify_cycles(
        self, papers: List[PaperRecord], citations: List[CitationRecord]
    ) -> List[CitationRecord]:
        """
        Detect cycles in the directed citation network and rectify them by
        resolving circular citations using publication year/date hierarchy:
        removes the chronological violator (the edge where an older paper appears
        to cite a strictly newer paper).
        """
        paper_map: Dict[str, PaperRecord] = {p.id: p for p in papers}

        # Deduplicate incoming citations
        current_citations: List[CitationRecord] = []
        seen_edges: Set[Tuple[str, str]] = set()
        for c in citations:
            edge = (c.source_paper_id, c.target_paper_id)
            if edge not in seen_edges and c.source_paper_id != c.target_paper_id:
                seen_edges.add(edge)
                current_citations.append(c)

        def _find_cycle(edges: List[CitationRecord]) -> Optional[List[Tuple[str, str]]]:
            """DFS-based cycle finder returning list of edges in the first found cycle."""
            adj: Dict[str, List[str]] = {}
            for edge_record in edges:
                adj.setdefault(edge_record.source_paper_id, []).append(edge_record.target_paper_id)

            # 0: unvisited, 1: visiting, 2: visited
            state: Dict[str, int] = {}
            nodes = list(adj.keys())

            for start_node in nodes:
                if state.get(start_node, 0) != 0:
                    continue

                stack: List[Tuple[str, int]] = [(start_node, 0)]
                path: List[str] = [start_node]
                state[start_node] = 1

                while stack:
                    u, idx = stack[-1]
                    neighbors = adj.get(u, [])
                    if idx < len(neighbors):
                        v = neighbors[idx]
                        stack[-1] = (u, idx + 1)
                        v_state = state.get(v, 0)
                        if v_state == 1:
                            # Cycle detected
                            cycle_nodes = path[path.index(v) :]
                            cycle_edges = [
                                (cycle_nodes[i], cycle_nodes[i + 1])
                                for i in range(len(cycle_nodes) - 1)
                            ]
                            cycle_edges.append((cycle_nodes[-1], v))
                            return cycle_edges
                        elif v_state == 0:
                            state[v] = 1
                            path.append(v)
                            stack.append((v, 0))
                    else:
                        state[u] = 2
                        path.pop()
                        stack.pop()
            return None

        while True:
            cycle = _find_cycle(current_citations)
            if not cycle:
                break

            # Find the chronological violator in the detected cycle
            # For edge (u, v): u is citing v.
            # Normal causality: year(u) >= year(v).
            # Violator: year(u) < year(v) (older paper citing strictly newer paper).
            worst_edge: Optional[Tuple[str, str]] = None
            max_violation = -float("inf")

            for u, v in cycle:
                p_u = paper_map.get(u)
                p_v = paper_map.get(v)
                y_u, d_u = _extract_year_and_date(p_u)
                y_v, d_v = _extract_year_and_date(p_v)

                # Positive violation means u is strictly older than v (u was published before v existed)
                violation_score = (y_v - y_u) * 1000.0
                if d_u and d_v and d_u < d_v:
                    violation_score += 1.0

                if violation_score > max_violation:
                    max_violation = violation_score
                    worst_edge = (u, v)

            if not worst_edge:
                worst_edge = cycle[0]

            # Remove the chronological violator edge from current citations
            current_citations = [
                c
                for c in current_citations
                if not (c.source_paper_id == worst_edge[0] and c.target_paper_id == worst_edge[1])
            ]

        return current_citations

    def compute_topological_depths(
        self, papers: List[PaperRecord], citations: List[CitationRecord]
    ) -> Dict[str, int]:
        """
        Compute integer topological depths: 0 <= depth <= D.
        Visual and intellectual lineage flows from Roots/Foundations (depth 0)
        -> Intermediate milestones -> Current Frontier (depth D).
        In citation terms: Foundational papers are cited by others; Frontier papers cite earlier work.
        """
        rectified_citations = self.detect_and_rectify_cycles(papers, citations)

        paper_ids = {p.id for p in papers}
        for c in rectified_citations:
            paper_ids.add(c.source_paper_id)
            paper_ids.add(c.target_paper_id)

        # Lineage dependency: source cites target, so target (foundation) is predecessor of source (citing)
        predecessors: Dict[str, List[str]] = {pid: [] for pid in paper_ids}
        for c in rectified_citations:
            if c.source_paper_id in paper_ids and c.target_paper_id in paper_ids:
                predecessors[c.source_paper_id].append(c.target_paper_id)

        depths: Dict[str, int] = {}
        visiting: Set[str] = set()

        def _calc_depth(node: str) -> int:
            if node in depths:
                return depths[node]
            if node in visiting:
                return 0
            visiting.add(node)
            preds = predecessors.get(node, [])
            if not preds:
                d = 0
            else:
                d = 1 + max(_calc_depth(p) for p in preds)
            visiting.remove(node)
            depths[node] = d
            return d

        for pid in paper_ids:
            _calc_depth(pid)

        return depths

    def crawl_lineage(
        self,
        query: str | PaperRecord,
        depth: int = 2,
        max_papers: int = 25,
        graph_id: Optional[str] = None,
        extract_gaps: bool = True,
        extract_benchmarks: bool = True,
    ) -> Tuple[str, List[PaperRecord], List[CitationRecord]]:
        """
        Execute multi-signal lineage crawl starting from query or seed paper:
        - Expands backward (foundations) and forward (frontier)
        - Enforces max_request_budget
        - Detects and rectifies citation cycles
        - Computes topological depths
        - Automatically persists to LiteratureStore if configured.
        """
        self.request_count = 0
        assigned_graph_id = graph_id or f"graph-{uuid.uuid4().hex[:12]}"

        seed = self.resolve_seed(query)
        if not seed:
            return (assigned_graph_id, [], [])

        discovered_papers: Dict[str, PaperRecord] = {seed.id: seed}
        node_roles: Dict[str, str] = {seed.id: "seed"}
        citations: List[CitationRecord] = []
        seen_citations: Set[Tuple[str, str]] = set()

        def _add_citation(src: str, tgt: str, influential: bool = False) -> None:
            if src == tgt:
                return
            edge = (src, tgt)
            if edge not in seen_citations:
                seen_citations.add(edge)
                citations.append(
                    CitationRecord(
                        source_paper_id=src,
                        target_paper_id=tgt,
                        is_influential=influential,
                    )
                )

        current_frontier = [seed]
        current_foundations = [seed]

        for current_hop in range(1, depth + 1):
            if len(discovered_papers) >= max_papers or not self._can_request():
                break

            next_foundations: List[PaperRecord] = []
            next_frontier: List[PaperRecord] = []

            # 1. Expand Foundations Backward
            for p in current_foundations:
                if len(discovered_papers) >= max_papers or not self._can_request():
                    break
                work_id = self._get_openalex_id(p) or p.id
                if not self._record_request():
                    break

                try:
                    raw_refs = self.resolver.resolve_references(work_id, limit=max_papers)
                except Exception:
                    raw_refs = []

                ranked_refs = self.rank_foundations(raw_refs, top_k=5)
                for ref in ranked_refs:
                    _add_citation(p.id, ref.id, influential=(ref.influential_citation_count > 0))
                    if ref.id not in discovered_papers:
                        if len(discovered_papers) >= max_papers:
                            break
                        discovered_papers[ref.id] = ref
                        node_roles[ref.id] = "foundation"
                        next_foundations.append(ref)

            # 2. Expand Frontier Forward
            for p in current_frontier:
                if len(discovered_papers) >= max_papers or not self._can_request():
                    break
                work_id = self._get_openalex_id(p) or p.id
                if not self._record_request():
                    break

                try:
                    raw_cits = self.resolver.resolve_citations(work_id, limit=max_papers)
                except Exception:
                    raw_cits = []

                ranked_cits = self.rank_frontier(raw_cits, top_k=5)
                for cit in ranked_cits:
                    _add_citation(cit.id, p.id, influential=(cit.influential_citation_count > 0))
                    if cit.id not in discovered_papers:
                        if len(discovered_papers) >= max_papers:
                            break
                        discovered_papers[cit.id] = cit
                        node_roles[cit.id] = "frontier"
                        next_frontier.append(cit)

            current_foundations = next_foundations
            current_frontier = next_frontier

        # Rectify cycles
        paper_list = list(discovered_papers.values())
        rectified_citations = self.detect_and_rectify_cycles(paper_list, citations)

        # Compute topological depths
        topological_depths = self.compute_topological_depths(paper_list, rectified_citations)

        # Persist to LiteratureStore if available
        if self.store is not None:
            self.store.create_or_get_graph(
                graph_id=assigned_graph_id,
                title=seed.title,
                seed_paper_id=seed.id,
            )
            for p in paper_list:
                role = node_roles.get(p.id, "intermediate")
                d = topological_depths.get(p.id, 0)
                self.store.save_paper(
                    paper=p,
                    graph_id=assigned_graph_id,
                    node_role=role,
                    topological_depth=d,
                )
            for c in rectified_citations:
                self.store.save_citation(c)

            if extract_gaps:
                s2 = self.s2_client or SemanticScholarClient()
                extractor = self.gap_extractor or GapExtractor()

                raw_gaps: List[Tuple[EvidenceRecord, PaperGapRecord]] = []

                for p in paper_list:
                    # 1. Extract self-reported abstract limitations
                    try:
                        abstract_gaps = extractor.extract_abstract_gaps(p)
                        raw_gaps.extend(abstract_gaps)
                    except Exception:
                        pass

                    # 2. Extract citation context limitations via S2
                    ext_id = _extract_external_id_for_s2(p)
                    if ext_id:
                        contexts: List[CitationContextRecord] = []
                        try:
                            fetch_fn = (
                                getattr(s2, "fetch_citation_contexts", None)
                                or getattr(s2, "get_paper_citations_with_contexts", None)
                            )
                            if fetch_fn:
                                contexts = fetch_fn(ext_id) or []
                        except Exception:
                            contexts = []

                        for ctx in contexts:
                            try:
                                self.store.save_citation_context(ctx)
                            except Exception:
                                pass

                        if contexts:
                            try:
                                ctx_gaps = extractor.extract_citation_context_gaps(p, contexts)
                                raw_gaps.extend(ctx_gaps)
                            except Exception:
                                pass

                # 3. Corroborate findings across papers
                try:
                    corroborated_gaps = extractor.corroborate_gaps(raw_gaps)
                except Exception:
                    corroborated_gaps = raw_gaps

                # 4. Persist evidence and gaps to store
                for ev, gap in corroborated_gaps:
                    try:
                        self.store.save_evidence(ev)
                        self.store.save_paper_gap(gap)
                    except Exception:
                        pass

            if extract_benchmarks:
                b_extractor = self.benchmark_extractor or BenchmarkExtractor()
                s_evaluator = self.sota_evaluator or SotaEvaluator()

                extracted_items: list[Any] = []
                for p in paper_list:
                    try:
                        extracted = b_extractor.extract_reported_results(p)
                        extracted_items.extend(extracted)
                    except Exception:
                        pass

                for bm, metric, cond, res, ev in extracted_items:
                    try:
                        self.store.save_benchmark(bm)
                        self.store.save_evaluation_metric(metric)
                        if cond:
                            self.store.save_evaluation_condition(cond)
                        if ev:
                            self.store.save_evidence(ev)
                        self.store.save_benchmark_result(res)
                    except Exception:
                        pass

                try:
                    graph_results = self.store.get_graph_benchmark_results(assigned_graph_id)
                    all_results = [r for rlist in graph_results.values() for r in rlist]
                    graph_metrics = self.store.get_graph_metrics(assigned_graph_id)
                    graph_benchmarks = self.store.get_graph_benchmarks(assigned_graph_id)

                    if all_results:
                        sota_reports = s_evaluator.evaluate_sota_frontier(
                            papers=paper_list,
                            benchmark_results=all_results,
                            metrics=graph_metrics,
                            benchmarks=graph_benchmarks,
                            depths=topological_depths,
                        )
                        for r in all_results:
                            try:
                                self.store.save_benchmark_result(r)
                            except Exception:
                                pass

                        enriched_roles = s_evaluator.assign_enriched_roles(
                            papers=paper_list,
                            depths=topological_depths,
                            reports=sota_reports,
                        )
                        for p in paper_list:
                            role = enriched_roles.get(p.id, node_roles.get(p.id, "intermediate"))
                            d = topological_depths.get(p.id, 0)
                            try:
                                self.store.save_paper(
                                    paper=p,
                                    graph_id=assigned_graph_id,
                                    node_role=role,
                                    topological_depth=d,
                                )
                            except Exception:
                                pass
                except Exception:
                    pass

        return (assigned_graph_id, paper_list, rectified_citations)


__all__ = ["LineageCrawler"]
