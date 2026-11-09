---
name: rebuttal
description: Peer-review rebuttal and manuscript revision suite. Ingests raw reviewer comments to scaffold disciplined, 4-beat point-by-point rebuttal responses and automates section-by-section LaTeX diff tracking via latexdiff.
---

# Rebuttal: Author Revision & Point-by-Point Rebuttal Suite

The `rebuttal` skill structures and disciplines author responses during the critical peer-review rebuttal and camera-ready revision cycles for top-tier venues (OpenReview, IEEE ScholarOne, ACM, Nature/Science).

## When to Use
- When receiving conference/journal peer reviews and drafting the author response.
- Scaffolding a disciplined, anti-sycophantic, 4-beat response for every reviewer critique.
- Tracking line-by-line and section-by-section changes between original submission and revision manuscripts.
- Generating marked-up revision PDFs and change ledgers via `latexdiff`.

---

## Native MCP Tools

Invoke the native SciFi MCP tools directly:

### `scifi_format_rebuttal`
Parse raw reviewer comments into a disciplined 4-beat response document.

```json
{
  "reviews_text": "Reviewer 1:\nAlgorithm 1 lacks runtime complexity analysis...",
  "venue": "openreview"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `reviews_text` | string | Yes | Raw review text or comments dump |
| `venue` | string | No | Target venue template (default: "openreview") |

---

### `scifi_diff_manuscript`
Perform a section-by-section diff between two LaTeX manuscripts and optionally generate a marked-up diff PDF.

```json
{
  "old_tex_path": "path/to/submission_v1/main.tex",
  "new_tex_path": "path/to/revision_v2/main.tex",
  "generate_pdf": true
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `old_tex_path` | string | Yes | Path to original submission LaTeX root |
| `new_tex_path` | string | Yes | Path to revised LaTeX root |
| `generate_pdf` | boolean | No | Whether to compile marked-up `diff.pdf` (default: false) |
| `output_tex` | string | No | Custom output path for marked-up `.tex` |
