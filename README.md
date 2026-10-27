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
| [`human`](#-human--academic-prose-humanizer) | Rewrite AI-generated text into objective academic prose |
| [`turing`](#-turing--mathematical-derivation-verifier) | Verify derivations, units, matrix shapes, limits, convexity, and notation in LaTeX |

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

## 🧮 Turing — Mathematical Derivation Verifier

Catches silent algebra errors in LaTeX manuscripts using SymPy, pint, and NumPy. All verifiers output structured JSON and are callable from the agent or directly from the terminal.

### 1. Derivative Verification

```bash
uv run python skills/turing/scripts/verify_derivation.py \
    --expr    "\frac{1}{2} x^2 + \sin(x)" \
    --var     "x" \
    --claimed "x + \cos(x)"
```

Computes $\frac{d}{dx}f$ symbolically and checks `simplify(computed − claimed) = 0`.

**Status codes:** `VALID` · `INVALID_DERIVATION`

---

### 2. Dimensional / Unit Consistency

```bash
# Both sides must reduce to the same physical dimension
uv run python skills/turing/scripts/verify_units.py \
    --lhs "5 watt * second" --rhs "5 joule" --check eq

# All additive terms must be unit-compatible
uv run python skills/turing/scripts/verify_units.py \
    --lhs "10 meter / second, 3 kilometer / second" --check add
```

**Status codes:** `VALID` · `DIMENSION_MISMATCH`

---

### 3. Matrix Dimension & Tensor Shape

```bash
uv run python skills/turing/scripts/verify_matrix_shapes.py \
    --matrices "A:m:n,B:n:k,C:m:k" \
    --expr     "A * B - C"
```

Validates matrix products symbolically (no concrete values needed). Dimension tokens like `m`, `n`, `k` are treated as generic positive integers.

**Status codes:** `VALID` · `SHAPE_ERROR`

---

### 4. Boundary & Asymptotic Behaviour

```bash
# lim_{N→∞} 1/N = 0 ?
uv run python skills/turing/scripts/verify_limits.py \
    --expr "\frac{1}{N}" --var "N" --point "oo" --claimed "0"

# One-sided limit: lim_{x→0⁺} 1/x = ∞ ?
uv run python skills/turing/scripts/verify_limits.py \
    --expr "\frac{1}{x}" --var "x" --point "0" --dir "+" --claimed "oo"
```

Supported `--point` values: any number, `oo`, `-oo`. Direction: `+`, `-`, or omit for two-sided.

**Status codes:** `VALID` · `INVALID_LIMIT`

---

### 5. Positive Definiteness & Convexity

```bash
uv run python skills/turing/scripts/verify_convexity.py \
    --expr    "x^2 + y^2 + x*y" \
    --vars    "x,y" \
    --claimed "strictly_convex"
```

Computes the symbolic Hessian $H_{ij} = \frac{\partial^2 f}{\partial x_i \partial x_j}$ and applies Sylvester's criterion. Always reports the Hessian matrix and its eigenvalues.

`--claimed`: `strictly_convex` · `convex` · `indefinite`

**Status codes:** `VALID` · `INVALID_CONVEXITY_CLAIM`

---

### 6. Equation-to-Plot Numerical Sanity

```bash
uv run python skills/turing/scripts/verify_numerical.py \
    --expr      "\frac{1}{1 + x^2}" \
    --var       "x" \
    --sweep     "0,1,2,3,4" \
    --simulated "[1.0, 0.5, 0.2, 0.1, 0.058]" \
    --rtol      1e-2
```

Converts the closed-form expression to a numerical function via `lambdify`, sweeps it over the provided parameter values, and checks agreement with simulation data using `np.allclose`.

**Status codes:** `VALID` · `NUMERICAL_MISMATCH`

---

### 7. Notation Consistency

```bash
uv run python skills/turing/scripts/verify_notation.py --file paper.tex
```

Scans all `$...$`, `$$...$$`, `equation`, `align`, and `multline` environments. Flags symbols appearing in multiple font/case variants across sections (e.g. $P_t$, $p(t)$, $\mathbf{P}$, $\mathcal{P}$). Produces a full cross-section symbol manifest.

**Status codes:** `VALID` · `NOTATION_INCONSISTENCY`

---

### Turing Output Reference

| Status | What it means | Key fields in output |
|---|---|---|
| `VALID` | Claim verified | — |
| `INVALID_DERIVATION` | Wrong derivative | `computed_derivative`, `discrepancy` |
| `DIMENSION_MISMATCH` | Incompatible units | `lhs_dimensionality`, `rhs_dimensionality` |
| `SHAPE_ERROR` | Matrix dims don't align | `error_message` |
| `INVALID_LIMIT` | Limit claim is false | `computed_limit`, `discrepancy` |
| `INVALID_CONVEXITY_CLAIM` | Hessian contradicts claim | `hessian`, `eigenvalues`, `actual_property` |
| `NUMERICAL_MISMATCH` | Analytical ≠ simulation | `max_abs_error`, `worst_at_x` |
| `NOTATION_INCONSISTENCY` | Symbol used inconsistently | `multi_variant_symbols`, `symbol_manifest` |
| `ERROR` | Parse or runtime failure | `error_message`, `hint` |

---

## Testing

```bash
uv run python -m unittest tests/test_citation_verifier.py
```

---

## Dependencies

| Package | Used by |
|---|---|
| `requests` | alex — HTTP registry queries |
| `bibtexparser` | alex — `.bib` file parsing |
| `sympy` + `antlr4-python3-runtime==4.11.0` | turing — symbolic math & LaTeX parsing |
| `pint` | turing — physical unit checking |
| `numpy` | turing — numerical sanity checks |
