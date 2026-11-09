"""Author rebuttal formatter and 4-beat response scaffolding engine."""

from __future__ import annotations

import re
from typing import Any

from scifi.rebuttal.models import RebuttalScaffold, ReviewItem


RE_REVIEWER_HEADER = re.compile(
    r"(?:###?\s*)?(?:Reviewer|Official Review|Review\s*#?)\s*([0-9A-Za-z]+)\s*[:\-]?",
    re.IGNORECASE,
)


def format_rebuttal_scaffold(
    reviews_text: str,
    venue: str = "openreview",
) -> RebuttalScaffold:
    """Parse raw review text and generate a structured 4-beat rebuttal response document."""
    lines = reviews_text.strip().splitlines()
    reviewer_chunks: dict[str, list[str]] = {}
    current_reviewer = "Reviewer 1"
    reviewer_chunks[current_reviewer] = []

    for line in lines:
        m = RE_REVIEWER_HEADER.match(line.strip())
        if m:
            rev_num = m.group(1).strip()
            current_reviewer = f"Reviewer {rev_num}"
            if current_reviewer not in reviewer_chunks:
                reviewer_chunks[current_reviewer] = []
        else:
            if line.strip():
                reviewer_chunks[current_reviewer].append(line.strip())

    items: list[ReviewItem] = []
    scaffold_blocks: list[str] = [
        f"# Author Response & Rebuttal ({venue.upper()})\n",
        "We thank the reviewers for their constructive feedback and thoughtful evaluation. Below, we address each question and critique with specific empirical evidence and corresponding manuscript revisions.\n",
    ]

    for rev_id, rev_lines in reviewer_chunks.items():
        if not rev_lines:
            continue
        scaffold_blocks.append(f"## Response to {rev_id}\n")

        # Split reviewer content into question / paragraph points
        combined = " ".join(rev_lines)
        # Split by question marks or numbers e.g. "1.", "2."
        points = re.split(r"(?<=[?.!])\s+(?=[A-Z0-9])", combined)
        filtered_points = [p.strip() for p in points if len(p.strip()) > 15]
        if not filtered_points:
            filtered_points = [combined]

        for p_idx, pt in enumerate(filtered_points, start=1):
            category = "CLARIFICATION"
            lower_pt = pt.lower()
            if any(k in lower_pt for k in ["baseline", "experiment", "sota", "curve", "result", "compare", "ablation"]):
                category = "ADDITIONAL_EXPERIMENT"
            elif any(k in lower_pt for k in ["proof", "theorem", "lemma", "assumption", "bound", "complexity"]):
                category = "THEORETICAL_RIGOR"

            item = ReviewItem(
                reviewer_id=rev_id,
                item_index=p_idx,
                critique_text=pt,
                category=category,
            )
            items.append(item)

            scaffold_blocks.append(f"### Q{p_idx} [{category}]: \"{pt}\"\n")
            scaffold_blocks.append(
                f"- **1. Summary & Direct Answer:**\n"
                f"  Under condition $\\mathcal{{C}}$, our approach addresses this directly because ...\n\n"
                f"- **2. Action Taken & Manuscript Revision:**\n"
                f"  We have updated Section X (Lines Y–Z) to explicitly document ...\n\n"
                f"- **3. Empirical / Theoretical Evidence:**\n"
                f"  The table below summarizes the new comparative evaluation:\n\n"
                f"  | Method | Metric A ($\\uparrow$) | Metric B ($\\downarrow$) |\n"
                f"  | :--- | :---: | :---: |\n"
                f"  | Baseline | 82.4 | 14.1 |\n"
                f"  | **Ours (Revised)** | **88.9** | **9.2** |\n\n"
                f"- **4. Revised Manuscript Excerpt:**\n"
                f"  > *\"...\"*\n"
            )

    full_markdown = "\n".join(scaffold_blocks)

    return RebuttalScaffold(
        status="SUCCESS",
        venue=venue,
        total_critiques_parsed=len(items),
        reviewers=list(reviewer_chunks.keys()),
        items=items,
        markdown_template=full_markdown,
    )
