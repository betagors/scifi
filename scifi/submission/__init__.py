"""SciFi Submission Suite: Editorial Cover Letters, Highlights, Title Pages & Code Packaging."""

from __future__ import annotations

from scifi.submission.code_packager import package_anonymous_code
from scifi.submission.cover_letter import generate_cover_letter
from scifi.submission.highlights import generate_highlights
from scifi.submission.title_page import generate_title_page
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
    "generate_cover_letter",
    "generate_highlights",
    "generate_title_page",
    "get_publisher_profile",
    "package_anonymous_code",
]
