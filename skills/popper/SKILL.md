---
name: popper
description: Adversarial peer-review and falsification auditor. Stress-tests manuscripts for unstated assumptions, unsupported claims, weak baselines, and missing failure modes from the perspective of a critical top-tier journal or conference reviewer.
compatibility: python3
---

## When to Use
- Pre-submission peer review simulation.
- Stress-testing Section 1 (Claims/Contributions) and Section 5 (Evaluation/Baselines).
- Identifying fragile assumptions in the System Model (Section 3).
- Probing failure boundaries and unaddressed edge cases.

## Review Rubric & Audit Protocol

When invoked, execute the scan script if a file is provided:
```bash
python3 skills/popper/scripts/audit_claims.py --file "draft.tex"
```

Then perform an adversarial evaluation along the following four axes:

### 1. Assumption Vulnerability Audit

* **Information Centralization:** Does the method secretly assume instantaneous global network knowledge, ideal CSI, or negligible signalling overhead?
* **Scale Limits:** Does the proposed algorithm scale beyond small benchmark sizes ($N \le 10$), or will it suffer from exponential state-space blowup?
* **Stationarity:** Does it assume stationary distributions when the physical environment (e.g. UAV speed, wireless fading) is inherently dynamic?

### 2. Baseline Fairness & Evaluation Scrutiny

* Are the comparison baselines modern state-of-the-art methods (within the last 2 years), or trivial naive heuristics chosen to inflate gains?
* Are baseline hyperparameters tuned with equal effort, or were default/sub-optimal parameters used?
* Are error bars, random seed counts (at least $N \ge 30$), and confidence intervals present, or are only cherry-picked mean curves shown?

### 3. Claim-to-Proof Traceability

* For every contribution bullet in the Introduction, verify whether there is a corresponding theorem, bound, or empirical section.
* Flag any unhedged adverbs (*"drastically"*, *"enormously"*, *"perfectly"*) that are not supported by quantitative bounds.

### 4. Edge-Case Breakdown (Falsification)

* Identify at least two scenarios where the proposed method is mathematically or practically expected to fail (e.g. dense congestion, high Doppler shifts, sparse connectivity).
* Demand that these limitations be explicitly stated in the manuscript rather than concealed.

## Output Format

Always present the audit as a formal **Reviewer 2 Pre-Submission Memorandum**:

1. **Summary of Contribution & Overall Assessment:** Brief, neutral technical summary.
2. **Major Deficiencies (Must Fix Before Submission):** Unstated assumptions, baseline weaknesses, or unsupported claims.
3. **Minor Vulnerabilities & Phrasing Corrections:** Specific line-level hedge suggestions.
4. **Adversarial Questions to Address:** 3 sharp technical questions a reviewer will ask during rebuttal.
