#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "numpy",
#     "scipy",
#     "sympy",
#     "antlr4-python3-runtime==4.11.0",
# ]
# ///
import argparse
import json
import sys
from pathlib import Path
import numpy as np
import sympy as sp
from sympy.parsing.latex import parse_latex


def verify_curve(
    formula_latex: str,
    var_name: str,
    sim_data_path: str,
    x_col: str = "x",
    y_col: str = "y",
    rtol: float = 1e-2,
    atol: float = 1e-3,
) -> dict:
    try:
        # Load empirical simulation data
        data_file = Path(sim_data_path)
        if not data_file.exists():
            return {"status": "ERROR", "message": f"Simulation file not found: {sim_data_path}"}

        if data_file.suffix.lower() == ".csv":
            import csv

            x_vals, y_sim = [], []
            with open(data_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    x_vals.append(float(row[x_col]))
                    y_sim.append(float(row[y_col]))
            x_arr = np.array(x_vals, dtype=np.float64)
            y_arr = np.array(y_sim, dtype=np.float64)
        elif data_file.suffix.lower() == ".json":
            with open(data_file, "r", encoding="utf-8") as f:
                raw_json = json.load(f)
            x_arr = np.array(raw_json[x_col], dtype=np.float64)
            y_arr = np.array(raw_json[y_col], dtype=np.float64)
        else:
            return {"status": "ERROR", "message": "Unsupported file format. Provide CSV or JSON."}

        # Parse formula and compile to fast numerical function
        var = sp.Symbol(var_name)
        expr = parse_latex(formula_latex)
        f_num = sp.lambdify(var, expr, modules=["numpy", "scipy"])

        # Compute theoretical points
        y_theo = f_num(x_arr)

        # Check alignment within tolerances
        discrepancy = np.abs(y_theo - y_arr)
        max_abs_err = float(np.max(discrepancy))
        mean_abs_err = float(np.mean(discrepancy))
        is_matched = bool(np.allclose(y_theo, y_arr, rtol=rtol, atol=atol))

        # Check monotonicity agreement
        theo_diff = np.diff(y_theo)
        sim_diff = np.diff(y_arr)
        monotonic_match = bool(np.all((theo_diff * sim_diff) >= 0))

        worst_idx = int(np.argmax(discrepancy))

        return {
            "status": "VALID_MATCH" if is_matched else "CURVE_MISMATCH",
            "is_matched": is_matched,
            "max_absolute_error": max_abs_err,
            "mean_absolute_error": mean_abs_err,
            "monotonicity_consistent": monotonic_match,
            "sample_points_checked": len(x_arr),
            "worst_point": None
            if is_matched
            else {
                "x": float(x_arr[worst_idx]),
                "theoretical_y": float(y_theo[worst_idx]),
                "simulated_y": float(y_arr[worst_idx]),
            },
        }

    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify analytical curve against simulation results")
    parser.add_argument("--formula", required=True, help="Theoretical formula in LaTeX")
    parser.add_argument("--var", default="x", help="Independent variable symbol")
    parser.add_argument("--data", required=True, help="Path to simulation CSV or JSON")
    parser.add_argument("--xcol", default="x", help="Independent variable column name")
    parser.add_argument("--ycol", default="y", help="Dependent variable column name")
    parser.add_argument("--rtol", type=float, default=0.05, help="Relative tolerance (default 5%%)")
    parser.add_argument("--atol", type=float, default=0.01, help="Absolute tolerance")

    args = parser.parse_args()
    res = verify_curve(args.formula, args.var, args.data, args.xcol, args.ycol, args.rtol, args.atol)
    print(json.dumps(res, indent=2))
