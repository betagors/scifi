"""SciFi Submission Suite: Editorial Cover Letters, Highlights, Title Pages & Code Packaging."""

from __future__ import annotations

from scifi.submission.highlights import generate_highlights
from scifi.submission.models import (
    AuthorInfo,
    CodePackagerResult,
    CoverLetterResult,
    HighlightItem,
    HighlightsResult,
    PublisherProfile,
    SubmissionBundleResult,
    TitlePageResult,
)
from scifi.submission.profiles import get_publisher_profile

__all__ = [
    "AuthorInfo",
    "CodePackagerResult",
    "CoverLetterResult",
    "HighlightItem",
    "HighlightsResult",
    "PublisherProfile",
    "SubmissionBundleResult",
    "TitlePageResult",
    "generate_highlights",
    "get_publisher_profile",
]
