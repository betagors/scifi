import pytest
from skills.shannon.scripts.test_keywords import (
    compute_title_keyword_overlap,
    compute_abstract_keyword_density,
    evaluate_accessibility,
    tokenize,
)

def test_tokenize_strips_punctuation_and_lowercases():
    text = "Adaptive Federated-Learning: Under High Latency?"
    tokens = tokenize(text)
    assert "adaptive" in tokens
    assert "federated" in tokens
    assert "learning" in tokens
    assert "latency" in tokens
    # Stop words like "under" should be stripped
    assert "under" not in tokens

def test_title_keyword_overlap_detects_redundancy():
    title = "Adaptive Federated Learning for Edge Computing under Latency Constraints"
    keywords = ["federated learning", "edge computing", "privacy preservation", "stochastic optimization"]
    result = compute_title_keyword_overlap(title, keywords)
    assert result["overlap_ratio"] > 0.0
    assert "federated" in result["overlapping_words"]
    assert "edge" in result["overlapping_words"]
    assert result["distinct_keywords_count"] == 2

def test_title_keyword_overlap_zero_when_distinct():
    title = "Adaptive Resource Allocation under Strict Latency Constraints"
    keywords = ["federated learning", "differential privacy", "edge nodes"]
    result = compute_title_keyword_overlap(title, keywords)
    assert result["overlap_ratio"] == 0.0
    assert len(result["overlapping_words"]) == 0
    assert result["distinct_keywords_count"] == 3

def test_abstract_keyword_density_counts_and_flags():
    abstract = (
        "We propose federated learning across edge devices. "
        "Our federated learning framework optimizes transmission latency. "
        "Evaluations show federated learning achieves convergence."
    )
    keywords = ["federated learning", "differential privacy"]
    result = compute_abstract_keyword_density(abstract, keywords)
    assert result["densities"]["federated learning"]["count"] == 3
    assert result["densities"]["federated learning"]["status"] == "OPTIMAL"
    assert result["densities"]["differential privacy"]["count"] == 0
    assert result["densities"]["differential privacy"]["status"] == "OMITTED"

def test_evaluate_accessibility_flags_runon_sentences():
    long_sentence = " ".join(["word"] * 40) + "."
    normal_sentence = "This is a concise opening sentence explaining the practical context."
    res = evaluate_accessibility(long_sentence)
    assert res["has_runon_sentences"] is True
    assert res["max_sentence_length"] == 40

    res_normal = evaluate_accessibility(normal_sentence)
    assert res_normal["has_runon_sentences"] is False
    assert res_normal["sentence_count"] == 1
