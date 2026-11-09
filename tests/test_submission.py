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
