"""Tests for the SciFi Academic Submission Suite."""

from __future__ import annotations

import pytest
from scifi.submission.profiles import get_publisher_profile
from scifi.submission.models import AuthorInfo


def test_publisher_profiles():
    els = get_publisher_profile("elsevier")
    assert els.venue_id == "elsevier"
    assert els.max_highlight_chars == 85
    assert els.require_credit_statement is True

    ieee = get_publisher_profile("ieee")
    assert ieee.venue_id == "ieee"
    assert ieee.max_highlight_chars == 100
    assert ieee.require_conference_extension_clause is True

    gen = get_publisher_profile("unknown_venue")
    assert gen.venue_id == "general"


def test_highlights_validation_elsevier():
    from scifi.submission.highlights import generate_highlights

    # Under 85 chars
    bullets = [
        "Proposes a sub-quadratic attention mechanism for multi-modal transformers.",
        "Demonstrates 4.2x inference speedup across canonical GLUE and SQuAD benchmarks.",
        "Validates mathematical convergence bounds under mild Lipschitz assumptions.",
    ]
    res = generate_highlights(bullets, venue="elsevier")
    assert res.all_valid is True
    assert len(res.highlights) == 3
    assert "\\begin{itemize}" in res.latex_text

    # Over 85 chars for Elsevier
    long_bullets = [
        "This is an excessively long bullet point that provides way too much descriptive background information and easily exceeds the eighty-five character limit."
    ]
    res_invalid = generate_highlights(long_bullets, venue="elsevier")
    assert res_invalid.all_valid is False
    assert res_invalid.highlights[0].is_valid is False
    assert res_invalid.highlights[0].char_count > 85

