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

## Native MCP Tool

Invoke the native SciFi MCP tool directly:

### `scifi_audit_figures`
Audit manuscript figures for resolution, vector vs raster format, subfigure parity, and colorblind risks.

```json
{
  "tex_path": "path/to/main.tex",
  "min_dpi": 300
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `tex_path` | string | Yes | Path to LaTeX root file (`main.tex`, `paper.tex`) |
| `base_dir` | string | No | Base directory containing figure assets (defaults to directory of `tex_path`) |
| `min_dpi` | integer | No | Minimum required DPI for raster images (default: 300) |

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
