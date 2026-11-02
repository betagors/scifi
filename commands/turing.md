---
description: Verify LaTeX mathematical derivations, symbolic calculus, units, and notation
argument-hint: "[--expr <latex> --claimed <latex> | --file <paper.tex>]"
---

Audit mathematical proofs and derivations using the `turing` skill and native `scifi_*` MCP tools:

- **Derivatives (`scifi_verify_derivative`)**: Check that symbolic $\frac{d}{dx} f(x)$ matches claimed results using SymPy.
- **Dimensional Units (`scifi_check_units`)**: Validate physical units and dimension consistency via Pint (`eq` or `terms` mode).
- **Matrix Dimensions (`scifi_check_matrix_shapes`)**: Validate symbolic tensor and matrix products.
- **Asymptotic Limits (`scifi_check_limits`)**: Check boundary and asymptotic behavior (e.g. $N \to \infty$).
- **Convexity (`scifi_check_convexity`)**: Calculate symbolic Hessian and test positive definiteness via Sylvester's criterion.
- **Curve Verification (`scifi_verify_curve`)**: Evaluate closed forms and compare against simulation data.
- **Notation Consistency (`scifi_check_notation`)**: Scan LaTeX files for conflicting notation variants ($P$, $p(t)$, $\mathbf{P}$).

Target/Arguments: $ARGUMENTS
