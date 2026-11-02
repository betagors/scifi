---
name: compiler
description: Autonomous LaTeX engine. Compiles manuscripts using latexmk/pdflatex, isolates compilation errors with exact file and line numbers, auto-installs missing TeX packages via tlmgr/mpm/winget, and flags undefined citations and broken cross-references.
---

# Compiler: Autonomous LaTeX Compilation & Error Isolation Engine

The `compiler` skill autonomously compiles LaTeX manuscripts into PDF, isolates build failures by file and line number, detects missing TeX packages, and flags broken cross-references and undefined citations.

## When to Use
- Compiling any LaTeX manuscript (`.tex`) into a final PDF.
- Diagnosing compilation failures, missing packages, syntax errors, or broken macro definitions.
- Identifying undefined citations (`\cite{...}`) and broken cross-references (`\ref{...}` / `\label{...}`).
- Verifying manuscript integrity after automated prose rewrites, math updates, or citation insertions.

---

## Native MCP Tools

Invoke the native SciFi MCP tool directly:

### `scifi_compile_latex`
Autonomously compile LaTeX manuscripts with automated log error parsing and engine diagnostics.

```json
{
  "entrypoint": "path/to/main.tex",
  "engine": "latexmk",
  "clean": true
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `entrypoint` | string | Yes | Path to the root `.tex` manuscript file |
| `engine` | string | No | Compiler engine: `"latexmk"` (default), `"pdflatex"`, `"xelatex"`, or `"lualatex"` |
| `clean` | boolean | No | Whether to clean auxiliary files (`.aux`, `.log`, `.out`, etc.) upon completion (default: `true`) |

---

## Output Fields

```json
{
  "status": "SUCCESS | ERROR",
  "pdf_path": "path/to/main.pdf",
  "engine": "latexmk",
  "errors": [
    {"file": "main.tex", "line": 42, "message": "Undefined control sequence."}
  ],
  "missing_packages": ["algorithm2e.sty"],
  "undefined_citations": ["Smith2020"],
  "undefined_references": ["fig:overview"],
  "layout_warnings": {"overfull_hbox": 3, "underfull_hbox": 1},
  "log_tail": "..."
}
```

---

## Status Codes & Agent Actions

| Status Code | Meaning | Agent Action |
|---|---|---|
| `SUCCESS` | PDF built cleanly | Report `pdf_path` to user. Report any non-fatal warnings (undefined references or citations, overfull hboxes). |
| `ERROR` | Compilation aborted or engine failed | Inspect `errors` list. For each syntax error, locate `file` and `line`, fix the LaTeX markup, and recompile. |
| Missing Packages | `missing_packages` is non-empty | Identify missing style files (`.sty`). If MiKTeX/TeX Live is installed, prompt package installation or provide fallback markup. |
| Undefined Citations | `undefined_citations` is non-empty | Cross-check with `references.bib`. Use `scifi_verify_citation` or `scifi_search_literature` to find missing BibTeX keys. |
| Undefined References | `undefined_references` is non-empty | Match broken `\ref{key}` against missing `\label{key}` across manuscript files. |

---

## Integrated Verification Workflow

```
turing    → verify equations/gradients
alex      → verify citations & .bib entries
argus     → audit uncredited methods
human     → rewrite prose & remove AI hallmarks
compiler  → scifi_compile_latex (confirm clean PDF build)
```
