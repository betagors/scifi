import json
from unittest.mock import patch

from skills.shannon.scripts.test_keywords import (
    check_keyword_relevance,
    check_title_collision,
    compute_abstract_keyword_density,
    compute_title_keyword_overlap,
    compute_title_similarity,
    evaluate_academic_seo,
    evaluate_accessibility,
    evaluate_triage_score,
    run_cli,
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


def test_evaluate_academic_seo_frontloading_and_anchoring():
    # Good SEO: keyphrase in first 65 chars, 10-14 words, keyphrase in lead, middle, end
    title = "Decentralized Beamforming for Distributed Satellite Clusters under Severe Doppler Constraints"
    abstract = (
        "Low Earth orbit satellite constellations rely on decentralized beamforming for inter-satellite links. "
        "However, high orbital velocities cause severe Doppler shifts that degrade synchronization. "
        "We introduce an adaptive decentralized beamforming algorithm using Riemannian manifold optimization. "
        "Simulations demonstrate a 4.2 dB signal-to-noise ratio gain and 28.5% lower phase drift. "
        "These results confirm that decentralized beamforming enables scalable satellite networking."
    )
    keywords = ["satellite constellations", "Doppler shift", "Riemannian manifold", "phase drift"]
    seo = evaluate_academic_seo(title, abstract, keywords)
    assert seo["front_loaded"] is True
    assert seo["sweet_spot_length"] is True
    assert seo["three_beat_anchoring"] is True
    assert len(seo["seo_hacks_applied"]) >= 3


def test_triage_score_penalizes_ai_tropes_and_em_dashes():
    title = "Delving into Deep Learning: A Pivotal Paradigm"
    abstract = (
        "It is crucial to note that this paper serves as a testament to deep learning — "
        "we delve into pivotal architectures to explore a rich tapestry of neural models."
    )
    keywords = ["deep learning", "neural networks"]
    res = evaluate_triage_score(title, abstract, keywords)
    assert res["scores"]["style_debiasing"]["points"] < 5
    assert "em_dash" in res["scores"]["style_debiasing"]["penalties"]
    assert "delve" in res["scores"]["style_debiasing"]["flagged_words"]


def test_triage_score_awards_clean_quantified_abstract():
    title = "Decentralized Beamforming for Distributed Satellite Clusters under Doppler Constraints"
    abstract = (
        "Low Earth orbit satellite constellations require coordinated beamforming. "
        "However, severe Doppler shift and propagation delays limit existing distributed algorithms. "
        "We formulate an adaptive synchronization algorithm based on Riemannian manifold optimization. "
        "Simulations demonstrate a 4.2 dB signal-to-noise ratio improvement and 28.5% reduction in phase drift "
        "compared to conventional gradient descent. "
        "These results enable real-time inter-satellite coordination under dynamic orbital geometry."
    )
    keywords = ["satellite constellations", "Doppler shift", "Riemannian manifold", "phase drift"]
    res = evaluate_triage_score(title, abstract, keywords)
    assert res["total_score"] >= 85
    assert res["scores"]["gap_precision"]["points"] >= 18
    assert res["scores"]["algorithmic_specificity"]["points"] >= 18
    assert res["scores"]["experimental_quantification"]["points"] >= 18
    assert res["scores"]["style_debiasing"]["points"] == 20


def test_title_similarity_computation():
    t1 = "Federated Learning for Edge Computing under Latency Constraints"
    t2 = "Federated Learning for Edge Computing with Latency Constraints"
    t3 = "Deep Reinforcement Learning for Autonomous Drone Navigation"
    assert compute_title_similarity(t1, t2) > 0.85
    assert compute_title_similarity(t1, t3) < 0.40


def test_title_collision_offline_mode():
    result = check_title_collision("Adaptive Beamforming for Satellites", live=False)
    assert result["status"] == "SKIPPED_OFFLINE"


def test_title_collision_mocked_openalex_response():
    mock_payload = {
        "results": [
            {
                "title": "Adaptive Beamforming for Low Earth Orbit Satellites",
                "cited_by_count": 42,
                "publication_year": 2023,
                "primary_location": {"source": {"display_name": "IEEE Transactions on Aerospace"}},
            }
        ]
    }
    with patch("skills.shannon.scripts.test_keywords.fetch_json_url", return_value=mock_payload):
        res = check_title_collision("Adaptive Beamforming for Low Earth Orbit Satellites", live=True)
        assert res["risk_level"] in ("MODERATE OVERLAP", "HIGH COLLISION")
        assert len(res["matches"]) == 1


def test_keyword_relevance_mocked_openalex_response():
    mock_payload = {
        "results": [
            {
                "title": "A Survey on Federated Learning",
                "primary_location": {"source": {"display_name": "IEEE Communications Surveys & Tutorials"}},
            }
        ]
    }
    with patch("skills.shannon.scripts.test_keywords.fetch_json_url", return_value=mock_payload):
        res = check_keyword_relevance(["federated learning"], live=True)
        assert res["status"] == "LIVE_OK"
        assert "federated learning" in res["keyword_insights"]


def test_cli_json_output(capsys):
    args = [
        "--title",
        "Decentralized Beamforming for Distributed Satellite Clusters under Severe Doppler Constraints",
        "--abstract",
        "Satellite networks require coordination. However, existing schemes fail under high latency. We formulate an algorithm achieving 3.5 dB gain. This enables robust links.",
        "--keywords",
        "satellite clusters, beamforming, latency constraints",
        "--json",
    ]
    exit_code = run_cli(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "triage_score" in data
    assert "seo" in data
    assert "accessibility" in data
    assert "overlap" in data
    assert "density" in data
    assert exit_code in (0, 1)


def test_cli_human_readable_report(capsys):
    args = [
        "--title",
        "Decentralized Beamforming for Distributed Satellite Clusters under Severe Doppler Constraints",
        "--abstract",
        "Satellite networks require coordination. However, existing schemes fail under high latency. We formulate an adaptive algorithm achieving 3.5 dB gain and 20% lower loss. This enables robust inter-satellite links.",
        "--keywords",
        "constellations, synchronization, orbital networks",
    ]
    exit_code = run_cli(args)
    captured = capsys.readouterr()
    assert "SHANNON MANUSCRIPT AUDIT" in captured.out
    assert "REVIEWER TRIAGE SCORECARD" in captured.out
    assert "ACADEMIC SEO & DISCOVERABILITY" in captured.out
    assert exit_code == 0
