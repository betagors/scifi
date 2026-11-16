---
name: da-vinci
description: Scientific figure, plot, and visual accessibility auditor. Audits LaTeX manuscripts for low-DPI raster figures, ensures vector formats for plots, verifies subfigure parity, and detects colorblind-inaccessible palettes.
---

# Da Vinci: Scientific Figure & Visual Accessibility Sentinel

The `da-vinci` skill audits figures and diagrams in scientific manuscripts to ensure publication-quality visuals and compliance with accessibility standards across top venues (IEEE, ACM, Nature, NeurIPS, ICML).

## When to Use
- Pre-submission figure quality and print resolution checks.
- Auditing scientific plots for low-DPI bitmaps ($< 300\text{ DPI}$) or missing vector formats.
- Detecting unreferenced subfigures (`(a)`, `(b)`, `(c)` declared in captions but never analyzed in body prose).
- Checking colorblind accessibility (avoiding problematic red/green curve conflicts without distinct line styling).

---

## Native MCP Tools

Invoke the native SciFi MCP tools directly:

### `scifi_audit_figures`
Audit manuscript figures for resolution, vector vs raster format, subfigure parity, colorblind risks, and **automatically render PNG visual previews** of vector `.pdf` figures and figure-bearing pages of the compiled PDF.

```json
{
  "tex_path": "path/to/main.tex",
  "min_dpi": 300,
  "render_previews": true
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `tex_path` | string | Yes | Path to LaTeX root file (`main.tex`, `paper.tex`) |
| `base_dir` | string | No | Base directory containing figure assets (defaults to directory of `tex_path`) |
| `min_dpi` | integer | No | Minimum required DPI for raster images (default: 300) |
| `render_previews` | boolean | No | Render PNG previews of vector figures & compiled PDF figure pages (default: `true`) |
| `pdf_path` | string | No | Optional compiled PDF path (auto-detected from `tex_path` if omitted) |
| `render_dpi` | integer | No | DPI for rendered PNG previews (default: 150) |
| `vlm_check` | boolean | No | Run VLM visual defect inspection on rendered PNGs (default: `false`; CLI: `sf figures --vlm`) |
| `vlm_provider` | string | No | Optional VLM provider (`gemini`, `openai`, `anthropic`, `openai_compatible`) |
| `vlm_model` | string | No | Optional VLM model identifier override |

### `scifi_render_pdf`
Render any pages of a compiled PDF manuscript or standalone figure PDF into PNG screenshots for direct visual inspection.

---

## Visual Inspection ("Eyes of SciFi") Protocol

**Do NOT rely solely on LaTeX source regex checks.** Whenever `rendered_previews` (from `scifi_audit_figures`) or `rendered_pages` (from `scifi_render_pdf` / `scifi_compile_latex`) are returned:
1. Call `read_file` on the PNG `image_path`s to visually inspect the rendered figures and PDF pages.
2. Check for defects that static LaTeX parsing cannot see:
   - Overlapping, clipped, or illegible axis labels, tick marks, and legends.
   - Subfigure `(a)`, `(b)`, `(c)` misalignment, inconsistent sizing, or awkward cropping.
   - Figures overflowing column/page margins or colliding with captions/text.
   - Poor contrast, cluttered gridlines, or indistinguishable colors.
   - **Semantic & Mathematical Plot Consistency:** Read fitted curve equations, legend annotations (e.g., $a + b x^{-\alpha}$), and axis values directly from the rendered PNGs and verify that they do not contradict the analytical constants or bounds stated in the manuscript text, tables, and appendices.
   - **Legend, Axis & Diagram Naming/Abbreviation Consistency:** Verify that method/variant names, baseline labels, and abbreviations inside figure legends, axis labels, and schematics match the standardized terminology in the manuscript text and tables (no stale `Lya-BiMAPPO` or `Safe-Pure-MAPPO` labels left in plots after text cleanup).

Returns:
```json
{
  "status": "SUCCESS",
  "total_figures_inspected": 4,
  "total_issues": 1,
  "clean_score": 95,
  "issues": [
    {
      "category": "UNREFERENCED_SUBFIGURE",
      "severity": "WARNING",
      "figure_ref": "fig:system_model",
      "message": "Subfigure (c) declared in caption of 'fig:system_model' is never referenced or discussed in manuscript body text.",
      "recommendation": "Add discussion or explicit cross-reference to (c) in the corresponding section prose."
    }
  ]
}
```

---

## Visual Audit Rubric

1. **Vector vs. Raster Format:** Scientific plots, loss curves, bar charts, and schematics must use vector formats (`.pdf`, `.eps`, `.svg`). Raster formats (`.png`, `.jpg`) are only permitted for photographs, micrographs, or synthetic rendering outputs.
2. **Resolution (DPI):** Any raster figure must maintain $\ge 300\text{ DPI}$ at its final printed column width.
3. **Subfigure Parity:** Every subfigure tag declared in a caption must be explicitly discussed in the body text.
4. **Colorblind Accessibility:** Curves distinguished solely by red and green colors must employ secondary visual channels (e.g., dashed, dotted, or distinctive marker symbols).
5. **Label & Abbreviation Consistency:** Figure legends, captions, and schematics must use the same standardized method/variant names as the manuscript text and tables, avoiding invented/compound acronyms (`Lya-BiMAPPO`, `Safe-Pure-MAPPO`) or unexplained ad-hoc abbreviations.
