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

## Native MCP Tools & Standalone Mode

Invoke `scifi_compile_latex` (or `scifi compile <entrypoint>`) directly. Both work on **standalone `.tex` files with zero project setup**—no `scifi init`, `scifi.toml`, or `.scifi/` directory is required, and `~/.scifi/config.json` is auto-created silently when caching `latex_bin_dir`.

### `scifi_compiler_info`
Inspect the active LaTeX toolchain and PDF visual renderer without running a build (reports `distribution`, `engine`, `engine_path`, `bin_dir`, `version`, `available_engines`, `cached`, and `pdf_renderer`).

### `scifi_compile_latex`
Autonomously compile LaTeX manuscripts with cached toolchain discovery, automated log error parsing, compiler metadata, and optional PDF-to-PNG rendering.

---

## Self-Recovery (`COMPILER_NOT_FOUND` / Off-PATH TeX)

If `scifi_compile_latex` returns `COMPILER_NOT_FOUND` (for example, when the MCP server is running an older build or TeX is installed off-`PATH`), **do not stop or tell the user LaTeX is missing** without running these automatic recovery steps:

1. **Try the local `scifi` CLI:** Run `scifi compile "<entrypoint>"` (or `uv run scifi compile "<entrypoint>"` from the `scifi` repo). It uses `discover_tex_toolchain()`, auto-creates `~/.scifi/config.json` if needed, and caches `latex_bin_dir`.
2. **Probe standard off-`PATH` TeX directories directly:** If the CLI is unavailable or still returns `COMPILER_NOT_FOUND`, check standard installation paths without user interaction:
   - **Windows:** `%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64`, `C:\Program Files\MiKTeX\miktex\bin\x64`, `C:\texlive\*\bin\windows`, `%APPDATA%\TinyTeX\bin\windows`
   - **macOS:** `/Library/TeX/texbin`, `~/Library/TinyTeX/bin/universal-darwin`, `/usr/local/texlive/*/bin/universal-darwin`
   - **Linux:** `/usr/local/texlive/*/bin/*`, `~/.TinyTeX/bin/*`
3. **Compile & cache:** Prepend the discovered `bin_dir` to `PATH` for the compile command, run `latexmk`/`xelatex`/`pdflatex` in the `.tex` file's directory, and persist it with `scifi config set latex_bin_dir "<bin_dir>"` (if `scifi` is available).
4. **Report missing only after exhausting fallbacks:** Only ask the user to install MiKTeX/TeX Live if all checks above find no TeX binaries.

```json
{
  "entrypoint": "path/to/main.tex",
  "engine": "auto",
  "clean": true,
  "render_pages": false
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `entrypoint` | string | Yes | Path to the root `.tex` manuscript file |
| `engine` | string | No | Compiler engine: `"auto"`, `"latexmk"` (default), `"pdflatex"`, `"xelatex"`, or `"lualatex"` |
| `clean` | boolean | No | Whether to clean auxiliary files (`.aux`, `.log`, `.out`, etc.) upon completion (default: `true`) |
| `render_pages` | boolean | No | Render compiled PDF pages to PNG screenshots for visual inspection (default: `false`) |
| `render_dpi` | integer | No | DPI for rendered PNGs when `render_pages=true` (default: `150`) |
| `max_render_pages` | integer | No | Max pages to render when `render_pages=true` (default: `10`) |

---

## Output Fields

```json
{
  "status": "SUCCESS | COMPILATION_ERROR | COMPILER_NOT_FOUND",
  "pdf_path": "path/to/main.pdf",
  "engine": "latexmk",
  "engine_path": "C:/Users/.../MiKTeX/miktex/bin/x64/latexmk.exe",
  "distribution": "MiKTeX",
  "compiler_version": "Latexmk, John Collins, ...",
  "duration_seconds": 2.14,
  "page_count": 8,
  "errors": [
    {"file": "main.tex", "line": 42, "message": "Undefined control sequence."}
  ],
  "missing_packages": ["algorithm2e.sty"],
  "undefined_citations": ["Smith2020"],
  "undefined_references": ["fig:overview"],
  "layout_warnings": {"overfull_hbox": 3, "underfull_hbox": 1},
  "rendered_pages": [
    {"page": 1, "image_path": ".../.scifi_renders/main/main_page-1.png", "width": 1275, "height": 1650}
  ]
}
```

Always report the compiler used (`distribution`, `engine`, `engine_path`, `duration_seconds`, `page_count`) to the user.

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
