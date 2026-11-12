"""
Curve fitting and analytical-to-simulation curve verification engine.

Consolidates Gauss curve verification and Turing numerical verification into
a single, unified interface supporting both inline arrays and simulation files.
"""

from __future__ import annotations

import csv
import json
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import sympy as sp
from sympy.parsing.latex import parse_latex


def _parse_formula(formula_str: str, var_name: str | None = None) -> sp.Expr:
    """Parse a formula string into a SymPy expression.

    Supports LaTeX expressions (e.g. r'\\frac{1}{1 + x^2}'), standard Python
    expressions (e.g. '2*x**2 + 1'), and relational equations (e.g. 'y = 2*x + 1').
    """
    s = formula_str.strip()
    var_sym = sp.Symbol(var_name) if var_name else None

    def _extract_side(eq: Any) -> sp.Expr:
        if not isinstance(eq, sp.Equality):
            return eq
        if var_sym is not None:
            if var_sym in eq.rhs.free_symbols and var_sym not in eq.lhs.free_symbols:
                return eq.rhs
            if var_sym in eq.lhs.free_symbols and var_sym not in eq.rhs.free_symbols:
                return eq.lhs
        return eq.rhs

    if "**" in s:
        if "=" in s:
            _, rhs = s.split("=", 1)
            expr = sp.sympify(rhs.strip())
        else:
            expr = sp.sympify(s)
        return _extract_side(expr)

    try:
        expr = parse_latex(s)
        return _extract_side(expr)
    except Exception:
        if "=" in s:
            _, rhs = s.split("=", 1)
            expr = sp.sympify(rhs.strip())
        else:
            expr = sp.sympify(s)
        return _extract_side(expr)


def verify_curve(
    formula_latex: str,
    var_name: str,
    sim_data_path: str | None = None,
    x_vals: list[float] | None = None,
    y_vals: list[float] | None = None,
    x_col: str = "x",
    y_col: str = "y",
    rtol: float = 1e-2,
    atol: float = 1e-3,
) -> dict[str, Any]:
    """Verify an analytical LaTeX formula against simulation data.

    Accepts empirical points either from a file (CSV or JSON) via `sim_data_path`
    or directly via `x_vals` and `y_vals` lists.

    Args:
        formula_latex: Closed-form expression in LaTeX format (e.g. ``\\frac{1}{1 + x^2}``).
        var_name: Independent variable symbol (e.g. "x", "t", "N").
        sim_data_path: Optional path to simulation file (.csv or .json).
        x_vals: Optional inline list of independent variable sample values.
        y_vals: Optional inline list of dependent variable simulation outputs.
        x_col: Column name or key for x data when loading from file (default: "x").
        y_col: Column name or key for y data when loading from file (default: "y").
        rtol: Relative tolerance for numpy.allclose comparison.
        atol: Absolute tolerance for numpy.allclose comparison.

    Returns:
        dict: Structured verification result including status ("VALID", "CURVE_MISMATCH",
            or "ERROR"), match flags, maximum/mean errors, monotonicity consistency,
            and deviation points.
    """
    try:
        # 1. Parse simulation data from inline lists or file
        x_list: list[float] = []
        y_list: list[float] = []

        if x_vals is not None or y_vals is not None:
            if x_vals is None or y_vals is None:
                return {
                    "status": "ERROR",
                    "error_message": "Both x_vals and y_vals must be provided for inline data verification.",
                    "message": "Both x_vals and y_vals must be provided for inline data verification.",
                }
            if len(x_vals) == 0 or len(y_vals) == 0:
                return {
                    "status": "ERROR",
                    "error_message": "Provided sample data lists are empty.",
                    "message": "Provided sample data lists are empty.",
                }
            if len(x_vals) != len(y_vals):
                return {
                    "status": "ERROR",
                    "error_message": f"Mismatched sample lengths: x_vals has {len(x_vals)} items, y_vals has {len(y_vals)} items.",
                    "message": f"Mismatched sample lengths: x_vals has {len(x_vals)} items, y_vals has {len(y_vals)} items.",
                }
            x_list = [float(v) for v in x_vals]
            y_list = [float(v) for v in y_vals]

        elif sim_data_path is not None:
            path = Path(sim_data_path)
            if not path.exists():
                return {
                    "status": "ERROR",
                    "error_message": f"Simulation file not found: {sim_data_path}",
                    "message": f"Simulation file not found: {sim_data_path}",
                }

            suffix = path.suffix.lower()
            if suffix == ".csv":
                with open(path, encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    if reader.fieldnames is None or x_col not in reader.fieldnames or y_col not in reader.fieldnames:
                        return {
                            "status": "ERROR",
                            "error_message": f"CSV columns '{x_col}' or '{y_col}' not found in file headers {reader.fieldnames}.",
                            "message": f"CSV columns '{x_col}' or '{y_col}' not found in file headers {reader.fieldnames}.",
                        }
                    for row in reader:
                        x_list.append(float(row[x_col]))
                        y_list.append(float(row[y_col]))

            elif suffix == ".json":
                with open(path, encoding="utf-8") as f:
                    raw_json = json.load(f)

                if isinstance(raw_json, dict):
                    if x_col not in raw_json or y_col not in raw_json:
                        return {
                            "status": "ERROR",
                            "error_message": f"JSON keys '{x_col}' or '{y_col}' not found in simulation dictionary.",
                            "message": f"JSON keys '{x_col}' or '{y_col}' not found in simulation dictionary.",
                        }
                    x_list = [float(v) for v in raw_json[x_col]]
                    y_list = [float(v) for v in raw_json[y_col]]
                elif isinstance(raw_json, list):
                    for idx, row in enumerate(raw_json):
                        if not isinstance(row, dict) or x_col not in row or y_col not in row:
                            return {
                                "status": "ERROR",
                                "error_message": f"JSON record at index {idx} does not contain '{x_col}' and '{y_col}'.",
                                "message": f"JSON record at index {idx} does not contain '{x_col}' and '{y_col}'.",
                            }
                        x_list.append(float(row[x_col]))
                        y_list.append(float(row[y_col]))
                else:
                    return {
                        "status": "ERROR",
                        "error_message": "JSON simulation file must contain a dict or list of dicts.",
                        "message": "JSON simulation file must contain a dict or list of dicts.",
                    }
            else:
                return {
                    "status": "ERROR",
                    "error_message": f"Unsupported simulation file format '{suffix}'. Supported: .csv, .json",
                    "message": f"Unsupported simulation file format '{suffix}'. Supported: .csv, .json",
                }

            if len(x_list) == 0:
                return {
                    "status": "ERROR",
                    "error_message": f"Simulation file {sim_data_path} contained no data rows.",
                    "message": f"Simulation file {sim_data_path} contained no data rows.",
                }
        else:
            return {
                "status": "ERROR",
                "error_message": "Either sim_data_path or both x_vals and y_vals must be provided.",
                "message": "Either sim_data_path or both x_vals and y_vals must be provided.",
            }

        x_arr = np.array(x_list, dtype=np.float64)
        y_sim = np.array(y_list, dtype=np.float64)

        # 2. Parse LaTeX or Python formula into SymPy symbolic expression
        var = sp.Symbol(var_name)
        expr = _parse_formula(formula_latex, var_name=var_name)

        # 3. Compile expression into numerical evaluator via lambdify
        f_num = sp.lambdify(var, expr, modules=["numpy", "scipy"])

        # 4. Evaluate analytical values over x_arr
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            y_theo_raw = f_num(x_arr)
        if np.isscalar(y_theo_raw) or (isinstance(y_theo_raw, np.ndarray) and y_theo_raw.shape == ()):
            y_theo = np.full_like(x_arr, float(np.asarray(y_theo_raw).item()), dtype=np.float64)
        else:
            y_theo = np.asarray(y_theo_raw, dtype=np.float64)

        # Check for division by zero, NaN, or Inf values
        if not np.all(np.isfinite(y_theo)):
            return {
                "status": "ERROR",
                "error_message": "Division by zero or non-finite result encountered during formula evaluation.",
                "message": "Division by zero or non-finite result encountered during formula evaluation.",
            }

        # 5. Compute discrepancy and match criteria
        discrepancy = np.abs(y_theo - y_sim)
        max_abs_err = float(np.max(discrepancy))
        mean_abs_err = float(np.mean(discrepancy))
        is_matched = bool(np.allclose(y_theo, y_sim, rtol=rtol, atol=atol))

        worst_idx = int(np.argmax(discrepancy))

        # Check monotonicity consistency
        if len(x_arr) > 1:
            theo_diff = np.diff(y_theo)
            sim_diff = np.diff(y_sim)
            monotonic_match = bool(np.all((theo_diff * sim_diff) >= -1e-9))
        else:
            monotonic_match = True

        worst_point = None
        if not is_matched:
            worst_point = {
                "x": float(x_arr[worst_idx]),
                "theoretical_y": float(y_theo[worst_idx]),
                "simulated_y": float(y_sim[worst_idx]),
                "error": max_abs_err,
            }

        return {
            "status": "VALID" if is_matched else "CURVE_MISMATCH",
            "is_correct": is_matched,
            "is_matched": is_matched,
            "formula": formula_latex,
            "variable": var_name,
            "rtol": rtol,
            "atol": atol,
            "max_error": max_abs_err,
            "max_absolute_error": max_abs_err,
            "mean_error": mean_abs_err,
            "mean_absolute_error": mean_abs_err,
            "monotonicity_consistent": monotonic_match,
            "sample_points_checked": len(x_arr),
            "worst_point": worst_point,
            "worst_at_x": float(x_arr[worst_idx]) if not is_matched else None,
            "analytical_values": [float(v) for v in y_theo],
            "simulated_values": [float(v) for v in y_sim],
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
            "message": str(e),
        }
