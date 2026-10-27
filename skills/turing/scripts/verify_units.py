#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pint",
# ]
# ///
"""
Turing – Dimensional / Unit Consistency Checker.

Usage
-----
python verify_units.py --lhs "5 watt * second" --rhs "5 joule"
python verify_units.py --lhs "10 meter / second" --rhs "3 meter / second" --check add

--check can be:
  eq   (default) – assert lhs and rhs have the same base dimensions
  add             – assert multiple comma-separated terms (--lhs only) can be added
"""
import argparse
import json
from typing import Optional

try:
    import pint
except ImportError:
    print(json.dumps({
        "status": "ERROR",
        "error_message": "pint is not installed. Run: uv add pint",
    }))
    raise SystemExit(1)

ureg = pint.UnitRegistry()

def _parse(expr: str):
    """Parse a unit expression, returning a Pint Quantity."""
    return ureg.parse_expression(expr)

def check_equality(lhs_str: str, rhs_str: str) -> dict:
    """Assert both sides reduce to the same dimensionality."""
    try:
        lhs = _parse(lhs_str)
        rhs = _parse(rhs_str)
        lhs_dim = lhs.dimensionality
        rhs_dim = rhs.dimensionality
        compatible = (lhs_dim == rhs_dim)
        result = {
            "status": "VALID" if compatible else "DIMENSION_MISMATCH",
            "is_correct": compatible,
            "lhs_dimensionality": str(lhs_dim),
            "rhs_dimensionality": str(rhs_dim),
        }
        if not compatible:
            result["hint"] = (
                f"LHS has dimension {lhs_dim} but RHS has dimension {rhs_dim}. "
                "The equation is dimensionally inconsistent."
            )
        return result
    except Exception as e:
        return {"status": "ERROR", "error_message": str(e)}

def check_additive(*term_strs: str) -> dict:
    """Assert all terms share the same dimensionality (required for addition)."""
    try:
        terms = [_parse(t.strip()) for t in term_strs]
        dims = [t.dimensionality for t in terms]
        reference = dims[0]
        mismatches = [
            {"term": str(term_strs[i]), "dimensionality": str(dims[i])}
            for i, d in enumerate(dims) if d != reference
        ]
        ok = len(mismatches) == 0
        result = {
            "status": "VALID" if ok else "DIMENSION_MISMATCH",
            "is_correct": ok,
            "reference_dimensionality": str(reference),
        }
        if mismatches:
            result["mismatched_terms"] = mismatches
            result["hint"] = "All additive terms must share the same physical dimension."
        return result
    except Exception as e:
        return {"status": "ERROR", "error_message": str(e)}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Turing: Dimensional / unit consistency checker"
    )
    parser.add_argument("--lhs", required=True,
                        help="LHS quantity expression, or comma-separated list of terms for --check add")
    parser.add_argument("--rhs", default=None,
                        help="RHS quantity expression (used with --check eq)")
    parser.add_argument("--check", choices=["eq", "add"], default="eq",
                        help="Verification mode: eq (equality) or add (additive compatibility)")
    args = parser.parse_args()

    if args.check == "add":
        terms = [t.strip() for t in args.lhs.split(",")]
        res = check_additive(*terms)
    else:
        if args.rhs is None:
            res = {"status": "ERROR", "error_message": "--rhs is required for --check eq"}
        else:
            res = check_equality(args.lhs, args.rhs)

    print(json.dumps(res, indent=2))
