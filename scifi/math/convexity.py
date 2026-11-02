"""
Positive definiteness, Hessian analysis, and convexity verification engine (scifi.math.convexity).
"""

from __future__ import annotations

from typing import Any
import sympy as sp
from sympy.parsing.latex import parse_latex


def _parse_latex_or_expr(text: str) -> sp.Expr:
    """Parse LaTeX scalar function, falling back to sympify."""
    s = text.strip()
    if "**" in s:
        return sp.sympify(s)
    try:
        return parse_latex(s)
    except Exception:
        return sp.sympify(s)


def _sylvester_criterion(H: sp.Matrix) -> bool:
    """Return True iff all leading principal minors are strictly positive (PD)."""
    n = H.shape[0]
    for k in range(1, n + 1):
        minor = H[:k, :k].det()
        simplified = sp.simplify(minor)
        if simplified == sp.Integer(0):
            return False
        if simplified.is_positive is True:
            continue
        if sp.ask(sp.Q.positive(simplified)) is True:
            continue
        return False
    return True


def check_convexity(
    expr: str,
    var: str,
    claimed: str = "convex",
) -> dict[str, Any]:
    """
    Compute symbolic Hessian of scalar function expr w.r.t var and test definiteness.

    Args:
        expr: Scalar function in LaTeX or symbolic math syntax.
        var: Comma-separated variable names (e.g., 'x' or 'x, y').
        claimed: Claimed property: 'strictly_convex', 'convex', 'strictly_concave', 'concave', or 'indefinite'.
    """
    try:
        variables = [sp.Symbol(v.strip()) for v in var.split(",") if v.strip()]
        if not variables:
            return {
                "status": "ERROR",
                "error_message": "No differentiation variables provided.",
            }

        f = _parse_latex_or_expr(expr)

        # Construct Hessian matrix
        H_entries = [
            [sp.diff(f, vi, vj) for vj in variables]
            for vi in variables
        ]
        H = sp.Matrix(H_entries)
        H_simplified = sp.simplify(H)

        eigenvals = H.eigenvals()
        eigenval_list = [sp.latex(ev) for ev in eigenvals.keys()]

        claimed_norm = claimed.strip().lower().replace(" ", "_").replace("-", "_")

        is_pd = _sylvester_criterion(H_simplified)
        is_psd = is_pd or all(
            sp.ask(sp.Q.nonnegative(sp.simplify(ev))) is True or sp.simplify(ev).is_nonnegative is True
            for ev in eigenvals.keys()
        )

        neg_H = -H_simplified
        is_nd = _sylvester_criterion(neg_H)
        is_nsd = is_nd or all(
            sp.ask(sp.Q.nonnegative(sp.simplify(-ev))) is True or sp.simplify(-ev).is_nonnegative is True
            for ev in eigenvals.keys()
        )

        if is_pd:
            actual = "strictly_convex"
        elif is_nd:
            actual = "strictly_concave"
        elif is_psd and not is_nsd:
            actual = "convex"
        elif is_nsd and not is_psd:
            actual = "concave"
        elif is_psd and is_nsd:
            actual = "concave" if "concave" in claimed_norm else "convex"
        else:
            actual = "indefinite"

        if claimed_norm == "convex":
            is_correct = is_psd
        elif claimed_norm == "concave":
            is_correct = is_nsd
        elif claimed_norm == "strictly_convex":
            is_correct = is_pd
        elif claimed_norm == "strictly_concave":
            is_correct = is_nd
        elif claimed_norm == "indefinite":
            is_correct = (not is_psd and not is_nsd)
        else:
            is_correct = (actual == claimed_norm)

        result: dict[str, Any] = {
            "status": "VALID" if is_correct else "INVALID_CONVEXITY_CLAIM",
            "is_correct": is_correct,
            "expression": sp.latex(f),
            "variables": var,
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
            "hint": "Ensure expr is valid LaTeX math and variables are comma-separated names.",
        }
