---
name: gauss
description: Numerical sanity, curve verification, and statistical audit engine. Validates that theoretical closed-form expressions match simulation curves, audits statistical significance (N >= 30, 95% confidence intervals), and catches boundary and monotonicity violations.
compatibility: python3, numpy, scipy, sympy
---

## When to Use
- Verifying whether theoretical closed-form bounds match numerical simulations in Section 5 / Evaluation.
- Auditing error bars and confidence intervals for statistical validity.
- Checking that numerical outputs obey physical boundaries ($0 \le P \le 1$, positive delay, monotonic curves).

## Instructions

### 1. Verify a theoretical curve against simulation data

```bash
python3 skills/gauss/scripts/verify_curve_match.py \
    --formula "\\frac{1}{1 + x^2}" \
    --var "x" \
    --data "results/sim_trace.csv" \
    --xcol "snr" \
    --ycol "ber" \
    --rtol 0.05
```

**Arguments:**

| Flag | Default | Description |
|------|---------|-------------|
| `--formula` | *(required)* | Theoretical expression in LaTeX |
| `--var` | `x` | Independent variable symbol |
| `--data` | *(required)* | Path to simulation CSV or JSON file |
| `--xcol` | `x` | Column name for independent variable |
| `--ycol` | `y` | Column name for dependent variable |
| `--rtol` | `0.05` | Relative tolerance (5 %) |
| `--atol` | `0.01` | Absolute tolerance |

**JSON output fields:**

| Field | Meaning |
|-------|---------|
| `status` | `VALID_MATCH` or `CURVE_MISMATCH` or `ERROR` |
| `is_matched` | Boolean pass/fail via `np.allclose` |
| `max_absolute_error` | Largest point-wise deviation |
| `mean_absolute_error` | Average point-wise deviation |
| `monotonicity_consistent` | Whether trend direction agrees everywhere |
| `worst_point` | `{x, theoretical_y, simulated_y}` at the worst deviation (only on mismatch) |

**Interpreting the output:**
- **`VALID_MATCH`** — The closed form accurately explains the empirical simulation.
- **`CURVE_MISMATCH`** — Surface the `worst_point` and maximum discrepancy to the user. Ask whether unmodelled hardware overhead, channel noise, or implementation artifacts account for the gap.

---

### 2. Audit statistical confidence intervals

```bash
python3 skills/gauss/scripts/audit_statistics.py \
    --samples 12.1 12.4 12.2 12.9 \
    --conf 0.95
```

**Arguments:**

| Flag | Default | Description |
|------|---------|-------------|
| `--samples` | *(required)* | Space-separated list of numeric sample values |
| `--conf` | `0.95` | Confidence level (e.g. `0.95` for 95 %) |

**JSON output fields:**

| Field | Meaning |
|-------|---------|
| `status` | `VALID` or `ERROR` |
| `sample_size` | $N$ |
| `is_statistically_sound` | `true` if $N \ge 30$ (CLT threshold) |
| `mean` | Sample mean |
| `standard_error` | Standard error of the mean |
| `95%_confidence_interval` | `[lower, upper]` bounds |
| `margin_of_error` | Half-width of the CI |
| `warning` | Non-null string if $N < 30$ |

---

### 3. Boundary & monotonicity invariants
The curve matcher automatically checks monotonicity agreement between theory and simulation. For domain-specific bounds (e.g., $P \in [0, 1]$), inspect `theoretical_y` and `simulated_y` at `worst_point` and flag any out-of-range values manually or in a custom wrapper script.

---

## Data File Formats

**CSV** (column headers required):
```csv
snr,ber
0,0.500
5,0.312
10,0.119
```

**JSON** (parallel arrays):
```json
{ "snr": [0, 5, 10], "ber": [0.500, 0.312, 0.119] }
```
