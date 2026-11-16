---
name: bacon
description: Conference reproducibility and open-science checklist auditor. Audits submissions for random seeds, trial error bars, compute infrastructure disclosures, hyperparameter search tables, and double-blind repository anonymization.
---

# Bacon: ML & Systems Reproducibility and Statistical-Pitfall Sentinel

The `bacon` skill audits manuscripts against Core ML conference reproducibility checklists (`ml`: NeurIPS, ICML, ICLR, OpenReview) and ML-for-Systems/Control/Optimization checklists (`ml-systems`: IEEE, Elsevier, ACM), and scans for common statistical pitfalls (multiple-testing without correction, train/test data leakage, and nested seed-vs-rollout pseudoreplication).

## When to Use
- Pre-submission reproducibility gate check (`ml`, `ml-systems`).
- Verifying whether empirical evaluations report seeds, variance, and confidence intervals.
- Checking ML-for-systems/control/optimization simulation parameter disclosures and solver/rollout tolerances.
- Catching multiple-testing omissions, data leakage before splitting, or conflating rollout episodes from few training seeds as independent trials.
- Verifying code repository anonymization under double-blind review.

---

## Native MCP Tool

Invoke the native SciFi MCP tool directly:

### `scifi_audit_reproducibility`
Audit manuscript against Core ML or ML-Systems checklists and statistical pitfalls.

```json
{
  "tex_path": "path/to/main.tex",
  "venue": "neurips",
  "standard": "ml",
  "double_blind": true,
  "check_pitfalls": true
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `tex_path` | string | Yes | Path to LaTeX root file (`main.tex`, `paper.tex`) |
| `venue` | string | No | Target venue checklist (default: `"neurips"`, `"icml"`, `"iclr"`, `"ieee"`, `"elsevier"`, `"acm"`) |
| `standard` | string | No | Reproducibility profile: `"ml"` (Core ML) or `"ml-systems"` (IEEE/Elsevier/ACM systems & control; inferred from `venue` if omitted) |
| `double_blind` | boolean | No | Whether double-blind anonymization is enforced (default: `false`) |
| `check_pitfalls` | boolean | No | Scan for multiple-testing, data leakage, and nested seed-vs-rollout pseudoreplication (default: `true`) |

Returns:
```json
{
  "status": "SUCCESS",
  "venue": "neurips",
  "score": 80,
  "checklist_items": {
    "seeds_specified": true,
    "error_bars_specified": true,
    "compute_specified": false,
    "hyperparameters_specified": true,
    "code_link_anonymized": true
  },
  "total_issues": 1,
  "issues": [
    {
      "category": "COMPUTE_RESOURCES",
      "severity": "WARNING",
      "message": "No compute hardware specifications or training hours disclosed.",
      "recommendation": "Add compute infrastructure details and training duration in the Experimental Setup or Appendix."
    }
  ]
}
```

---

## Experimental Variance, Solver Fidelity & Scaling Standards

When auditing computational, machine learning, and quantitative empirical manuscripts:
- **Separating Nested Sources of Variance:** Require explicitly separating distinct variance sources—such as independent model initialization/training seeds ($N_{\mathrm{train}}$) vs. evaluation rollouts or data splits ($N_{\mathrm{eval}}$)—alongside objective definitions, stopping criteria, and baseline hyperparameter tuning effort.
- **Formulation Class vs. Executed Numerical Solver / Approximator:** Distinguish the mathematical problem formulation (e.g., convex/conic program, exact posterior, PDE) from the numerical solver or approximator actually invoked in code (e.g., generic SQP/quasi-Newton optimizer vs. dedicated conic solver; variational surrogate vs. exact MCMC). Require reporting solver convergence residuals or constraint-intervention statistics where applicable.
- **Multi-Dimension Scalability:** Verify that scalability claims vary all primary problem dimensions (e.g., sample size, feature dimensionality, network/agent count), rather than sweeping only a single secondary parameter at fixed problem scale.
