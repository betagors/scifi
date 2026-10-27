---
name: turing
description: Verify mathematical derivations, gradients, and symbolic differentiations in LaTeX manuscripts using SymPy. Use when auditing calculus steps, optimality conditions, or checking if mathematical equations hold.
compatibility: python3, sympy, pint, numpy
---

## When to Use
- Validating claimed gradients, Jacobians, or first-order optimality conditions ($\nabla f(x) = 0$).
- Checking derivations in proofs, state equations, or Hamilton-Jacobi-Bellman (HJB) systems.
- Verifying step-by-step calculus before inserting proofs into paper drafts.
- Catching dimensional inconsistencies (Watts vs. Joules), matrix shape mismatches, divergent limits, indefinite Hessians, analytical-vs-simulation deviations, or symbol-notation drift across sections.

---

## Verifier Scripts

All scripts live in `skills/turing/scripts/` and output structured JSON.

### 1. Derivative Verification — `verify_derivation.py`

Check whether a claimed derivative $f'_{\text{claimed}}$ equals $\frac{d}{dx}f$.

```bash
uv run python skills/turing/scripts/verify_derivation.py \
    --expr    "\\frac{1}{2} x^2 + \\sin(x)" \
    --var     "x" \
    --claimed "x + \\cos(x)"
```

| Arg | Description |
|---|---|
| `--expr` | Original function $f$ in LaTeX |
| `--var` | Differentiation variable |
| `--claimed` | Author's claimed derivative in LaTeX |

**Status codes:** `VALID` · `INVALID_DERIVATION` · `ERROR`

---

### 2. Dimensional / Unit Consistency — `verify_units.py`

Assert that both sides of an equation share the same physical dimension, or that additive terms are unit-compatible.

```bash
# Equality check
uv run python skills/turing/scripts/verify_units.py \
    --lhs "5 watt * second" --rhs "5 joule" --check eq

# Additive compatibility (comma-separated terms in --lhs)
uv run python skills/turing/scripts/verify_units.py \
    --lhs "10 meter / second, 3 kilometer / second" --check add
```

| Arg | Description |
|---|---|
| `--lhs` | LHS expression, or comma-separated terms for `add` mode |
| `--rhs` | RHS expression (required for `eq` mode) |
| `--check` | `eq` (default) or `add` |

**Status codes:** `VALID` · `DIMENSION_MISMATCH` · `ERROR`

---

### 3. Matrix Dimension & Tensor Shape — `verify_matrix_shapes.py`

Validate symbolic matrix products without substituting concrete numbers. Raises `SHAPE_ERROR` if inner dimensions do not align.

```bash
uv run python skills/turing/scripts/verify_matrix_shapes.py \
    --matrices "A:m:n,B:n:k,C:m:k" \
    --expr     "A * B - C"
```

| Arg | Description |
|---|---|
| `--matrices` | Comma-separated `NAME:ROWS:COLS` specs; dimension tokens are symbolic by default |
| `--expr` | Python-style matrix expression using declared names |

**Status codes:** `VALID` · `SHAPE_ERROR` · `ERROR`

---

### 4. Boundary & Asymptotic Behaviour — `verify_limits.py`

Check whether a claimed limit value is correct; detects false convergence claims and singularities.

```bash
# Two-sided limit as N → ∞
uv run python skills/turing/scripts/verify_limits.py \
    --expr "\\frac{1}{N}" --var "N" --point "oo" --claimed "0"

# One-sided limit from the right as x → 0⁺
uv run python skills/turing/scripts/verify_limits.py \
    --expr "\\frac{1}{x}" --var "x" --point "0" --dir "+" --claimed "oo"
```

| Arg | Description |
|---|---|
| `--expr` | Expression in LaTeX |
| `--var` | Limit variable |
| `--point` | Limit point: a number, `oo`, or `-oo` |
| `--claimed` | Claimed limit value (LaTeX or `oo`/`-oo`) |
| `--dir` | `+` (right), `-` (left), or omit for two-sided |

**Status codes:** `VALID` · `INVALID_LIMIT` · `ERROR`

---

### 5. Positive Definiteness & Convexity — `verify_convexity.py`

Compute the symbolic Hessian $H_{ij} = \frac{\partial^2 f}{\partial x_i \partial x_j}$, apply Sylvester's criterion for positive definiteness, and compare against the author's claim.

```bash
uv run python skills/turing/scripts/verify_convexity.py \
    --expr    "x^2 + y^2 + x*y" \
    --vars    "x,y" \
    --claimed "strictly_convex"
```

| Arg | Description |
|---|---|
| `--expr` | Scalar function $f$ in LaTeX |
| `--vars` | Comma-separated variable names |
| `--claimed` | `strictly_convex` · `convex` · `indefinite` |

**Status codes:** `VALID` · `INVALID_CONVEXITY_CLAIM` · `ERROR`

---

### 6. Equation-to-Plot Numerical Sanity — `verify_numerical.py`

Convert a closed-form symbolic expression to a numerical function via `lambdify`, sweep it over parameter values, and check agreement with simulation output within tolerance.

```bash
uv run python skills/turing/scripts/verify_numerical.py \
    --expr      "\\frac{1}{1 + x^2}" \
    --var       "x" \
    --sweep     "0,1,2,3,4" \
    --simulated "[1.0, 0.5, 0.2, 0.1, 0.058]" \
    --rtol      1e-2
```

| Arg | Description |
|---|---|
| `--expr` | Closed-form expression in LaTeX |
| `--var` | Sweep variable name |
| `--sweep` | Comma-separated parameter values |
| `--simulated` | JSON array of simulation outputs (same length as sweep) |
| `--rtol` | Relative tolerance (default `1e-3`) |
| `--atol` | Absolute tolerance (default `1e-6`) |

**Status codes:** `VALID` · `NUMERICAL_MISMATCH` · `ERROR`

---

### 7. Notation Consistency — `verify_notation.py`

Scan all math environments in a `.tex` file. Flags symbols that appear in multiple font/case variants across sections (e.g. $P_t$ vs $p(t)$ vs $\mathbf{P}$). Produces a full cross-section symbol manifest.

```bash
uv run python skills/turing/scripts/verify_notation.py --file paper.tex
```

| Arg | Description |
|---|---|
| `--file` | Path to the `.tex` manuscript |

**Status codes:** `VALID` · `NOTATION_INCONSISTENCY` · `ERROR`

---

## Output Interpretation

| Status | Meaning | Agent Action |
|---|---|---|
| `VALID` | Claim is verified | Report confirmation to user |
| `INVALID_DERIVATION` | Derivative is wrong | Show `computed_derivative` and `discrepancy` |
| `DIMENSION_MISMATCH` | Units are incompatible | Report `lhs_dimensionality` vs `rhs_dimensionality` |
| `SHAPE_ERROR` | Matrix inner dims don't align | Report which product failed |
| `INVALID_LIMIT` | Limit claim is false | Show `computed_limit` and divergence hint if applicable |
| `INVALID_CONVEXITY_CLAIM` | Hessian definiteness contradicts claim | Show `hessian` and `eigenvalues` |
| `NUMERICAL_MISMATCH` | Analytical curve deviates from simulation | Report `max_abs_error` and `worst_at_x` |
| `NOTATION_INCONSISTENCY` | Symbol used in multiple forms | List `multi_variant_symbols` with sections |
| `ERROR` | Parse or runtime failure | Surface `error_message` and `hint` to user |
