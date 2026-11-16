# CLI Reference

SciFi provides two command-line binary aliases: `sf` and `scifi`. Both provide access to the full suite of subcommands.

---

## Command Overview

| Command | Description |
|---|---|
| `sf doctor` | Run the 6-stage Manuscript Readiness Pipeline or environment diagnostics |
| `sf verify` | Verify an academic citation by DOI, arXiv ID, or title |
| `sf audit` | Audit an entire `.bib` bibliography file against registries |
| `sf search` | Search OpenAlex and Crossref for canonical literature |
| `sf argus` | Scan LaTeX manuscripts for uncredited methods and attribution gaps |
| `sf math` | Verify symbolic mathematical calculus, derivations, units, and limits |
| `sf stats` | Validate numerical simulation curves and audit statistical significance |
| `sf review` | Popper adversarial peer-review and unstated assumptions hunting |
| `sf shannon` | Audit title length, 5-beat abstract structure, and SEO keywords |
| `sf human` | Scan and humanize academic prose and LaTeX source ergonomics |
| `sf table` | Generate publication-grade LaTeX `booktabs` tables |
| `sf venue` | Audit venue formatting compliance and double-blind anonymization |
| `sf figures` | Da-Vinci visual accessibility and 300+ DPI figure auditor |
| `sf trim` | Layout assistant for recovering page lines without negative `\vspace` |
| `sf proofs` | Euclid theorem-proof completeness and appendix reference checker |
| `sf repro` | Bacon conference reproducibility and open-science checklist auditor |
| `sf rebuttal` | Generate disciplined 4-beat rebuttal scaffolding and LaTeX diffs |
| `sf submission` | Generate cover letters, highlights, title pages, and anonymous code bundles |
| `sf zotero` | Inspect local Zotero library, sync collections, and push audit notes |
| `sf literature` | Hypatia lineage discovery graph, gap analysis, and central knowledge store |
| `sf scaffold` | Scaffold a standard 2-pillar SciFi research project workspace |
| `sf compile` | Autonomously compile LaTeX manuscripts with log diagnostic parsing |
| `sf setup` | Automatically configure Google Antigravity (`~/.gemini/config/mcp_config.json` or `.agents/mcp_config.json`) |
| `sf ui` | Launch the browser-based research cockpit UI |

---

## Detailed Command Flags

### `sf doctor`
```bash
sf doctor [TARGET] [OPTIONS]
```
- `TARGET`: Main LaTeX file (`main.tex`) or workspace directory.
- `--bib FILE`: Explicit path to `.bib` bibliography file.
- `--venue VENUE`: Target venue profile (`ieee`, `acm`, `elsevier`, `springer`, `neurips`, `icml`, `openreview`).
- `--double-blind`: Enforce double-blind review checks.
- `--compile`: Attempt LaTeX build compilation during the audit.
- `--env`: Run environment and toolchain diagnostics instead of manuscript audit.
- `--fix`: Automatically attempt toolchain fixes during diagnostics.

### `sf math`
```bash
# Derivative verification
sf math derivative "<EXPRESSION>" <VARIABLE> "<CLAIMED_DERIVATIVE>"

# Calculus step equivalence
sf math step "<LHS>" "<RHS>" [--assumptions "<ASSUMPTIONS>"]

# Dimensional unit homogeneity
sf math units "<EXPRESSION>" [--mode strict|tolerant]

# Matrix shape compatibility
sf math shapes "<EXPRESSION>" --shapes '{"A": [3, 4], "B": [4, 5]}'

# Analytical limits
sf math limits "<EXPRESSION>" <VARIABLE> --tends-to <POINT> --expected <VALUE>

# Convexity verification
sf math convexity "<EXPRESSION>" "<VARIABLES>"
```

### `sf stats`
```bash
# Curve fitting & theoretical alignment
sf stats curve --formula "<FORMULA>" --var-name <VAR> --data-path <CSV_OR_JSON> [--tolerance 0.01]

# Statistical sample auditing
sf stats audit --values "<NUMBERS_OR_FILE>" [--confidence 0.95]
```

### `sf submission`
```bash
# Research highlights validation
sf submission highlights --bullets "Bullet 1|Bullet 2|Bullet 3" --venue elsevier

# Standalone double-blind title page
sf submission title-page --venue ieee --target main.tex --output title_page.tex

# Editorial cover letter
sf submission letter --journal "IEEE Trans. on AI" --target main.tex

# Anonymous code ZIP packaging
sf submission pack-code --code-dir ./code --output anonymous_code.zip

# Complete submission bundle
sf submission bundle --target main.tex --venue elsevier --output ./submission_bundle
```
