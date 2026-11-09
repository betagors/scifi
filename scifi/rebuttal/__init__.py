"""Author Rebuttal and Revision Diff Suite module (socrates/rebuttal)."""

from scifi.rebuttal.differ import diff_manuscript
from scifi.rebuttal.formatter import format_rebuttal_scaffold
from scifi.rebuttal.models import (
    ManuscriptDiffSummary,
    RebuttalScaffold,
    ReviewItem,
)

__all__ = [
    "diff_manuscript",
    "format_rebuttal_scaffold",
    "ManuscriptDiffSummary",
    "RebuttalScaffold",
    "ReviewItem",
]
