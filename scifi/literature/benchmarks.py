"""
Benchmark Ingestion and Pattern Mining Engine.
Extracts empirical benchmark evaluations, metrics, conditions, and reported performance scores
from scientific paper abstracts and textual evidence.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Optional

from scifi.literature.models import (
    BenchmarkRecord,
    BenchmarkResultRecord,
    EvaluationConditionRecord,
    EvaluationMetricRecord,
    EvidenceRecord,
    PaperRecord,
)

# Canonical benchmark catalog with domains, canonical URLs, and descriptions
CANONICAL_BENCHMARKS: dict[str, BenchmarkRecord] = {
    "humaneval": BenchmarkRecord(
        id="bm-humaneval",
        name="HumanEval",
        domain="Code Generation",
        canonical_url="https://paperswithcode.com/dataset/humaneval",
        description="Functional correctness of code synthesis",
    ),
    "mbpp": BenchmarkRecord(
        id="bm-mbpp",
        name="MBPP",
        domain="Code Generation",
        canonical_url="https://paperswithcode.com/dataset/mbpp",
        description="Mostly Basic Python Problems",
    ),
    "swe-bench": BenchmarkRecord(
        id="bm-swe-bench",
        name="SWE-bench",
        domain="Software Engineering",
        canonical_url="https://paperswithcode.com/dataset/swe-bench",
        description="Resolving real-world GitHub issues",
    ),
    "mmlu": BenchmarkRecord(
        id="bm-mmlu",
        name="MMLU",
        domain="Reasoning",
        canonical_url="https://paperswithcode.com/dataset/mmlu",
        description="Massive Multitask Language Understanding",
    ),
    "gsm8k": BenchmarkRecord(
        id="bm-gsm8k",
        name="GSM8K",
        domain="Mathematical Reasoning",
        canonical_url="https://paperswithcode.com/dataset/gsm8k",
        description="Grade School Math 8K",
    ),
    "math": BenchmarkRecord(
        id="bm-math",
        name="MATH",
        domain="Mathematical Reasoning",
        canonical_url="https://paperswithcode.com/dataset/math",
        description="Challenging Competition Mathematics",
    ),
    "arc": BenchmarkRecord(
        id="bm-arc",
        name="ARC",
        domain="Reasoning",
        canonical_url="https://paperswithcode.com/dataset/arc",
        description="Abstraction and Reasoning Corpus / AI2 Reasoning Challenge",
    ),
    "hellaswag": BenchmarkRecord(
        id="bm-hellaswag",
        name="HellaSwag",
        domain="Common Sense Reasoning",
        canonical_url="https://paperswithcode.com/dataset/hellaswag",
        description="Harder endings for common sense reasoning",
    ),
    "glue": BenchmarkRecord(
        id="bm-glue",
        name="GLUE",
        domain="Natural Language Processing",
        canonical_url="https://paperswithcode.com/dataset/glue",
        description="General Language Understanding Evaluation",
    ),
    "superglue": BenchmarkRecord(
        id="bm-superglue",
        name="SuperGLUE",
        domain="Natural Language Processing",
        canonical_url="https://paperswithcode.com/dataset/superglue",
        description="SuperGLUE benchmark",
    ),
    "squad": BenchmarkRecord(
        id="bm-squad",
        name="SQuAD",
        domain="Question Answering",
        canonical_url="https://paperswithcode.com/dataset/squad",
        description="Stanford Question Answering Dataset",
    ),
    "truthfulqa": BenchmarkRecord(
        id="bm-truthfulqa",
        name="TruthfulQA",
        domain="Honesty & Safety",
        canonical_url="https://paperswithcode.com/dataset/truthfulqa",
        description="Measuring how models mimic human falsehoods",
    ),
    "imagenet": BenchmarkRecord(
        id="bm-imagenet",
        name="ImageNet",
        domain="Computer Vision",
        canonical_url="https://paperswithcode.com/dataset/imagenet",
        description="ImageNet visual classification",
    ),
    "imagenet-1k": BenchmarkRecord(
        id="bm-imagenet-1k",
        name="ImageNet-1k",
        domain="Computer Vision",
        canonical_url="https://paperswithcode.com/dataset/imagenet-1k",
        description="ImageNet 1K visual classification",
    ),
    "coco": BenchmarkRecord(
        id="bm-coco",
        name="COCO",
        domain="Computer Vision",
        canonical_url="https://paperswithcode.com/dataset/coco",
        description="Common Objects in Context",
    ),
    "cifar-10": BenchmarkRecord(
        id="bm-cifar-10",
        name="CIFAR-10",
        domain="Computer Vision",
        canonical_url="https://paperswithcode.com/dataset/cifar-10",
        description="CIFAR-10 image classification",
    ),
    "cifar-100": BenchmarkRecord(
        id="bm-cifar-100",
        name="CIFAR-100",
        domain="Computer Vision",
        canonical_url="https://paperswithcode.com/dataset/cifar-100",
        description="CIFAR-100 image classification",
    ),
    "wmt14": BenchmarkRecord(
        id="bm-wmt14",
        name="WMT14",
        domain="Machine Translation",
        canonical_url="https://paperswithcode.com/dataset/wmt14",
        description="WMT 2014 translation benchmark",
    ),
    "wmt16": BenchmarkRecord(
        id="bm-wmt16",
        name="WMT16",
        domain="Machine Translation",
        canonical_url="https://paperswithcode.com/dataset/wmt16",
        description="WMT 2016 translation benchmark",
    ),
    "librispeech": BenchmarkRecord(
        id="bm-librispeech",
        name="LibriSpeech",
        domain="Speech & Audio",
        canonical_url="https://paperswithcode.com/dataset/librispeech",
        description="Corpus of read English speech",
    ),
    "wikitext-103": BenchmarkRecord(
        id="bm-wikitext-103",
        name="WikiText-103",
        domain="Language Modeling",
        canonical_url="https://paperswithcode.com/dataset/wikitext-103",
        description="WikiText-103 language modeling benchmark",
    ),
    "wikitext-2": BenchmarkRecord(
        id="bm-wikitext-2",
        name="WikiText-2",
        domain="Language Modeling",
        canonical_url="https://paperswithcode.com/dataset/wikitext-2",
        description="WikiText-2 language modeling benchmark",
    ),
}

# Canonical evaluation metrics with goals and units
CANONICAL_METRICS: dict[str, EvaluationMetricRecord] = {
    "pass@1": EvaluationMetricRecord(
        id="metric-pass-1",
        name="pass@1",
        goal="maximize",
        unit="%",
        description="Percentage of problems solved on first attempt",
    ),
    "pass@10": EvaluationMetricRecord(
        id="metric-pass-10",
        name="pass@10",
        goal="maximize",
        unit="%",
        description="Percentage of problems solved within 10 attempts",
    ),
    "accuracy": EvaluationMetricRecord(
        id="metric-accuracy",
        name="Accuracy",
        goal="maximize",
        unit="%",
        description="Classification accuracy percentage",
    ),
    "top-1-accuracy": EvaluationMetricRecord(
        id="metric-top-1-accuracy",
        name="Top-1 Accuracy",
        goal="maximize",
        unit="%",
        description="Top-1 classification accuracy percentage",
    ),
    "top-5-accuracy": EvaluationMetricRecord(
        id="metric-top-5-accuracy",
        name="Top-5 Accuracy",
        goal="maximize",
        unit="%",
        description="Top-5 classification accuracy percentage",
    ),
    "f1": EvaluationMetricRecord(
        id="metric-f1",
        name="F1",
        goal="maximize",
        unit="pts",
        description="Harmonic mean of precision and recall",
    ),
    "f1-score": EvaluationMetricRecord(
        id="metric-f1-score",
        name="F1-Score",
        goal="maximize",
        unit="pts",
        description="Harmonic mean of precision and recall",
    ),
    "bleu": EvaluationMetricRecord(
        id="metric-bleu",
        name="BLEU",
        goal="maximize",
        unit="pts",
        description="Bilingual Evaluation Understudy score",
    ),
    "bleu-4": EvaluationMetricRecord(
        id="metric-bleu-4",
        name="BLEU-4",
        goal="maximize",
        unit="pts",
        description="Bilingual Evaluation Understudy 4-gram score",
    ),
    "rouge-1": EvaluationMetricRecord(
        id="metric-rouge-1",
        name="ROUGE-1",
        goal="maximize",
        unit="pts",
        description="ROUGE 1-gram overlap score",
    ),
    "rouge-2": EvaluationMetricRecord(
        id="metric-rouge-2",
        name="ROUGE-2",
        goal="maximize",
        unit="pts",
        description="ROUGE 2-gram overlap score",
    ),
    "rouge-l": EvaluationMetricRecord(
        id="metric-rouge-l",
        name="ROUGE-L",
        goal="maximize",
        unit="pts",
        description="ROUGE longest common subsequence score",
    ),
    "exact-match": EvaluationMetricRecord(
        id="metric-exact-match",
        name="Exact Match",
        goal="maximize",
        unit="%",
        description="Exact match percentage",
    ),
    "map": EvaluationMetricRecord(
        id="metric-map",
        name="mAP",
        goal="maximize",
        unit="pts",
        description="Mean Average Precision",
    ),
    "perplexity": EvaluationMetricRecord(
        id="metric-perplexity",
        name="Perplexity",
        goal="minimize",
        unit="score",
        description="Language model perplexity",
    ),
    "wer": EvaluationMetricRecord(
        id="metric-wer",
        name="WER",
        goal="minimize",
        unit="%",
        description="Word Error Rate",
    ),
    "latency": EvaluationMetricRecord(
        id="metric-latency",
        name="Latency",
        goal="minimize",
        unit="ms",
        description="Inference latency",
    ),
    "loss": EvaluationMetricRecord(
        id="metric-loss",
        name="Loss",
        goal="minimize",
        unit="score",
        description="Evaluation loss",
    ),
}

# Primary default metric per benchmark
_BENCHMARK_DEFAULT_METRICS: dict[str, str] = {
    "humaneval": "pass@1",
    "mbpp": "pass@1",
    "swe-bench": "pass@1",
    "mmlu": "accuracy",
    "gsm8k": "accuracy",
    "math": "accuracy",
    "arc": "accuracy",
    "hellaswag": "accuracy",
    "glue": "accuracy",
    "superglue": "accuracy",
    "squad": "f1",
    "truthfulqa": "accuracy",
    "imagenet": "top-1-accuracy",
    "imagenet-1k": "top-1-accuracy",
    "coco": "map",
    "cifar-10": "accuracy",
    "cifar-100": "accuracy",
    "wmt14": "bleu",
    "wmt16": "bleu",
    "librispeech": "wer",
    "wikitext-103": "perplexity",
    "wikitext-2": "perplexity",
}

# Regex pattern and alias specifications for benchmarks: (key, regex, case_sensitive)
_BENCHMARK_ALIASES: list[tuple[str, str, bool]] = [
    ("humaneval", r"\b(?:HumanEval|human-eval|human_eval)\b", False),
    ("mbpp", r"\bMBPP\b", False),
    ("swe-bench", r"\b(?:SWE-bench|swebench|swe_bench)\b", False),
    ("mmlu", r"\bMMLU\b", False),
    ("gsm8k", r"\b(?:GSM8K|gsm-8k|gsm_8k)\b", False),
    ("math", r"\bMATH\b", True),
    ("math", r"\bmath\s+(?:benchmark|dataset|test\s+set)\b", False),
    ("arc", r"\bARC-(?:c|e|challenge|easy)\b", False),
    ("arc", r"\bAI2\s+Reasoning\s+Challenge\b", False),
    ("arc", r"\bARC\b", True),
    ("hellaswag", r"\b(?:HellaSwag|hella-swag)\b", False),
    ("superglue", r"\b(?:SuperGLUE|super-glue)\b", False),
    ("glue", r"\bGLUE\s+(?:benchmark|score|dataset)\b", False),
    ("glue", r"\bGLUE\b", True),
    ("squad", r"\bSQuAD(?:\s*v?[12](?:\.[012])?)?\b", False),
    ("truthfulqa", r"\b(?:TruthfulQA|truthful-qa)\b", False),
    ("imagenet-1k", r"\b(?:ImageNet-1k|imagenet-1k|imagenet\s+1k)\b", False),
    ("imagenet", r"\b(?:ImageNet|image-net)\b", False),
    ("coco", r"\b(?:MS-?COCO|COCO\s+(?:benchmark|dataset))\b", False),
    ("coco", r"\bCOCO\b", True),
    ("cifar-100", r"\b(?:CIFAR-100|cifar100)\b", False),
    ("cifar-10", r"\b(?:CIFAR-10|cifar10)\b", False),
    ("wmt14", r"\b(?:WMT14|wmt-14|wmt\s*2014|wmt\'?14|wmt\s+14)\b", False),
    ("wmt16", r"\b(?:WMT16|wmt-16|wmt\s*2016|wmt\'?16|wmt\s+16)\b", False),
    ("librispeech", r"\b(?:LibriSpeech|libri-speech)\b", False),
    ("wikitext-103", r"\b(?:WikiText-103|wikitext-103|wikitext\s+103)\b", False),
    ("wikitext-2", r"\b(?:WikiText-2|wikitext-2|wikitext\s+2)\b", False),
    ("wikitext-103", r"\b(?:WikiText|wikitext)\b", False),
]

# Patterns for explicit evaluation metrics
_METRIC_PATTERNS: list[tuple[str, str]] = [
    ("pass@1", r"\bpass\s*@\s*1\b|\bpass-at-1\b"),
    ("pass@10", r"\bpass\s*@\s*10\b|\bpass-at-10\b"),
    ("top-1-accuracy", r"\btop-?1\s+(?:accuracy|acc)\b|\btop-?1\b"),
    ("top-5-accuracy", r"\btop-?5\s+(?:accuracy|acc)\b|\btop-?5\b"),
    ("accuracy", r"\baccuracy\b|\bacc\b|\bacc\.\b"),
    ("f1", r"\bf1-score\b|\bf1\s+score\b|\bf-score\b|\bf1\b"),
    ("bleu-4", r"\bbleu-?4\b"),
    ("bleu", r"\bbleu\s+score\b|\bbleu\b"),
    ("rouge-l", r"\brouge-?l\b"),
    ("rouge-1", r"\brouge-?1\b"),
    ("rouge-2", r"\brouge-?2\b"),
    ("exact-match", r"\bexact\s+match\b|\bEM\b"),
    ("map", r"\bmean\s+average\s+precision\b|\bmAP\b"),
    ("perplexity", r"\bperplexity\b|\bppl\b"),
    ("wer", r"\bword\s+error\s+rate\b|\bwer\b"),
    ("latency", r"\blatency\b|\bruntime\b|\binference\s+time\b"),
    ("loss", r"\b(?:eval|test|val)?\s*loss\b"),
]

# Evaluation condition patterns
_CONDITION_PATTERNS: list[tuple[str, str]] = [
    ("0-shot", r"\b(?:0-shot|0\s+shot)\b"),
    ("zero-shot", r"\b(?:zero-shot|zero\s+shot)\b"),
    ("1-shot", r"\b(?:1-shot|1\s+shot|one-shot|one\s+shot)\b"),
    ("3-shot", r"\b(?:3-shot|3\s+shot)\b"),
    ("5-shot", r"\b(?:5-shot|5\s+shot)\b"),
    ("few-shot", r"\b(?:few-shot|few\s+shot)\b"),
    ("fine-tuned", r"\b(?:fine-tuned|finetuned|fine-tuning|fine\s+tuned)\b"),
    ("greedy", r"\b(?:greedy\s+decoding|greedy)\b"),
    ("chain-of-thought", r"\b(?:chain-of-thought|cot)\b"),
]


def _slugify(text: str) -> str:
    """Create URL/ID friendly slug from arbitrary string."""
    clean = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return clean or "unknown"


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences while protecting common academic abbreviations."""
    if not text or not text.strip():
        return []

    cleaned = text.strip()
    abbreviations = [
        (r"\be\.g\.", "e_DOT_g_DOT_"),
        (r"\bi\.e\.", "i_DOT_e_DOT_"),
        (r"\bet al\.", "et al_DOT_"),
        (r"\bFig\.", "Fig_DOT_"),
        (r"\bEq\.", "Eq_DOT_"),
        (r"\bvs\.", "vs_DOT_"),
        (r"\bi\.i\.d\.", "i_DOT_i_DOT_d_DOT_"),
    ]
    for pattern, replacement in abbreviations:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", cleaned)

    sentences = []
    for part in parts:
        restored = part
        for _, replacement in abbreviations:
            orig = replacement.replace("_DOT_", ".")
            restored = restored.replace(replacement, orig)
        if restored.strip():
            sentences.append(restored.strip())

    return sentences


def _clean_citation_brackets(text: str) -> str:
    """Mask citation brackets like [12], [1, 2], [1-4] with spaces to avoid false numbers."""
    return re.sub(r"\[\s*\d+(?:\s*[,-]\s*\d+)*\s*\]", " ", text)


class BenchmarkExtractor:
    """
    Mines academic papers for benchmark claims, metrics, conditions, and reported performance numbers.
    Links results to immutable EvidenceRecord instances.
    """

    def __init__(
        self,
        custom_benchmarks: Optional[dict[str, BenchmarkRecord]] = None,
    ) -> None:
        self.benchmarks: dict[str, BenchmarkRecord] = dict(CANONICAL_BENCHMARKS)
        self.benchmark_aliases: list[tuple[str, str, bool]] = list(_BENCHMARK_ALIASES)

        if custom_benchmarks:
            for key, bm in custom_benchmarks.items():
                bm_key = _slugify(bm.name)
                self.benchmarks[bm_key] = bm
                pattern = r"\b" + re.escape(bm.name) + r"\b"
                self.benchmark_aliases.insert(0, (bm_key, pattern, False))

    def extract_reported_results(
        self,
        paper: PaperRecord,
        evidence_items: Optional[list[EvidenceRecord]] = None,
    ) -> list[
        tuple[
            BenchmarkRecord,
            EvaluationMetricRecord,
            EvaluationConditionRecord,
            BenchmarkResultRecord,
            EvidenceRecord,
        ]
    ]:
        """
        Extract reported benchmark results from paper abstract and any provided evidence items.
        Returns a list of 5-tuples: (BenchmarkRecord, EvaluationMetricRecord, EvaluationConditionRecord, BenchmarkResultRecord, EvidenceRecord).
        """
        results: list[
            tuple[
                BenchmarkRecord,
                EvaluationMetricRecord,
                EvaluationConditionRecord,
                BenchmarkResultRecord,
                EvidenceRecord,
            ]
        ] = []
        seen_keys: set[tuple[str, str, str, str, float]] = set()

        # 1. Mine paper abstract if available
        if paper.abstract and paper.abstract.strip():
            sentences = _split_into_sentences(paper.abstract)
            for idx, sentence in enumerate(sentences):
                extracted = self._extract_from_sentence(
                    sentence=sentence,
                    paper=paper,
                    sentence_idx=idx + 1,
                    source_ev=None,
                )
                for item in extracted:
                    bm, metric, cond, res, ev = item
                    key = (paper.id, bm.id, metric.id, cond.id, res.metric_value)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        results.append(item)

        # 2. Mine evidence items if provided
        if evidence_items:
            for ev_item in evidence_items:
                if not ev_item.extracted_text or not ev_item.extracted_text.strip():
                    continue
                sentences = _split_into_sentences(ev_item.extracted_text)
                for idx, sentence in enumerate(sentences):
                    extracted = self._extract_from_sentence(
                        sentence=sentence,
                        paper=paper,
                        sentence_idx=idx + 1,
                        source_ev=ev_item,
                    )
                    for item in extracted:
                        bm, metric, cond, res, ev = item
                        key = (paper.id, bm.id, metric.id, cond.id, res.metric_value)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            results.append(item)

        return results

    def _extract_from_sentence(
        self,
        sentence: str,
        paper: PaperRecord,
        sentence_idx: int,
        source_ev: Optional[EvidenceRecord] = None,
    ) -> list[
        tuple[
            BenchmarkRecord,
            EvaluationMetricRecord,
            EvaluationConditionRecord,
            BenchmarkResultRecord,
            EvidenceRecord,
        ]
    ]:
        cleaned = _clean_citation_brackets(sentence)

        # 1. Identify benchmark mentions in sentence
        benchmarks_found = self._locate_benchmarks(cleaned)
        if not benchmarks_found:
            return []

        # 2. Identify sentence-level condition mentions
        sentence_conditions = self._locate_conditions(cleaned)
        default_cond = (
            sentence_conditions[0][2]
            if sentence_conditions
            else EvaluationConditionRecord(id="cond-unspecified", name="unspecified")
        )

        # 3. Locate candidate scores in the sentence
        candidate_scores = self._locate_candidate_scores(cleaned)
        if not candidate_scores:
            return []

        # 4. Determine table/figure citation if present
        table_or_figure = None
        tf_match = re.search(
            r"\b(Table\s+\d+|Figure\s+\d+|Fig\.\s*\d+)\b",
            sentence,
            re.IGNORECASE,
        )
        if tf_match:
            table_or_figure = tf_match.group(1)
        elif source_ev and source_ev.source_location and (
            "table" in source_ev.source_location.lower() or "fig" in source_ev.source_location.lower()
        ):
            table_or_figure = source_ev.source_location

        # 5. Result date determination
        result_date = None
        if paper.publication_date:
            result_date = str(paper.publication_date)
        elif paper.year:
            result_date = f"{paper.year}-01-01"

        extracted_tuples: list[
            tuple[
                BenchmarkRecord,
                EvaluationMetricRecord,
                EvaluationConditionRecord,
                BenchmarkResultRecord,
                EvidenceRecord,
            ]
        ] = []

        # 6. Pair candidate scores with benchmark mentions
        # If there's 1 benchmark mention in sentence, pair all scores with it
        if len(benchmarks_found) == 1:
            bm_record = benchmarks_found[0][2]
            bm_key = benchmarks_found[0][3]

            for score_info in candidate_scores:
                metric = self._resolve_metric(score_info.get("metric_name"), bm_key)
                cond = score_info.get("condition") or default_cond

                ev_id = f"ev-{uuid.uuid4().hex[:12]}"
                res_id = f"res-{uuid.uuid4().hex[:12]}"

                evidence = EvidenceRecord(
                    id=ev_id,
                    paper_id=paper.id,
                    evidence_type="benchmark_claim",
                    extracted_text=sentence.strip(),
                    extraction_method="benchmark_pattern_mining",
                    reporting_paper_id=source_ev.reporting_paper_id if source_ev else None,
                    source_section=source_ev.source_section if source_ev and source_ev.source_section else "Abstract",
                    source_location=source_ev.source_location if source_ev and source_ev.source_location else f"sentence_{sentence_idx}",
                    confidence=0.90,
                    retrieved_at=source_ev.retrieved_at if source_ev else None,
                )

                result_record = BenchmarkResultRecord(
                    id=res_id,
                    paper_id=paper.id,
                    benchmark_id=bm_record.id,
                    metric_id=metric.id,
                    condition_id=cond.id,
                    metric_value=float(score_info["val"]),
                    is_sota=False,
                    rank=None,
                    evidence_id=evidence.id,
                    table_or_figure=table_or_figure,
                    result_date=result_date,
                    provenance_source="author_reported",
                )

                extracted_tuples.append((bm_record, metric, cond, result_record, evidence))

        else:
            # Multiple benchmarks: pair each score with the best affinity benchmark
            for score_info in candidate_scores:
                closest_bm = min(
                    benchmarks_found,
                    key=lambda bm_item: self._calculate_bm_distance(score_info, bm_item, cleaned),
                )
                bm_record = closest_bm[2]
                bm_key = closest_bm[3]

                metric = self._resolve_metric(score_info.get("metric_name"), bm_key)
                cond = score_info.get("condition") or default_cond

                ev_id = f"ev-{uuid.uuid4().hex[:12]}"
                res_id = f"res-{uuid.uuid4().hex[:12]}"

                evidence = EvidenceRecord(
                    id=ev_id,
                    paper_id=paper.id,
                    evidence_type="benchmark_claim",
                    extracted_text=sentence.strip(),
                    extraction_method="benchmark_pattern_mining",
                    reporting_paper_id=source_ev.reporting_paper_id if source_ev else None,
                    source_section=source_ev.source_section if source_ev and source_ev.source_section else "Abstract",
                    source_location=source_ev.source_location if source_ev and source_ev.source_location else f"sentence_{sentence_idx}",
                    confidence=0.90,
                    retrieved_at=source_ev.retrieved_at if source_ev else None,
                )

                result_record = BenchmarkResultRecord(
                    id=res_id,
                    paper_id=paper.id,
                    benchmark_id=bm_record.id,
                    metric_id=metric.id,
                    condition_id=cond.id,
                    metric_value=float(score_info["val"]),
                    is_sota=False,
                    rank=None,
                    evidence_id=evidence.id,
                    table_or_figure=table_or_figure,
                    result_date=result_date,
                    provenance_source="author_reported",
                )

                extracted_tuples.append((bm_record, metric, cond, result_record, evidence))

        return extracted_tuples

    def _calculate_bm_distance(
        self,
        score_info: dict[str, Any],
        bm_item: tuple[int, int, BenchmarkRecord, str],
        text: str,
    ) -> float:
        """Calculate linguistic affinity distance between a score candidate and a benchmark mention."""
        s_start, s_end = score_info["start"], score_info["end"]
        b_start, b_end = bm_item[0], bm_item[1]

        if s_end <= b_start:
            # Score is before benchmark: e.g. "85.4% on HumanEval"
            between = text[s_end:b_start]
            # Prepositional attachment bonus
            if re.fullmatch(r"\s*(?:on|in|for|at|with)\s*(?:the\s+)?", between, re.IGNORECASE):
                return 1.0
            dist = float(b_start - s_end)
        elif b_end <= s_start:
            # Benchmark is before score: e.g. "On HumanEval, we achieve 85.4%"
            between = text[b_end:s_start]
            if re.fullmatch(r"\s*(?:[\(:]|\bof\b|\s*-\s*)\s*", between, re.IGNORECASE):
                return 1.0
            dist = float(s_start - b_end)
        else:
            between = ""
            dist = 0.0

        # Penalize crossing coordinate clause boundaries
        if re.search(r";\s*|\b(?:and|while|whereas|but)\b", between, re.IGNORECASE):
            dist += 100.0

        return dist

    def _locate_benchmarks(
        self, text: str
    ) -> list[tuple[int, int, BenchmarkRecord, str]]:
        """Find non-overlapping benchmark occurrences in text: (start, end, record, key)."""
        found: list[tuple[int, int, BenchmarkRecord, str]] = []
        occupied_spans: list[tuple[int, int]] = []

        for bm_key, pattern, case_sensitive in self.benchmark_aliases:
            flags = 0 if case_sensitive else re.IGNORECASE
            for m in re.finditer(pattern, text, flags):
                start, end = m.span()
                # Check for overlap with already found longer match
                if any(start < o_end and end > o_start for o_start, o_end in occupied_spans):
                    continue
                bm_record = self.benchmarks.get(bm_key)
                if bm_record:
                    found.append((start, end, bm_record, bm_key))
                    occupied_spans.append((start, end))

        found.sort(key=lambda item: item[0])
        return found

    def _locate_conditions(
        self, text: str
    ) -> list[tuple[int, int, EvaluationConditionRecord]]:
        """Find condition occurrences in text."""
        conditions: list[tuple[int, int, EvaluationConditionRecord]] = []
        for cond_name, pattern in _CONDITION_PATTERNS:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                start, end = m.span()
                cond_id = f"cond-{_slugify(cond_name)}"
                cond_rec = EvaluationConditionRecord(id=cond_id, name=cond_name)
                conditions.append((start, end, cond_rec))
        conditions.sort(key=lambda item: item[0])
        return conditions

    def _locate_candidate_scores(self, text: str) -> list[dict[str, Any]]:
        """
        Locate candidate scores while ignoring standalone years (e.g. 2023),
        citations, and dataset parameters.
        """
        candidates: list[dict[str, Any]] = []
        occupied_spans: list[tuple[int, int]] = []

        # Pattern 1: Variance notation: 92.3 ± 0.4% or 92.3 +/- 0.4%
        var_pattern = re.compile(
            r"\b(?P<val>\d+(?:\.\d+)?)\s*(?:±|\+/-)\s*\d+(?:\.\d+)?\s*(?P<pct>%?)",
            re.IGNORECASE,
        )
        for m in var_pattern.finditer(text):
            val_str = m.group("val")
            try:
                val = float(val_str)
                start, end = m.span()
                metric_name = self._sniff_metric_near(text, start, end)
                candidates.append({
                    "val": val,
                    "start": start,
                    "end": end,
                    "metric_name": metric_name,
                })
                occupied_spans.append((start, end))
            except ValueError:
                continue

        # Pattern 2: Explicit score + metric: 73.4% pass@1 or 85.2 F1 or 3.2% WER or 12.8 ms
        score_metric_pattern = re.compile(
            r"\b(?P<val>\d+(?:\.\d+)?)\s*(?P<pct>%?)\s+(?P<metric>pass\s*@\s*\d+|top-?\d+\s+acc(?:uracy)?|f1(?:-score|\s+score)?|bleu(?:-4)?|rouge-[l12]|exact\s+match|accuracy|acc\b|wer\b|latency|ms\b|perplexity|ppl\b|loss)\b",
            re.IGNORECASE,
        )
        for m in score_metric_pattern.finditer(text):
            start, end = m.span()
            if any(start < o_end and end > o_start for o_start, o_end in occupied_spans):
                continue
            val_str = m.group("val")
            metric_raw = m.group("metric").strip()
            if metric_raw.lower() == "ms":
                metric_raw = "latency"
            try:
                val = float(val_str)
                # Ignore years
                if self._is_year(val_str, text, start, end):
                    continue
                candidates.append({
                    "val": val,
                    "start": start,
                    "end": end,
                    "metric_name": metric_raw,
                })
                occupied_spans.append((start, end))
            except ValueError:
                continue

        # Pattern 3: Explicit metric + score: perplexity of 14.5 or WER of 3.2% or latency of 12.8 ms
        metric_score_pattern = re.compile(
            r"\b(?P<metric>pass\s*@\s*\d+|top-?\d+\s+acc(?:uracy)?|f1(?:-score|\s+score)?|bleu(?:-4)?|rouge-[l12]|exact\s+match|accuracy|acc\b|wer\b|latency|perplexity|ppl\b|loss)\s+(?:of|is|reaches|at|scores?|achieves?|:|=)?\s*(?P<val>\d+(?:\.\d+)?)\s*(?P<unit>%|ms|s|pts)?\b",
            re.IGNORECASE,
        )
        for m in metric_score_pattern.finditer(text):
            start, end = m.span()
            if any(start < o_end and end > o_start for o_start, o_end in occupied_spans):
                continue
            val_str = m.group("val")
            metric_raw = m.group("metric").strip()
            try:
                val = float(val_str)
                if self._is_year(val_str, text, start, end):
                    continue
                candidates.append({
                    "val": val,
                    "start": start,
                    "end": end,
                    "metric_name": metric_raw,
                })
                occupied_spans.append((start, end))
            except ValueError:
                continue

        # Pattern 4: Percentages: 73.4% or 88.5%
        pct_pattern = re.compile(r"\b(?P<val>\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
        for m in pct_pattern.finditer(text):
            start, end = m.span()
            if any(start < o_end and end > o_start for o_start, o_end in occupied_spans):
                continue
            val_str = m.group("val")
            try:
                val = float(val_str)
                metric_name = self._sniff_metric_near(text, start, end)
                candidates.append({
                    "val": val,
                    "start": start,
                    "end": end,
                    "metric_name": metric_name,
                })
                occupied_spans.append((start, end))
            except ValueError:
                continue

        # Pattern 5: Action verbs followed by number: achieves 88.5 on HumanEval
        verb_pattern = re.compile(
            r"\b(?:achieves?|obtains?|scores?|reaches?|reports?|yields?)\s+(?P<val>\d+(?:\.\d+)?)\b",
            re.IGNORECASE,
        )
        for m in verb_pattern.finditer(text):
            start, end = m.span()
            if any(start < o_end and end > o_start for o_start, o_end in occupied_spans):
                continue
            val_str = m.group("val")
            if self._is_year(val_str, text, start, end):
                continue
            try:
                val = float(val_str)
                metric_name = self._sniff_metric_near(text, start, end)
                candidates.append({
                    "val": val,
                    "start": start,
                    "end": end,
                    "metric_name": metric_name,
                })
                occupied_spans.append((start, end))
            except ValueError:
                continue

        candidates.sort(key=lambda item: item["start"])
        return candidates

    def _is_year(self, val_str: str, text: str, start: int, end: int) -> bool:
        """Check if an extracted number is a calendar year rather than a performance score."""
        if re.fullmatch(r"(?:19\d\d|20[0-3]\d)", val_str):
            # Check context around number
            prefix = text[max(0, start - 15) : start].lower()
            if any(w in prefix for w in ("in ", "since ", "during ", "published ", "year ")):
                return True
            # Check if followed by et al. or citation
            suffix = text[end : min(len(text), end + 15)].lower()
            if any(w in suffix for w in ("et al", "conference", "workshop", "springer", "ieee")):
                return True
            # Standalone 4-digit without percentage or explicit metric is a year
            return True
        return False

    def _sniff_metric_near(self, text: str, start: int, end: int) -> Optional[str]:
        """Look for metric keywords in the local window around a number."""
        window_start = max(0, start - 25)
        window_end = min(len(text), end + 25)
        window = text[window_start:window_end]

        for canonical_key, pat in _METRIC_PATTERNS:
            if re.search(pat, window, re.IGNORECASE):
                return canonical_key
        return None

    def _resolve_metric(
        self,
        metric_hint: Optional[str],
        benchmark_key: str,
    ) -> EvaluationMetricRecord:
        """Resolve metric record from explicit hint or benchmark default."""
        if metric_hint:
            metric_hint_lower = metric_hint.lower().strip()
            # Match directly or by pattern
            if metric_hint_lower in CANONICAL_METRICS:
                return CANONICAL_METRICS[metric_hint_lower]

            for canonical_key, pat in _METRIC_PATTERNS:
                if re.search(pat, metric_hint_lower, re.IGNORECASE):
                    if canonical_key in CANONICAL_METRICS:
                        return CANONICAL_METRICS[canonical_key]

        # Fallback to benchmark default
        default_key = _BENCHMARK_DEFAULT_METRICS.get(benchmark_key)
        if default_key and default_key in CANONICAL_METRICS:
            return CANONICAL_METRICS[default_key]

        return CANONICAL_METRICS["accuracy"]


__all__ = [
    "CANONICAL_BENCHMARKS",
    "CANONICAL_METRICS",
    "BenchmarkExtractor",
]
