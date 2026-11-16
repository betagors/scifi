---
name: layout
description: Page budget and typographic micro-trimming assistant. Detects paragraph widow lines, prunes line slack, condenses BibTeX venues to standard ISO-4/IEEE abbreviations, and optimizes float density without forbidden negative vspace hacks.
---

# Layout: Academic Page Budget & Micro-Trimming Assistant

The `layout` skill helps authors meet strict page limits (e.g. 8 pages or 12 pages) legitimately and typographically—without resorting to forbidden negative `\vspace` hacks or squeezed margins that trigger desk rejection.

## When to Use
- When a paper is slightly over length (e.g., 8.2 pages with an 8-page ceiling).
- Finding paragraphs with orphan/widow terminal lines (1–3 words) where minor rewording claws back full lines.
- Shortening verbose bibliography entries in `.bib` files using standard IEEE/ISO-4 abbreviations (saving 0.5–1 full page).
- Identifying oversized floats and tables that need `\small` or adjusted padding.

---

## Native MCP Tool

Invoke the native SciFi MCP tool directly:

### `scifi_trim_budget`
Audit manuscript and bibliography for line-saving opportunities.

```json
{
  "tex_path": "path/to/main.tex",
  "bib_path": "path/to/references.bib"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `tex_path` | string | Yes | Path to LaTeX root file (`main.tex`, `paper.tex`) |
| `bib_path` | string | No | Path to BibTeX file (auto-discovered if omitted) |
| `render_previews` | boolean | No | Render compiled PDF pages to PNG for visual layout inspection (default: `true`) |
| `pdf_path` | string | No | Optional compiled PDF path (auto-detected from `tex_path` if omitted) |
| `render_dpi` | integer | No | DPI for rendered PNG previews (default: 150) |
| `pages` | string | No | Optional page numbers or ranges to render (e.g., `"1-4,8"`) |
| `vlm_check` | boolean | No | Optional external VLM check (default: `false`; not needed when running inside Antigravity/Claude Code) |
| `vlm_provider` | string | No | Optional external VLM provider (`gemini`, `openai`, `anthropic`, `openai_compatible`) |
| `vlm_model` | string | No | Optional external VLM model identifier override |

---

## Visual Inspection ("Eyes of SciFi") Protocol (No API Key Required)

`scifi_trim_budget` automatically renders compiled PDF pages to PNGs (`rendered_pages`) and runs local pixel-level whitespace checks (`bottom_whitespace_ratio`). Whenever `rendered_pages` are returned:
1. Call `read_file` on the PNG `image_path`s to visually inspect the rendered pages directly using your built-in vision.
2. Check for layout defects that static `.tex` parsing cannot see:
   - Awkward page-break whitespace or large gaps before/after floats.
   - Orphan headings or isolated single-line trailing paragraphs at page/column boundaries.
   - Sparse trailing final page slack or overfull margins/gutters.

Returns:
```json
{
  "status": "SUCCESS",
  "total_potential_lines_saved": 8,
  "bibtex_condensed_entries": 4,
  "total_suggestions": 3,
  "suggestions": [
    {
      "suggestion_type": "WIDOW_LINE",
      "target": "... convergence.",
      "description": "Paragraph ends with a widow line of only 1 word(s) ('convergence.'). Pruning 1 word(s) from this paragraph will recover 1 full vertical line.",
      "potential_savings_lines": 1,
      "proposed_text": "[Trim 1-3 non-essential words from preceding sentences]"
    },
    {
      "suggestion_type": "BIBTEX_ABBREVIATION",
      "target": "references.bib",
      "description": "Found 4 verbose journal/conference titles that can be shortened to standard ISO-4/IEEE abbreviations.",
      "potential_savings_lines": 4,
      "proposed_text": "Run BibTeX abbreviation engine to shorten 4 entries"
    }
  ]
}
```
