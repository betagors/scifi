"""
Calculus verification engine: symbolic derivatives, limits, and derivation steps.
"""

from __future__ import annotations

import re
from typing import Any

import sympy as sp
from sympy.parsing.latex import parse_latex

_SPECIAL_LIMIT_POINTS: dict[str, Any] = {
    "oo": sp.oo,
    "+oo": sp.oo,
    "inf": sp.oo,
    "+inf": sp.oo,
    r"\infty": sp.oo,
    r"+\infty": sp.oo,
    "-oo": -sp.oo,
    "-inf": -sp.oo,
    r"-\infty": -sp.oo,
    "0": sp.Integer(0),
}


def _parse_latex_or_expr(text: str) -> sp.Expr:
    """Parse LaTeX string, falling back to sympify for python-style expressions."""
    s = text.strip()
    if "**" in s:
        return sp.sympify(s)
    try:
        return parse_latex(s)
    except Exception:
        return sp.sympify(s)


def _apply_assumptions(expr: sp.Expr, assumptions: list[str] | None) -> sp.Expr:
    """Substitute symbols in expr with assumption-aware Symbol instances."""
    if not assumptions:
        return expr

    subs_map: dict[sp.Symbol, sp.Symbol] = {}
    for a in assumptions:
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(>|>=|<|<=|!=|==)\s*0\s*$", a)
        if m:
            var, op = m.group(1), m.group(2)
            kwargs: dict[str, bool] = {}
            if op == ">":
                kwargs["positive"] = True
            elif op == ">=":
                kwargs["nonnegative"] = True
            elif op == "<":
                kwargs["negative"] = True
            elif op == "<=":
                kwargs["nonpositive"] = True
            elif op == "!=":
                kwargs["nonzero"] = True
            elif op == "==":
                kwargs["zero"] = True
            subs_map[sp.Symbol(var)] = sp.Symbol(var, **kwargs)

    if subs_map:
        expr = expr.subs(subs_map)
    return expr


def verify_derivative(expr: str, var: str, claimed: str) -> dict[str, Any]:
    """
    Verify whether the claimed derivative d(expr)/d(var) matches the computed derivative.
    """
    try:
        diff_var = sp.Symbol(var.strip())
        f = _parse_latex_or_expr(expr)
        claimed_expr = _parse_latex_or_expr(claimed)

        computed = sp.diff(f, diff_var)
        diff = sp.simplify(computed - claimed_expr)
        is_correct = bool(diff == 0)

        result: dict[str, Any] = {
            "status": "VALID" if is_correct else "INVALID_DERIVATION",
            "is_correct": is_correct,
            "variable": var.strip(),
            "original_expression": sp.latex(f),
            "claimed_derivative": sp.latex(claimed_expr),
            "computed_derivative": sp.latex(computed),
        }
        if not is_correct:
            result["discrepancy"] = sp.latex(diff)

        return result
    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
            "hint": "Ensure LaTeX expressions are valid standard math syntax without custom macros.",
        }


def verify_derivation_step(lhs: str, rhs: str, assumptions: list[str] | None = None) -> dict[str, Any]:
    """
    Verify algebraic or analytical equivalence between lhs and rhs, optionally under assumptions.
    """
    try:
        lhs_expr = _parse_latex_or_expr(lhs)
        rhs_expr = _parse_latex_or_expr(rhs)

        if assumptions:
            lhs_expr = _apply_assumptions(lhs_expr, assumptions)
            rhs_expr = _apply_assumptions(rhs_expr, assumptions)

        diff = sp.simplify(lhs_expr - rhs_expr)
        if diff != 0:
            diff = sp.trigsimp(diff)
        if diff != 0:
            diff = sp.expand(diff)
        if diff != 0:
            diff = sp.simplify(diff)

        is_correct = bool(diff == 0)
        result: dict[str, Any] = {
            "status": "VALID" if is_correct else "INVALID_DERIVATION",
            "is_correct": is_correct,
            "lhs": sp.latex(lhs_expr),
            "rhs": sp.latex(rhs_expr),
        }
        if not is_correct:
            result["discrepancy"] = sp.latex(diff)

        return result
    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
            "hint": "Ensure both LHS and RHS expressions are valid standard math syntax.",
        }


def check_limits(
    expr: str,
    var: str,
    point: str,
    claimed: str,
    direction: str = "+-",
) -> dict[str, Any]:
    """
    Verify whether the limit of expr as var -> point equals claimed.
    direction can be '+' (right), '-' (left), or '+-' (two-sided).
    """
    try:
        var_sym = sp.Symbol(var.strip())
        parsed_expr = _parse_latex_or_expr(expr)

        pt_key = point.strip()
        parsed_point = _SPECIAL_LIMIT_POINTS.get(pt_key)
        if parsed_point is None:
            parsed_point = _parse_latex_or_expr(pt_key)

        claimed_key = claimed.strip()
        parsed_claimed = _SPECIAL_LIMIT_POINTS.get(claimed_key)
        if parsed_claimed is None:
            parsed_claimed = _parse_latex_or_expr(claimed_key)

        dir_arg = direction if direction in ("+", "-") else "+-"
        computed = sp.limit(parsed_expr, var_sym, parsed_point, dir_arg)

        if computed == parsed_claimed:
            is_correct = True
            diff = sp.Integer(0)
        else:
            try:
                diff = sp.simplify(computed - parsed_claimed)
                is_correct = bool(diff == 0)
            except Exception:
                diff = None
                is_correct = False

        result: dict[str, Any] = {
            "status": "VALID" if is_correct else "INVALID_LIMIT",
            "is_correct": is_correct,
            "variable": var.strip(),
            "point": point.strip(),
            "direction": direction if direction in ("+", "-") else "two-sided",
            "expression": sp.latex(parsed_expr),
            "claimed_limit": sp.latex(parsed_claimed)
            if hasattr(parsed_claimed, "_sympy_") or isinstance(parsed_claimed, sp.Basic)
            else str(parsed_claimed),
            "computed_limit": sp.latex(computed)
            if hasattr(computed, "_sympy_") or isinstance(computed, sp.Basic)
            else str(computed),
        }

        if not is_correct:
            if diff is not None:
                result["discrepancy"] = sp.latex(diff)
            if computed in (sp.oo, -sp.oo):
                result["hint"] = "Expression diverges – the claimed convergence is false."
            elif sp.ask(sp.Q.infinite(computed)):
                result["hint"] = "Expression hits a singularity at this point."

        return result
    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
            "hint": "Ensure LaTeX expressions are valid standard math syntax. Use 'oo' for infinity.",
        }
