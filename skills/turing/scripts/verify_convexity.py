#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "sympy",
#     "antlr4-python3-runtime==4.11.0",
# ]
# ///
"""
Turing – Positive Definiteness & Convexity Checker.

Computes the symbolic Hessian of f w.r.t. a list of variables and tests:
  - strict convexity  (all leading principal minors > 0,  i.e. PD)
  - convexity         (all eigenvalues >= 0,               i.e. PSD)

Usage
-----
# f = x^2 + y^2 + x*y  is it strictly convex in x, y?
python verify_convexity.py \
    --expr "x^2 + y^2 + x*y" \
    --vars "x,y" \
    --claimed "strictly_convex"

# --claimed can be: strictly_convex | convex | indefinite
# The tool always reports the Hessian and its eigenvalues regardless.
"""
import argparse
import json
import sympy as sp
from sympy.parsing.latex import parse_latex

def _sylvester_criterion(H: sp.Matrix) -> bool:
    """Return True iff all leading principal minors are strictly positive (PD)."""
    n = H.shape[0]
    for k in range(1, n + 1):
        minor = H[:k, :k].det()
        simplified = sp.simplify(minor)
        # We require the minor to be a strictly positive constant or expression
        if simplified == sp.Integer(0):
            return False
        is_pos = sp.ask(sp.Q.positive(simplified))
        if is_pos is not True:
            return False
    return True

def verify_convexity(expr_latex: str, vars_str: str, claimed: str) -> dict:
    try:
        variables = [sp.Symbol(v.strip()) for v in vars_str.split(",")]
        f = parse_latex(expr_latex)

        # Build symbolic Hessian
        n = len(variables)
        H_entries = [
            [sp.diff(f, vi, vj) for vj in variables]
            for vi in variables
        ]
        H = sp.Matrix(H_entries)
        H_simplified = sp.simplify(H)

        eigenvals = H.eigenvals()  # {eigenvalue: multiplicity}
        eigenval_list = [sp.latex(ev) for ev in eigenvals.keys()]

        # Determine actual definiteness
        is_pd  = _sylvester_criterion(H_simplified)
        # PSD: all eigenvalues non-negative (may be symbolic – best-effort)
        is_psd = is_pd or all(
            sp.ask(sp.Q.nonnegative(sp.simplify(ev))) is True
            for ev in eigenvals.keys()
        )

        if is_pd:
            actual = "strictly_convex"
        elif is_psd:
            actual = "convex"
        else:
            actual = "indefinite"

        is_correct = (actual == claimed)

        result = {
            "status": "VALID" if is_correct else "INVALID_CONVEXITY_CLAIM",
            "is_correct": is_correct,
            "expression": sp.latex(f),
            "variables": vars_str,
            "hessian": sp.latex(H_simplified),
            "eigenvalues": eigenval_list,
            "actual_property": actual,
            "claimed_property": claimed,
        }
        if not is_correct:
            result["hint"] = (
                f"The Hessian is {actual}, not {claimed}. "
                "Check the sign of the leading principal minors or eigenvalues."
            )
        return result
    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
            "hint": (
                "Ensure --expr is valid LaTeX and --vars is a comma-separated list of variable names. "
                "--claimed must be one of: strictly_convex, convex, indefinite."
            ),
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Turing: Positive definiteness & convexity checker"
    )
    parser.add_argument("--expr",    required=True, help="Scalar function f in LaTeX")
    parser.add_argument("--vars",    required=True, help="Comma-separated differentiation variables (e.g. x,y)")
    parser.add_argument("--claimed", required=True,
                        choices=["strictly_convex", "convex", "indefinite"],
                        help="Author's claim about the function")
    args = parser.parse_args()
    res = verify_convexity(args.expr, args.vars, args.claimed)
    print(json.dumps(res, indent=2))
