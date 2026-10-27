---
name: compiler
description: Autonomous LaTeX engine. Compiles manuscripts using latexmk/pdflatex, isolates compilation errors with exact file and line numbers, auto-installs missing TeX packages via tlmgr/mpm/winget, and flags undefined citations and broken cross-references.
compatibility: python3, latexmk or pdflatex (MiKTeX / TeX Live)
---

## When to Use
- Compiling any LaTeX manuscript into PDF.
- Diagnosing why a `.tex` document fails to build or throws fatal errors.
- Auditing missing packages, broken `\ref{}` / `\label{}` pairs, or undefined `\cite{}` keys.
- Running as the final build-check step after `turing` verifies math or `alex` audits citations.

---

## Compilation Script

The single script lives at `skills/compiler/scripts/compile_latex.py`.  
All output is structured JSON — no raw log flooding.

### Basic usage

```bash
uv run python skills/compiler/scripts/compile_latex.py --tex "path/to/main.tex"
```

### Disable auto-install (dry-run mode)

```bash
uv run python skills/compiler/scripts/compile_latex.py --tex "main.tex" --no-auto-fix
```

| Flag | Default | Description |
|---|---|---|
| `--tex` | *(required)* | Path to the root `.tex` file |
| `--no-auto-fix` | off | Skip automatic `tlmgr`/`mpm` package installation |

---

## Output Fields

```json
{
  "status":                "SUCCESS | FAILED | ENGINE_MISSING | TIMEOUT | FILE_NOT_FOUND | ERROR",
  "pdf_generated":         true,
  "pdf_path":              "/absolute/path/to/main.pdf",
  "engine":                "latexmk | pdflatex",
  "errors":                [{"file": "main.tex", "line": 42, "message": "Undefined control sequence."}],
  "missing_packages":      ["algorithm2e.sty"],
  "undefined_citations":   ["Smith2020"],
  "undefined_references":  ["fig:overview"],
  "layout_warnings":       {"overfull_hbox": 3, "underfull_hbox": 1},
  "raw_log_tail":          "..."
}
```

`raw_log_tail` is only present on `FAILED` — the last 30 lines of the compiler log.

---

## Status Codes & Agent Actions

| Status | Meaning | Agent Action |
|---|---|---|
| `SUCCESS` | PDF built cleanly | Report `pdf_path`; list any non-fatal warnings (undefined refs/cites, layout) |
| `FAILED` | Build aborted | Navigate to each `errors[].file : errors[].line`, fix the syntax error, recompile |
| `ENGINE_MISSING` | No `latexmk`/`pdflatex` on PATH | Run the `action_required.install_command` returned in the JSON |
| `FILE_NOT_FOUND` | `.tex` path does not exist | Verify the path and rerun |
| `TIMEOUT` | Build exceeded 180 s | Check for infinite loops in custom macros; try `--no-auto-fix` |
| `ERROR` | Unexpected runtime exception | Surface `error` field to the user |

---

## Auto-Fix Behaviour

1. **Missing packages** (`! LaTeX Error: File '…' not found`):  
   - TeX Live: runs `tlmgr install <pkg>` then recompiles once.  
   - MiKTeX (Windows): the `--enable-installer` flag downloads packages on demand; `mpm --install=<pkg>` is the fallback.  
   - If installation fails, `missing_packages` is reported and the agent should prompt the user.

2. **Engine bootstrap**:  
   - Windows without any TeX: invokes `winget install MiKTeX.MiKTeX --silent`.  
   - Linux without any TeX: returns the exact `apt install` line for the agent to execute.

---

## Integration with Other Skills

```
turing   → verify math   → compiler → confirm PDF builds cleanly
alex     → audit .bib    → compiler → catch \cite{} key mismatches in log
human    → rewrite prose → compiler → validate no LaTeX syntax was broken
```

Typical chained workflow:

```bash
# 1. Verify derivations
uv run python skills/turing/scripts/verify_derivation.py --expr "..." --var "x" --claimed "..."

# 2. Audit citations
uv run python skills/alex/scripts/verify_citations.py --bib refs.bib

# 3. Compile and confirm
uv run python skills/compiler/scripts/compile_latex.py --tex main.tex
```
