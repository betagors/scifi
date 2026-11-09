"""Page budget micro-trimming assistant module (scribe/layout)."""

from scifi.layout.abbreviations import (
    abbreviate_bib_string,
    abbreviate_venue,
)
from scifi.layout.models import (
    TrimBudgetResult,
    TrimSuggestion,
    TrimSuggestionType,
)
from scifi.layout.trim import (
    audit_trim_budget,
    detect_paragraph_slack,
    detect_table_and_float_slack,
)

__all__ = [
    "abbreviate_bib_string",
    "abbreviate_venue",
    "audit_trim_budget",
    "detect_paragraph_slack",
    "detect_table_and_float_slack",
    "TrimBudgetResult",
    "TrimSuggestion",
    "TrimSuggestionType",
]
