---
description: Verify LaTeX mathematical derivations, symbolic calculus, units, and notation
argument-hint: "[--expr <latex> --claimed <latex> | --file <paper.tex>]"
---

Audit mathematical proofs and derivations using the `turing` skill and verification scripts:

- **Derivatives (`verify_derivation.py`)**: Check that symbolic $\frac{d}{dx} f(x)$ matches claimed results using SymPy.
- **Dimensional Units (`verify_units.py`)**: Validate physical units and dimension consistency via Pint.
- **Matrix Dimensions (`verify_matrix_shapes.py`)**: Validate symbolic tensor and matrix products.
- **Asymptotic Limits (`verify_limits.py`)**: Check boundary and asymptotic behavior (e.g. $N \to \infty$).
- **Convexity (`verify_convexity.py`)**: Calculate symbolic Hessian and test positive definiteness via Sylvester's criterion.
- **Numerical Sanity (`verify_numerical.py`)**: Lambdify closed forms and compare against simulation data.
- **Notation Consistency (`verify_notation.py`)**: Scan LaTeX files for conflicting notation variants ($P$, $p(t)$, $\mathbf{P}$).

Target/Arguments: $ARGUMENTS
