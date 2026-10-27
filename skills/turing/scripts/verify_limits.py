#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "sympy",
#     "antlr4-python3-runtime==4.11.0",
# ]
# ///
"""
Turing – Boundary & Asymptotic Behaviour (Limits) Verifier.

Checks whether a claimed limit value or convergence assertion is correct.

Usage
-----
# Claim: lim_{N -> oo} 1/N = 0
python verify_limits.py --expr "\\frac{1}{N}" --var "N" --point oo --claimed "0"

# One-sided limit from the right
python verify_limits.py --expr "\\frac{1}{x}" --var "x" --point "0" --dir "+" --claimed "oo"

Supported --point values: a number, "oo" (∞), "-oo" (-∞).
Supported --dir values: "+" (from right), "-" (from left), "" or omit (two-sided, default).
"""
import argparse
import json
import sympy as sp
from sympy.parsing.latex import parse_latex

_SPECIAL = {"oo": sp.oo, "-oo": -sp.oo, "0": sp.Integer(0)}

def _parse_point(tok: str):
    return _SPECIAL.get(tok, parse_latex(tok))

def verify_limit(expr_latex: str, var_str: str, point_str: str,
                 claimed_latex: str, direction: str) -> dict:
    try:
        var = sp.Symbol(var_str)
        expr = parse_latex(expr_latex)
        claimed = _parse_point(claimed_latex) if claimed_latex in _SPECIAL else parse_latex(claimed_latex)
        point = _parse_point(point_str)
        dir_arg = direction if direction in ("+", "-") else "+-"

        computed = sp.limit(expr, var, point, dir_arg)
        diff = sp.simplify(computed - claimed)
        is_correct = (diff == 0)

        result = {
            "status": "VALID" if is_correct else "INVALID_LIMIT",
            "is_correct": is_correct,
            "variable": var_str,
            "point": point_str,
            "direction": direction or "two-sided",
            "expression": sp.latex(expr),
            "claimed_limit": sp.latex(claimed),
            "computed_limit": sp.latex(computed),
        }
        if not is_correct:
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
            "hint": "Use standard LaTeX. For infinity use 'oo' or '-oo' as --point.",
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Turing: Boundary & asymptotic behaviour verifier"
    )
    parser.add_argument("--expr",    required=True, help="Expression f in LaTeX")
    parser.add_argument("--var",     required=True, help="Limit variable (e.g. N, x, t)")
    parser.add_argument("--point",   required=True, help="Limit point (e.g. 0, oo, -oo, or LaTeX)")
    parser.add_argument("--claimed", required=True, help="Claimed limit value in LaTeX or 'oo'/'-oo'")
    parser.add_argument("--dir",     default="",
                        help="Direction: '+' (from right), '-' (from left), '' for two-sided (default)")
    args = parser.parse_args()
    res = verify_limit(args.expr, args.var, args.point, args.claimed, args.dir)
    print(json.dumps(res, indent=2))
