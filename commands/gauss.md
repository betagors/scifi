---
description: Verify theoretical curves against simulation data and audit statistical confidence
argument-hint: "[--formula <latex> --data <file.csv> | --samples <values...>]"
---

Execute the `gauss` skill on `$ARGUMENTS`. Verify that the specified LaTeX formula matches the simulation dataset within standard tolerances, check confidence interval validity, and report any discrepancies.

**Curve verification** (`verify_curve_match.py`): Lambdify a LaTeX closed-form expression, evaluate it at every simulation point, and compare with `np.allclose`. Report `VALID_MATCH` or `CURVE_MISMATCH` with the worst deviation and its location.

**Statistical audit** (`audit_statistics.py`): Compute mean, standard error, and $t$-distribution confidence interval. Flag $N < 30$ with a reviewer-facing warning.

**Monotonicity check**: Built into curve verification — surfaces when theory and simulation disagree on the sign of the slope between consecutive points.
