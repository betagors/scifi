---
name: euclid
description: Theorem-proof and appendix completeness sentinel. Audits theoretical manuscripts for orphan theorems, missing proofs, and broken appendix derivation cross-references.
---

# Euclid: Theorem–Proof & Appendix Completeness Sentinel

The `euclid` skill prevents submissions from being penalized by theoretical reviewers for "orphan claims"—theorems, lemmas, or propositions stated without a proof or with vague references to the supplementary material without verifiable cross-reference anchors.

## When to Use
- Pre-submission audit of theoretical and algorithmic sections.
- Auditing papers that defer complex proofs to an appendix.
- Catching broken `\ref{app:...}` pointers before camera-ready or peer-review triage.

---

## Native MCP Tool

Invoke the native SciFi MCP tool directly:

### `scifi_audit_proofs`
Audit manuscript for theorem-to-proof resolution and verify appendix labels.

```json
{
  "tex_path": "path/to/main.tex"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `tex_path` | string | Yes | Path to LaTeX root file (`main.tex`, `paper.tex`) |

Returns:
```json
{
  "status": "SUCCESS",
  "total_theorems": 3,
  "orphan_theorems": 1,
  "theorems": [
    {
      "env_type": "theorem",
      "label": "thm:convergence",
      "has_inline_proof": false,
      "referenced_appendix_label": "app:thm1_proof",
      "appendix_verified": true
    }
  ],
  "issues": [
    {
      "category": "ORPHAN_THEOREM",
      "severity": "CRITICAL",
      "theorem": "lem:unproved_claim",
      "message": "Orphan Lemma 'lem:unproved_claim': Stated without an inline \\begin{proof} or an explicit cross-reference to an appendix proof.",
      "recommendation": "Provide an inline proof or explicitly specify 'The proof is deferred to Appendix~\\ref{...}'."
    }
  ]
}
```

---

## Theorem-to-Algorithm & Assumption Integrity Checklist

Beyond structural proof resolution, audit every theoretical statement against these three universal rigor checks:

1. **Conditional Oracle Guarantee vs. Practical Implementation:** Check whether the theorem assumes an idealized estimator, exact subproblem solver, or $\delta$-optimal oracle while the implemented method couples learned models, greedy steps, or heuristic approximations. Unless the composite pipeline is proven to inherit that bound, explicitly state that the theorem certifies the idealized model/oracle and separate that conditional guarantee from empirical performance.
2. **Hypothesis, Domain & Weight Completeness:** For boundedness, convergence, or weighted-norm theorems, verify that all required regularity, domain, positivity, and parameter-weight restrictions (e.g., $\omega_i > 0$, Lipschitz constants, compactness) are explicitly stated in the theorem hypotheses or derived cleanly.
3. **Avoid Strawman "Paradox" Framing:** Do not frame structural or sample-path refinements as a breakdown or "paradox" of classical theory by overstating what classical theory requires (e.g., confusing expectation-level conditions with deterministic per-sample monotonicity). Present exact discrepancy bounds on their own mathematical merit.
