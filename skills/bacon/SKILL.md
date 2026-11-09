---
name: bacon
description: Conference reproducibility and open-science checklist auditor. Audits submissions for random seeds, trial error bars, compute infrastructure disclosures, hyperparameter search tables, and double-blind repository anonymization.
---

# Bacon: Conference Reproducibility & Open-Science Sentinel

The `bacon` skill audits manuscripts against formal conference reproducibility checklists (NeurIPS Reproducibility Checklist, ICML, ICLR, and IEEE Open Science mandates) to catch missing random seeds, unreported compute budgets, and unblinded code repositories before desk triage.

## When to Use
- Pre-submission reproducibility gate check.
- Verifying whether empirical evaluations report seeds, variance, and confidence intervals.
- Checking that compute resources (GPU model, total training hours) are properly declared.
- Verifying code repository anonymization under double-blind review.

---

## Native MCP Tool

Invoke the native SciFi MCP tool directly:

### `scifi_audit_reproducibility`
Audit manuscript against conference reproducibility checklists.

```json
{
  "tex_path": "path/to/main.tex",
  "venue": "neurips",
  "double_blind": true
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `tex_path` | string | Yes | Path to LaTeX root file (`main.tex`, `paper.tex`) |
| `venue` | string | No | Target venue checklist (default: "neurips", "icml", "ieee") |
| `double_blind` | boolean | No | Whether double-blind anonymization is enforced (default: false) |

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
