#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "sympy",
#     "numpy",
#     "antlr4-python3-runtime==4.11.0",
# ]
# ///
"""
Turing – Equation-to-Plot Numerical Sanity Checker.

Converts a symbolic closed-form expression to a numerical function via
sympy.lambdify, evaluates it over a parameter sweep, and compares against
a JSON array of simulation values.

Usage
-----
python verify_numerical.py \
    --expr "\\frac{1}{1 + x^2}" \
    --var "x" \
    --sweep "0,1,2,3,4" \
    --simulated "[1.0, 0.5, 0.2, 0.1, 0.058]" \
    --rtol 1e-2

--sweep   : comma-separated x values (must match length of --simulated)
--simulated: JSON array of simulation output values
--rtol    : relative tolerance for np.allclose (default 1e-3)
--atol    : absolute tolerance for np.allclose (default 1e-6)
"""
import argparse
import json
import numpy as np
import sympy as sp
from sympy.parsing.latex import parse_latex

def verify_numerical(expr_latex: str, var_str: str,
                     sweep: list[float], simulated: list[float],
                     rtol: float = 1e-3, atol: float = 1e-6) -> dict:
    try:
        var = sp.Symbol(var_str)
        f_sym = parse_latex(expr_latex)
        f_num = sp.lambdify(var, f_sym, modules="numpy")

        x_arr = np.array(sweep, dtype=float)
        analytical = f_num(x_arr)
        sim_arr    = np.array(simulated, dtype=float)

        close = bool(np.allclose(analytical, sim_arr, rtol=rtol, atol=atol))

        abs_errors = np.abs(analytical - sim_arr).tolist()
        worst_idx  = int(np.argmax(abs_errors))

        result = {
            "status": "VALID" if close else "NUMERICAL_MISMATCH",
            "is_correct": close,
            "expression": sp.latex(f_sym),
            "variable": var_str,
            "rtol": rtol,
            "atol": atol,
            "analytical_values": [float(v) for v in analytical],
            "simulated_values": simulated,
            "max_abs_error": abs_errors[worst_idx],
            "worst_at_x": sweep[worst_idx],
        }
        if not close:
            result["hint"] = (
                f"Largest deviation is {abs_errors[worst_idx]:.4g} at {var_str}={sweep[worst_idx]}. "
                "Check closed-form coefficients or simulation normalisation."
            )
        return result
    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
            "hint": "Ensure --expr is valid LaTeX and --sweep / --simulated have equal length.",
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Turing: Equation-to-plot numerical sanity checker"
    )
    parser.add_argument("--expr",      required=True, help="Closed-form expression in LaTeX")
    parser.add_argument("--var",       required=True, help="Sweep variable name (e.g. x, N)")
    parser.add_argument("--sweep",     required=True, help="Comma-separated x values (e.g. 0,1,2,3)")
    parser.add_argument("--simulated", required=True, help="JSON array of simulation outputs")
    parser.add_argument("--rtol", type=float, default=1e-3, help="Relative tolerance (default 1e-3)")
    parser.add_argument("--atol", type=float, default=1e-6, help="Absolute tolerance (default 1e-6)")
    args = parser.parse_args()

    sweep     = [float(v) for v in args.sweep.split(",")]
    simulated = json.loads(args.simulated)
    res = verify_numerical(args.expr, args.var, sweep, simulated, args.rtol, args.atol)
    print(json.dumps(res, indent=2))
