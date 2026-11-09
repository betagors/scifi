"""Publisher and venue profile registry for academic submissions."""

from __future__ import annotations

from scifi.submission.models import PublisherProfile

PUBLISHER_PROFILES: dict[str, PublisherProfile] = {
    "elsevier": PublisherProfile(
        venue_id="elsevier",
        name="Elsevier",
        max_highlight_chars=85,
        min_highlights=3,
        max_highlights=5,
        require_credit_statement=True,
        require_conference_extension_clause=False,
        require_ethics_declaration=False,
    ),
    "ieee": PublisherProfile(
        venue_id="ieee",
        name="IEEE Transactions & Journals",
        max_highlight_chars=100,
        min_highlights=3,
        max_highlights=5,
        require_credit_statement=False,
        require_conference_extension_clause=True,
        require_ethics_declaration=False,
    ),
    "springer": PublisherProfile(
        venue_id="springer",
        name="Springer Nature",
        max_highlight_chars=100,
        min_highlights=3,
        max_highlights=5,
        require_credit_statement=False,
        require_conference_extension_clause=False,
        require_ethics_declaration=True,
    ),
    "acm": PublisherProfile(
        venue_id="acm",
        name="ACM Publications",
        max_highlight_chars=100,
        min_highlights=3,
        max_highlights=5,
        require_credit_statement=False,
        require_conference_extension_clause=False,
        require_ethics_declaration=False,
    ),
    "openreview": PublisherProfile(
        venue_id="openreview",
        name="OpenReview / Double-Blind Conference",
        max_highlight_chars=100,
        min_highlights=3,
        max_highlights=5,
        require_credit_statement=False,
        require_conference_extension_clause=False,
        require_ethics_declaration=False,
    ),
    "general": PublisherProfile(
        venue_id="general",
        name="Standard Academic Journal",
        max_highlight_chars=100,
        min_highlights=3,
        max_highlights=5,
        require_credit_statement=False,
        require_conference_extension_clause=False,
        require_ethics_declaration=False,
    ),
}

# Aliases
VENUE_ALIASES: dict[str, str] = {
    "elsevier": "elsevier",
    "sciencedirect": "elsevier",
    "cell": "elsevier",
    "ieee": "ieee",
    "ieee-t": "ieee",
    "springer": "springer",
    "nature": "springer",
    "sn": "springer",
    "acm": "acm",
    "neurips": "openreview",
    "icml": "openreview",
    "iclr": "openreview",
    "cvpr": "openreview",
    "acl": "openreview",
    "openreview": "openreview",
}


def get_publisher_profile(venue: str | None = None) -> PublisherProfile:
    """Resolve venue identifier to a PublisherProfile."""
    if not venue:
        return PUBLISHER_PROFILES["general"]
    key = venue.strip().lower()
    canonical = VENUE_ALIASES.get(key, key)
    return PUBLISHER_PROFILES.get(canonical, PUBLISHER_PROFILES["general"])
