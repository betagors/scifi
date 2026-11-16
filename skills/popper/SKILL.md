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

## Forensic Investigation Workflow (Before Writing the Memorandum)

Follow this 5-step cross-artifact audit trajectory before writing findings:
1. **Full-Document + Appendix Inspection:** Read the main manuscript alongside all appendices so buried assumption caveats, boundary/weight constraints, or derived constants cannot hide discrepancies in main-body claims.
2. **Proof-from-Implementation Separation (Code Audit):** Whenever simulation, experimental, or solver code exists in the workspace, inspect the actual implementation to verify whether the executed pipeline matches the theorem hypotheses (e.g., approximate/heuristic algorithm vs. idealized oracle; executed numerical solver vs. stated problem formulation; true end-to-end bottleneck complexity).
3. **Visual PDF & Plot-Legend Cross-Check:** Use `scifi_render_pdf` / `da-vinci` previews to inspect rendered figure pages and compare fitted curve formulas printed inside plot legends/captions against analytical constants reported in theorems, tables, and appendices.
4. **Live Literature & Citation Source Check:** Use `hypatia` / `alex` / web search to inspect closest same-year SOTA combinations of the manuscript's techniques and verify referenced source pages.
5. **Fatal vs. Fixable Triage:** Separate **substantive rejection risks** (certification gaps, bound-to-plot contradictions, unestablished guarantee-level novelty) from **fixable framing/prose issues**, and order recommendations so theoretical/experimental repairs precede prose or figure polish.

---

## Review Rubric & Audit Protocol

After running `scifi_audit_claims`, evaluate the manuscript across the four adversarial axes:

### 1. Assumption Vulnerability Audit
- **Theory-to-Method Certification Gap:** Flag theorems that rely on idealized assumptions (e.g., an exact/$\delta$-approximate subproblem oracle, convexity, i.i.d. sampling, or exact projection) while claiming to certify an implementation that executes a learned heuristic, greedy step, or non-convex approximation without proving the composite pipeline inherits that bound. Require explicitly separating conditional theoretical guarantees from empirical performance.
- **Strawman Critique of Classical Theory:** Flag claims that foundational theory "breaks down" or forms a "paradox" via an overly strict mischaracterization of its assumptions (e.g., confusing expectation-level conditions with deterministic worst-case ones); require framing refinements on their exact mathematical or empirical merit.
- **Information Centralization:** Does the method secretly assume instantaneous global network knowledge, ideal channel state information (CSI), or negligible signalling delay?
- **Scale Limits:** Does the algorithm scale beyond small benchmark instances ($N \le 10$), or will it suffer from exponential combinatorial blowup?
- **Stationarity:** Does it assume stationary distributions when the underlying physical or data-generating environment is dynamic?

### 2. Baseline Fairness & Evaluation Scrutiny
- **Citation Recency & Backbone Justification:** Are comparison baselines modern state-of-the-art methods (within the last 2 years), or weak/naive heuristics chosen to artificially inflate gains? When an ablation suite isolates modular components, verify that recent SOTA formulations (last 1–2 years) are cited alongside foundational papers in both the baseline descriptions and evaluation tables, and that the shared backbone or experimental protocol is explicitly justified.
- **Multi-Dimension Scalability & Ground-Truth Reference:** Require scaling experiments across all primary problem dimensions (e.g., sample size, dimensionality, node/agent count), not merely sweeping one secondary parameter at fixed scale; verify whether an exact solver or ground-truth reference is included on tractable small instances.
- **Experimental Variance Separation:** Require explicitly separating distinct sources of experimental variance (e.g., training/initialization seeds vs. evaluation rollouts/splits, or biological vs. technical replicates), alongside objective definitions, stopping criteria, and baseline tuning effort.
- **Cross-Paper vs. Controlled Benchmark Integrity:** Flag any literature comparison table that compares raw environment-dependent metrics (e.g., wall-clock runtime in `ms`/`s`, throughput) copied from disparate papers with different hardware, datasets, or software stacks. Require replacing raw timings with **Solver Paradigm / Asymptotic Complexity** or an explicit disparate-setup footnote, reserving raw runtime comparisons strictly for controlled same-environment, same-seed evaluation tables.
- **Degenerate / Invariant Table Columns:** Flag any evaluation table column whose values are identical across all method rows (e.g., due to a fixed constraint, dataset split, or deterministic preprocessing). Reviewers often mistake identical columns for copy-paste errors or wasted space; require replacing the column with a discriminative downstream metric (reporting the invariant in the table caption) or attaching a column-header footnote explaining why it is invariant by construction.
- **Tuning & Statistical Rigor:** Were baseline hyperparameters tuned with equal effort, or were default/sub-optimal configurations used? Are error bars, random seed counts (at least $N \ge 30$), and 95% confidence intervals present, or are only cherry-picked mean curves shown? (Verify with `gauss`.)

### 3. Claim-to-Proof Traceability
- **Analytical Constant vs. Empirical Curve-Fit Discrepancy:** Flag when an empirical regression fit (e.g., $a + b N^{-\alpha}$) is claimed to verify an analytical theorem bound whose derived constant $B$ differs by orders of magnitude from $b$, or whose baseline asymptote $a$ lacks an independent optimality calculation, ground truth, or certified bound.
- **End-to-End Bottleneck Complexity vs. Sub-Module Complexity:** Flag when the Abstract or Introduction headlines the asymptotic complexity of a fast sub-routine while a coupled stage in the same pipeline has higher dominant complexity.
- **Formulation Class vs. Executed Solver/Approximator:** Flag conflating the mathematical problem class (e.g., convex/conic program, exact posterior, PDE) with the numerical solver or approximator actually executed in code (e.g., generic SQP/quasi-Newton solver, variational surrogate); require reporting both clearly.
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
