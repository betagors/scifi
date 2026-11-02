# SciFi — Scientific Research & Academic Writing Toolkit

**SciFi** is an [Antigravity](https://antigravity.google) plugin for rigorous academic work: verifying citations, humanizing AI-generated prose, auditing mathematical derivations, and enforcing notation consistency across LaTeX manuscripts.

```
uv sync        # install all dependencies
```

Requires Python ≥ 3.12 and [`uv`](https://docs.astral.sh/uv/).

---

## Skills

| Skill | Purpose |
|---|---|
| [`alex`](#-alex--citation--literature-verifier) | Verify citations, DOIs, and `.bib` files against global registries |
| [`argus`](#-argus--academic-attribution--plagiarism-sentinel) | Audit manuscripts for uncredited methods, plagiarism, and informal web articles |
| [`human`](#-human--academic-prose-humanizer) | Rewrite AI-generated text into objective academic prose |
| [`turing`](#-turing--mathematical-derivation-verifier) | Verify derivations, units, matrix shapes, limits, convexity, and notation in LaTeX |
| [`gauss`](#-gauss--numerical-sanity--statistical-auditing) | Verify theoretical curves against simulation traces and audit CLT sample size ($N \ge 30$) |
| [`popper`](#-popper--adversarial-peer-review--claim-auditor) | Hostile peer-review simulation, unstated assumption hunting, and baseline fairness audits |
| [`compiler`](#-compiler--autonomous-latex-engine) | Compile manuscripts with latexmk/pdflatex, isolate file:line errors, and auto-install packages |
| [`hypatia`](#-hypatia--literature-synthesis--gap-analysis) | Download open-access PDFs, extract text, and synthesize delta-novelty matrices |

---

## 🛡️ Argus — Academic Attribution & Plagiarism Sentinel

Audits manuscripts, sections, or individual paragraphs for attribution gaps, uncredited scientific methods, and copied web/blog content. Categorizes findings into:

- **`CANONICAL_ACADEMIC`:** Specific algorithm or technique lacking citation -> queries OpenAlex/Crossref, generates verified BibTeX, and injects `\cite{...}`.
- **`COMMON_KNOWLEDGE`:** Universal concepts (e.g. *gradient descent*, *Fourier transform*, *backpropagation*) -> suppresses false alarms.
- **`INFORMAL_WEB`:** Text or explanation derived from an online article, tutorial, or blog -> dispatches to `human` for academic reformulation or traces back to primary literature.
- **`PREPRINT_ALIGNMENT`:** Overlap matching author's own preprints or previous papers -> flags as self-reference to ensure proper lineage.

### CLI

```bash
# Audit a LaTeX manuscript
uv run scifi argus audit paper.tex --bib references.bib

# Automatically inject citations in-place into paper.tex and update references.bib
uv run scifi argus audit paper.tex --bib references.bib --fix

# Scan a raw text excerpt or paragraph
uv run scifi argus scan "We use Low-Rank Adaptation to parameterize weight updates."

# Search canonical academic paper for a method
uv run scifi argus search "FlashAttention" --format bibtex
```

### Python API

```python
from scifi.argus import ArgusEngine

engine = ArgusEngine()
report = engine.audit_text("We optimize the model using AdamW optimizer.")
print(f"Academic gaps: {report.academic_count}")
for finding in report.findings:
    print(finding.matched_entity, finding.suggested_action, finding.cite_key)
```

---

## 🔍 Alex — Citation & Literature Verifier

Validates academic citations against **Crossref**, **OpenAlex**, **arXiv**, and **DataCite**. Works on individual DOIs/links or entire `.bib` files.

**Detects:**
- Retracted papers, expressions of concern, and published errata
- Title, author, and year discrepancies vs. registry records
- Missing DOIs and hallucinated references

**Generates:** Clean BibTeX (predictable `[Author][Year][Word]` citekeys) and APA 7th edition citations.

### CLI

```bash
# Verify a single DOI or link
uv run scifi verify 10.1038/s41586-020-2649-2
uv run scifi verify https://arxiv.org/abs/1706.03762 --format bibtex

# Check claimed metadata against the registry record
uv run scifi verify 10.1038/s41586-020-2649-2 \
  --claimed-title "NumPy in Python" \
  --claimed-year 2018 \
  --claimed-author "Smith"

# Audit and sanitize an entire .bib file
uv run scifi audit references.bib \
  --output-report audit_report.md \
  --output-bib clean_references.bib

# Search registries by title
uv run scifi search "Attention is all you need" --verify
```

Output formats: `markdown` (default) · `bibtex` · `apa` · `json` · `text`

### Python API

```python
from scifi.citation_verifier import verify_citation, audit_bib_file

result = verify_citation("10.1038/s41586-020-2649-2")
print(result.status)        # VerificationStatus.VERIFIED
print(result.is_retracted)  # False
print(result.to_bibtex())   # Standard BibTeX entry
print(result.to_apa())      # APA 7th edition string

report = audit_bib_file("my_paper.bib")
print(f"Retracted: {report.retracted_count} / {report.total_entries}")
print(report.summary_markdown())
```

### Status Codes

| Status | Meaning |
|---|---|
| `VERIFIED` | Active, peer-reviewed or preprint work found in registry |
| `RETRACTED` | Formally retracted by publisher or authors |
| `ERRATA_EXISTS` | Correction or expression of concern published |
| `MISMATCH` | Citation found but metadata deviates from claimed values |
| `UNRESOLVED` | Could not locate identifier in any registry |

---

## ✍️ Human — Academic Prose Humanizer

Rewrites AI-generated text into rigorous, objective, human-authored academic prose. Follows the **Master Academic Humanizer** protocol: eliminates AI-isms, marketing fluff, and em dashes; enforces passive voice, hedging, and discipline-specific conventions.

**Triggers:** Ask the agent to *humanize*, *de-AI*, or *rewrite for a journal* any piece of text.

**Removes:** Hollow openers ("In this paper, we…"), superlatives ("groundbreaking"), certainty over-claims, bullet-point padding, and ChatGPT-style transitional phrases.

**Enforces:** Passive constructions, epistemic hedges ("it is suggested that…"), precise quantification, and citation-backed claims.

---

## ⚡ FastMCP Server & Integration

SciFi embeds a high-performance FastMCP server daemon implementing 17 deterministic verification tools across literature, mathematics, statistics, compilation, and review.

### Native Plugin Integration (`mcp_config.json`)
The repository includes a root `mcp_config.json` configuration file, allowing Antigravity to discover and load the server automatically:
```json
{
  "mcpServers": {
    "scifi": {
      "command": "uv",
      "args": ["run", "python", "-m", "scifi.server"]
    }
  }
}
```

### Automatic Setup Installer
Configure SciFi in Antigravity, Claude Desktop, and Cursor with a single command:
```bash
# Interactive setup
uv run scifi setup

# Non-interactive / automated installation
uv run scifi setup --auto
```

### Running the Server Daemon
```bash
# Standard stdio transport
uv run scifi server

# Or via Python module directly
uv run python -m scifi.server
```

### Available FastMCP Tools
| Tool | Domain | Description |
|---|---|---|
| `scifi_verify_citation` | Literature | Verify DOI/link against Crossref/OpenAlex/arXiv with cached canonical metadata |
| `scifi_audit_bib` | Literature | Audit `.bib` file for retractions, errata, and metadata mismatches |
| `scifi_search_literature` | Literature | Search OpenAlex and academic registries for canonical literature |
| `scifi_audit_attribution` | Attribution | Audit LaTeX manuscripts for uncredited methods, plagiarism, and auto-cite |
| `scifi_verify_derivative` | Mathematics | Check that $\frac{d}{dx}f(x)$ matches claimed results symbolically via SymPy |
| `scifi_verify_derivation_step` | Mathematics | Audit step-by-step calculus derivation equivalence |
| `scifi_check_units` | Mathematics | Dimensional consistency checking via Pint (`eq` or `terms` mode) |
| `scifi_check_matrix_shapes` | Mathematics | Matrix product and tensor contraction shape verification with AST validation |
| `scifi_check_limits` | Mathematics | Asymptotic boundary and one-sided limit verification |
| `scifi_check_convexity` | Mathematics | Symbolic Hessian definiteness test (convex, strictly convex, concave, strictly concave) |
| `scifi_check_notation` | Mathematics | Cross-section LaTeX mathematical notation consistency scanner |
| `scifi_compile_latex` | Compilation | Autonomous `latexmk`/`pdflatex` compilation and error log diagnosis |
| `scifi_verify_curve` | Statistics | Match theoretical closed-form LaTeX expressions with simulation data |
| `scifi_audit_statistics` | Statistics | Compute mean, std err, 95% CI, and audit CLT sample size ($N \ge 30$) |
| `scifi_audit_claims` | Peer Review | Scan manuscript for unhedged overclaims and fragile assumptions |
| `scifi_fetch_paper_pdf` | Retrieval | Fetch open-access PDF by DOI or arXiv ID |
| `scifi_extract_pdf_text` | Retrieval | Extract structured text and sections from paper PDFs |

---

## 🧮 Turing — Mathematical Derivation Verifier

Catches silent algebra errors in LaTeX manuscripts using SymPy, Pint, and NumPy. Available as native FastMCP tools and Python library functions (`from scifi.math import ...`).

### 1. Derivative Verification (`scifi_verify_derivative`)
Computes $\frac{d}{dx}f$ symbolically and checks `simplify(computed − claimed) = 0`.
```python
from scifi.math import verify_derivative

result = verify_derivative(
    expr=r"\frac{1}{2} x^2 + \sin(x)",
    var="x",
    claimed=r"x + \cos(x)",
)
print(result["status"])  # VALID
```

### 2. Dimensional / Unit Consistency (`scifi_check_units`)
Ensures equations match physical dimensions or that all additive terms share identical dimensionality.
```python
from scifi.math import check_units

# Equation equality mode
res_eq = check_units(lhs="5 watt * second", rhs="5 joule", check_mode="eq")

# Additive terms mode
res_add = check_units(lhs="10 meter / second, 3 kilometer / second", check_mode="terms")
```

### 3. Matrix Dimension & Tensor Shape (`scifi_check_matrix_shapes`)
Validates matrix products symbolically with safe AST parsing.
```python
from scifi.math import check_matrix_shapes

result = check_matrix_shapes(
    operation="A * B.T",
    dimensions={"A": ["m", "n"], "B": ["k", "n"]},
)
print(result["result_shape"])  # ['m', 'k']
```

### 4. Boundary & Asymptotic Behaviour (`scifi_check_limits`)
Validates asymptotic limits ($N \to \infty$) and one-sided limits ($x \to 0^+$).
```python
from scifi.math import check_limits

result = check_limits(
    expr=r"\frac{1}{x}",
    var="x",
    point="0",
    claimed="oo",
    direction="+",
)
```

### 5. Positive Definiteness & Convexity (`scifi_check_convexity`)
Computes the symbolic Hessian and tests positive or negative definiteness via Sylvester's criterion.
Supports `strictly_convex`, `convex`, `strictly_concave`, `concave`, and `indefinite`.
```python
from scifi.math import check_convexity

result = check_convexity(
    expr=r"x^2 + y^2 + x y",
    var="x, y",
    claimed="strictly_convex",
)
```

### 6. Notation Consistency (`scifi_check_notation`)
Scans all math environments in a LaTeX document for symbol variance and collision.
```python
from scifi.math import check_notation

result = check_notation(tex_path="paper.tex")
```

---

## 📈 Gauss — Numerical Sanity & Statistical Auditing

Validates empirical results and audits statistical rigor in scientific manuscripts.

### 1. Curve Verification (`scifi_verify_curve`)
Verifies closed-form theoretical formulas against empirical simulation datasets (CSV/JSON or inline arrays) with relational equation parsing and power syntax support:
```python
from scifi.stats import verify_curve

result = verify_curve(
    formula_latex=r"y = \frac{1}{1 + x^2}",
    var_name="x",
    x_vals=[0.0, 1.0, 2.0, 3.0],
    y_vals=[1.0, 0.5, 0.2, 0.1],
)
```

### 2. Statistical Auditing (`scifi_audit_statistics`)
Audits sample size against Central Limit Theorem ($N \ge 30$), computing mean, standard error, and confidence intervals:
```python
from scifi.stats import audit_statistics

result = audit_statistics(samples=[12.1, 12.4, 12.2, 12.9, 12.5], confidence=0.95)
print(result["is_statistically_sound"])  # False (N < 30)
```

---

## 🏗️ Compiler — Autonomous LaTeX Engine

Compiles manuscripts, isolates build errors with exact `file:line` locations, and auto-detects missing packages.

```bash
# Compile via unified CLI
uv run scifi compile paper.tex

# Or invoke the scifi_compile_latex MCP tool
```

---

## 🔬 Popper — Adversarial Peer-Review & Claim Auditor

Stress-tests manuscripts for unstated assumptions, unsupported claims, and weak baselines.

```bash
# Scan manuscript for overclaims and fragile assumptions
uv run python -c "from scifi.review import audit_claims; print(audit_claims('paper.tex'))"

# Or invoke the scifi_audit_claims MCP tool
```

---

## 🧪 Testing

Run the comprehensive test suite across all modules:

```bash
uv run pytest tests/ -v
```

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `mcp` | FastMCP server implementation |
| `requests` | HTTP academic registry queries |
| `bibtexparser` | BibTeX parsing and sanitization |
| `sympy` + `antlr4-python3-runtime` | Symbolic mathematics & LaTeX parsing |
| `pint` | Physical unit and dimension checking |
| `numpy` & `scipy` | Numerical curve verification & statistics |
| `pypdf` | Open-access PDF text extraction |
| `pytest` | Test runner and test suite |
