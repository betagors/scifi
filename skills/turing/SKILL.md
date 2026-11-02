---
name: turing
description: Verify mathematical derivations, gradients, and symbolic differentiations in LaTeX manuscripts using SymPy. Use when auditing calculus steps, optimality conditions, or checking if mathematical equations hold.
---

# Turing: Symbolic Mathematics & Theoretical Rigor

The `turing` skill provides symbolic mathematics, proof auditing, and dimensional validation for academic manuscripts. It exposes native MCP tools powered by SymPy, Pint, and NumPy to verify calculus derivations, algebraic equivalence, physical units, matrix shapes, limits, convexity, and symbol notation consistency.

## When to Use
- Validating claimed gradients, Jacobians, or first-order optimality conditions ($\nabla f(x) = 0$).
- Checking step-by-step calculus, algebraic steps, or Bellman / HJB equations in proofs.
- Asserting dimensional homogeneity across equations (e.g. Watts vs. Joules) and additive terms.
- Validating matrix/tensor shapes without concrete numeric substitutions.
- Checking boundary conditions, asymptotic limits ($N \to \infty$, $x \to 0^+$), and Hessian convexity.
- Auditing symbol notation consistency and overloading across manuscript sections.

---

## Native MCP Tools

Invoke the native SciFi MCP tools directly:

### 1. `scifi_verify_derivative`
Check whether a claimed derivative $f'_{\text{claimed}}$ equals $\frac{d}{dx}f(x)$.

```json
{
  "expr": "\\frac{1}{2} x^2 + \\sin(x)",
  "var": "x",
  "claimed": "x + \\cos(x)"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `expr` | string | Yes | Function $f(x)$ in LaTeX or Python math syntax |
| `var` | string | Yes | Differentiation variable (e.g., `"x"`) |
| `claimed` | string | Yes | Claimed analytical derivative in LaTeX or Python math |

### 2. `scifi_verify_derivation_step`
Symbolically verify algebraic derivation equality asserting $LHS == RHS$.

```json
{
  "lhs": "(x + 1)^2 - (x - 1)^2",
  "rhs": "4 * x",
  "assumptions": ["x > 0"]
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `lhs` | string | Yes | Left-hand side mathematical expression |
| `rhs` | string | Yes | Right-hand side mathematical expression |
| `assumptions` | array of strings | No | Optional algebraic assumptions (e.g. `["x > 0", "n >= 1"]`) |

### 3. `scifi_check_units`
Verify physical dimensional homogeneity across equations or additive terms via Pint.

```json
{
  "lhs": "5 * watt * second",
  "rhs": "5 * joule",
  "check_mode": "eq"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `lhs` | string | Yes | Left-hand expression with units, or comma-separated terms if `check_mode="terms"` |
| `rhs` | string | No | Right-hand expression with units (required for `check_mode="eq"`) |
| `check_mode` | string | No | `"eq"` (equality check, default) or `"terms"` (additive compatibility check) |

### 4. `scifi_check_matrix_shapes`
Validate matrix dimensions, vector products, and tensor contractions symbolically.

```json
{
  "operation": "A * B - C",
  "dimensions": {
    "A": ["m", "n"],
    "B": ["n", "k"],
    "C": ["m", "k"]
  }
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `operation` | string | Yes | Matrix algebra expression (e.g., `"A * B - C"`, `"A.T * B"`) |
| `dimensions` | object or string | Yes | Map of matrix names to `[rows, cols]` dimensions (symbolic or integer) |

### 5. `scifi_check_limits`
Evaluate and verify asymptotic and boundary limits $\lim_{var \to point} expr$.

```json
{
  "expr": "\\frac{1}{N}",
  "var": "N",
  "point": "oo",
  "claimed": "0",
  "direction": "+-"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `expr` | string | Yes | Expression in LaTeX or Python math syntax |
| `var` | string | Yes | Limit variable (e.g., `"N"`, `"x"`) |
| `point` | string | Yes | Target point (`"0"`, `"oo"`, `"-oo"`, or numeric constant) |
| `claimed` | string | Yes | Claimed limit value (`"0"`, `"oo"`, `"-oo"`, etc.) |
| `direction` | string | No | Direction: `"+-"` (two-sided, default), `"+"` (right), or `"-"` (left) |

### 6. `scifi_check_convexity`
Verify convexity/concavity via second derivative (Hessian sign analysis).

```json
{
  "expr": "x^2 + 3*x",
  "var": "x",
  "claimed": "convex"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `expr` | string | Yes | Scalar objective function in LaTeX or Python math |
| `var` | string | Yes | Optimization variable (e.g., `"x"`) |
| `claimed` | string | No | Claimed property: `"convex"` (default), `"strictly convex"`, `"concave"`, or `"strictly concave"` |

### 7. `scifi_check_notation`
Audit manuscript LaTeX for mathematical symbol notation consistency and collisions.

```json
{
  "tex_path": "path/to/manuscript.tex",
  "sections": ["Section 3", "Section 4"]
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `tex_path` | string | Yes | File path to `.tex` manuscript or raw LaTeX string |
| `sections` | array of strings | No | Optional section filter |

---

## Status Codes & Interpretation

| Status Code | Meaning | Agent Action |
|---|---|---|
| `VALID` | Mathematical claim verified symbolically | Confirm step to user; safe to incorporate in manuscript. |
| `INVALID_DERIVATION` | Computed derivative does not match claimed | Report `computed_derivative` and `difference`. Do not assert incorrect gradient in text. |
| `INVALID_STEP` | LHS does not equal RHS | Report simplified difference to user; highlight required algebraic assumption if missing. |
| `DIMENSION_MISMATCH` | Incompatible physical units | Report dimensionality mismatch between LHS and RHS or additive terms. |
| `SHAPE_ERROR` | Inner matrix dimensions do not align | Surface incompatible product and suggest transposed or corrected shapes. |
| `INVALID_LIMIT` | Computed limit differs from claimed | Surface `computed_limit` and divergence or singularity note. |
| `INVALID_CONVEXITY_CLAIM` | Function does not satisfy claimed convexity | Report computed second derivative / Hessian sign behavior. |
| `NOTATION_INCONSISTENCY` | Same symbol overloaded or formatted inconsistently | Provide list of conflicting symbols with section locations. |
| `ERROR` | Parsing or symbolic evaluation failure | Inspect LaTeX syntax error or unsupported function; prompt user for clarification. |
