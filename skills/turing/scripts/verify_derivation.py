#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "sympy",
#     "antlr4-python3-runtime==4.11.0",
# ]
# ///
import argparse
import json
import sys
import sympy as sp
from sympy.parsing.latex import parse_latex

def verify_derivative(f_latex: str, var_str: str, claimed_latex: str) -> dict:
    try:
        # Parse LaTeX into SymPy expressions
        var = sp.Symbol(var_str)
        f = parse_latex(f_latex)
        claimed = parse_latex(claimed_latex)

        # Compute exact symbolic derivative
        computed = sp.diff(f, var)

        # Check equivalence: computed - claimed == 0
        diff = sp.simplify(computed - claimed)
        is_correct = (diff == 0)

        result = {
            "status": "VALID" if is_correct else "INVALID_DERIVATION",
            "is_correct": is_correct,
            "variable": var_str,
            "original_expression": sp.latex(f),
            "claimed_derivative": sp.latex(claimed),
            "computed_derivative": sp.latex(computed),
        }

        if not is_correct:
            result["discrepancy"] = sp.latex(diff)

        return result

    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
            "hint": "Ensure LaTeX expressions are valid standard math syntax without custom macros."
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Turing: Symbolic derivative & derivation verifier")
    parser.add_argument("--expr", required=True, help="Original function f in LaTeX")
    parser.add_argument("--var", required=True, help="Differentiation variable (e.g., x, t)")
    parser.add_argument("--claimed", required=True, help="Claimed derivative in LaTeX")

    args = parser.parse_args()
    res = verify_derivative(args.expr, args.var, args.claimed)
    print(json.dumps(res, indent=2))
