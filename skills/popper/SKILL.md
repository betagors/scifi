---
name: popper
description: Adversarial peer-review and falsification auditor. Stress-tests manuscripts for unstated assumptions, unsupported claims, weak baselines, and missing failure modes from the perspective of a critical top-tier journal or conference reviewer.
---

# Popper: Adversarial Peer-Review & Falsification Auditor

The `popper` skill acts as an adversarial, hostile reviewer (the archetypal "Reviewer 2") to stress-test academic manuscripts prior to submission. It identifies unstated physical and computational assumptions, unsupported claims, weak baselines, and missing failure modes. It combines the automated `scifi_audit_claims` MCP tool with rigorous falsification heuristics.

## When to Use
- Pre-submission peer-review simulation and hostile stress-testing.
- Auditing Section 1 (Contributions/Claims) and Section 5 (Evaluation/Baselines).
- Identifying fragile or unstated assumptions in the System Model (Section 3).
- Probing failure boundaries, extreme regimes, and unaddressed edge cases.

---

## Native MCP Tools

Invoke the native SciFi MCP tool directly:

### `scifi_audit_claims`
Audit manuscript text or LaTeX files for unstated assumptions, unhedged overclaims, and sweeping statements.

```json
{
  "file_path": "path/to/manuscript.tex"
}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file_path` | string | Yes | Path to LaTeX (`.tex`) file, markdown draft, or raw text manuscript content |

Returns:
```json
{
  "status": "SUCCESS | ERROR",
  "total_flags": 4,
  "flags": [
    {
      "line_number": 48,
      "matched_text": "our algorithm completely eliminates latency",
      "category": "UNHEDGED_CLAIM",
      "critique": "Absolute claim of zero latency lacks proof under real channel conditions.",
      "recommendation": "Hedge with 'significantly reduces latency under condition C'."
    }
  ]
}
```

---

## Review Rubric & Audit Protocol

After running `scifi_audit_claims`, evaluate the manuscript across the four adversarial axes:

### 1. Assumption Vulnerability Audit
- **Information Centralization:** Does the method secretly assume instantaneous global network knowledge, ideal channel state information (CSI), or negligible signalling delay?
- **Scale Limits:** Does the algorithm scale beyond small benchmark instances ($N \le 10$), or will it suffer from exponential combinatorial blowup?
- **Stationarity:** Does it assume stationary distributions when the physical environment (e.g., UAV mobility, wireless fading) is dynamic?

### 2. Baseline Fairness & Evaluation Scrutiny
- Are comparison baselines modern state-of-the-art methods (within the last 2 years), or weak/naive heuristics chosen to artificially inflate gains?
- Were baseline hyperparameters tuned with equal effort, or were default/sub-optimal configurations used?
- Are error bars, random seed counts (at least $N \ge 30$), and 95% confidence intervals present, or are only cherry-picked mean curves shown? (Verify with `gauss`.)

### 3. Claim-to-Proof Traceability
- For every contribution bullet in Section 1, is there a matching theorem, analytical bound, or empirical evaluation in the paper?
- Flag unhedged superlatives (*"drastically"*, *"enormously"*, *"perfectly"*, *"optimal"*) that lack quantitative bounds.

### 4. Edge-Case Breakdown (Falsification)
- Identify at least two operational regimes where the proposed method fails (e.g., extreme congestion, high Doppler spread, sparse connectivity).
- Require these failure regimes and limitations to be explicitly stated in the manuscript.

---

## Output Format: Reviewer 2 Pre-Submission Memorandum

Always format findings as a formal memorandum:

1. **Summary of Contribution & Overall Assessment:** Concise, objective technical summary without praise.
2. **Major Deficiencies (Must Fix Before Submission):** Unstated assumptions, weak baselines, or unproven claims.
3. **Minor Vulnerabilities & Phrasing Corrections:** Specific line-level hedging and phrasing suggestions from `scifi_audit_claims`.
4. **Adversarial Rebuttal Questions:** 3 sharp technical questions a reviewer will ask during peer review.
