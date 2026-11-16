---
name: gauss
description: Numerical sanity, curve verification, and statistical audit engine. Validates that theoretical closed-form expressions match simulation curves, audits statistical significance (N >= 30, 95% confidence intervals), and catches boundary and monotonicity violations.
---

# Gauss: Numerical Sanity, Curve Verification & Statistical Auditing

The `gauss` skill validates empirical results, ensures numerical fidelity, and audits statistical rigor in scientific manuscripts. It provides native MCP tools to verify that closed-form theoretical expressions match simulation curves and that statistical sampling obeys confidence intervals and the Central Limit Theorem ($N \ge 30$).

## When to Use
- Validating whether theoretical closed-form bounds match numerical simulations in the Evaluation section.
- Auditing sample size, error bars, standard errors, and confidence intervals for statistical rigor.
- Checking boundary conditions ($0 \le P \le 1$, positive delay) and monotonicity consistency between theory and empirical traces.
- Catching unhedged claims where empirical data diverges from theoretical closed forms.

---

## Native MCP Tools

Invoke the native SciFi MCP tools directly:

### 1. `scifi_verify_curve`
Verify that theoretical closed-form LaTeX formulas align with empirical simulation curves from CSV/JSON or numeric arrays.

```json
{
  "formula_latex": "\\frac{1}{1 + x^2}",
  "var_name": "x",
  "sim_data_path": "results/sim_trace.csv",
  "x_col": "snr",
  "y_col": "ber",
  "rtol": 0.05,
  "atol": 0.01
}
```

Or pass sample values directly:
```json
{
  "formula_latex": "2 * x + 1",
  "var_name": "x",
  "x_vals": [0.0, 1.0, 2.0, 3.0],
  "y_vals": [1.02, 3.01, 4.98, 7.02],
  "rtol": 0.02
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `formula_latex` | string | Yes | Theoretical mathematical equation in LaTeX (e.g., `"\\frac{1}{1 + x^2}"`) |
| `var_name` | string | Yes | Independent variable symbol (e.g., `"x"`) |
| `sim_data_path` | string | No | Path to CSV or JSON simulation trace file |
| `x_vals` | array of floats | No | Explicit independent variable sample values |
| `y_vals` | array of floats | No | Explicit empirical simulation values |
| `x_col` | string | No | Column name for $x$ in CSV/JSON data (default: `"x"`) |
| `y_col` | string | No | Column name for $y$ in CSV/JSON data (default: `"y"`) |
| `rtol` | float | No | Relative tolerance threshold (default: `0.01` = 1%) |
| `atol` | float | No | Absolute tolerance threshold (default: `0.001`) |

### 2. `scifi_audit_statistics`
Audit empirical simulation data: compute mean, standard error, confidence intervals, and check Central Limit Theorem sample size ($N \ge 30$).

```json
{
  "samples": [12.1, 12.4, 12.2, 12.9, 12.5, 12.3, 12.7, 12.8],
  "confidence": 0.95
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `samples` | array of floats | Yes | List of numerical observations or experiment run samples |
| `confidence` | float | No | Confidence level (default: `0.95` for 95% CI) |

---

## Status Codes & Interpretation

### Curve Verification
| Status Code | Meaning | Agent Action |
|---|---|---|
| `VALID` | Closed-form theory matches simulation within tolerance | Confirm alignment; theoretical derivation explains empirical results. |
| `CURVE_MISMATCH` | Simulation deviates from theoretical curve | Surface `worst_point` and `max_relative_error`. Ask whether hardware overhead, channel noise, or unmodelled dynamics explain the divergence. |
| `ERROR` | Data file not found or formula parse failure | Check column names and formula syntax; prompt user. |

### Statistical Auditing
| Condition | Meaning | Agent Action |
|---|---|---|
| `is_statistically_sound: true` | $N \ge 30$, satisfying Central Limit Theorem | Safe to report mean, margin of error, and confidence interval in paper. |
| `is_statistically_sound: false` | $N < 30$ ($N$ too small for CLT assumption) | Warn user about `clt_warning`. Recommend increasing sample size to at least 30 runs, or explicitly note Student's $t$ caveat. |

---

## Analytical Bounds vs. Empirical Regression Fits

When comparing numerical trade-off or scaling curves (e.g., $y = a + b x^{-\alpha}$ convergence, error, or energy–latency trade-off plots) against theoretical bounds:
- **Never conflate an empirical fit with analytical bound verification:** If the derived theoretical bound constant $B$ differs by orders of magnitude from an empirically fitted regression coefficient $b$, or if the asymptotic baseline $a$ is not established by an independent exact solver, ground-truth oracle, or certified lower bound, do **not** label the fitted curve as quantitative verification of the theorem bound.
- **Required Framing:** Either derive a tighter valid analytical constant and independently certify the reference baseline, or explicitly separate the theorem's worst-case upper/lower bound from the empirical trend—presenting the plot as *empirical scaling consistency with the predicted functional rate* rather than quantitative proof of the theorem's constants.
