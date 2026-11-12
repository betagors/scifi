"""
Dimensional consistency and physical unit verification engine (scifi.math.units).
"""

from __future__ import annotations

from typing import Any

import pint

_ureg = pint.UnitRegistry()


def check_units(
    lhs: str,
    rhs: str | None = None,
    check_mode: str = "eq",
) -> dict[str, Any]:
    """
    Check dimensional consistency using Pint unit registry.

    Args:
        lhs: Primary unit expression or comma-separated terms (for check_mode='add').
        rhs: Secondary unit expression to compare against (for check_mode='eq').
        check_mode: 'eq' (assert lhs and rhs match dimensionality) or
                    'add' / 'terms' (assert all terms share the same dimensionality).
    """
    try:
        mode = check_mode.strip().lower()
        if mode == "eq":
            if rhs is None:
                return {
                    "status": "ERROR",
                    "error_message": "rhs is required for eq check",
                }
            lhs_q = _ureg.parse_expression(lhs)
            rhs_q = _ureg.parse_expression(rhs)

            lhs_dim = lhs_q.dimensionality
            rhs_dim = rhs_q.dimensionality
            is_compatible = bool(lhs_dim == rhs_dim)

            res: dict[str, Any] = {
                "status": "VALID" if is_compatible else "DIMENSION_MISMATCH",
                "is_correct": is_compatible,
                "lhs_dimensionality": str(lhs_dim),
                "rhs_dimensionality": str(rhs_dim),
            }
            if not is_compatible:
                res["hint"] = (
                    f"LHS has dimension {lhs_dim} but RHS has dimension {rhs_dim}. "
                    "The equation is dimensionally inconsistent."
                )
            return res

        elif mode in ("add", "terms"):
            terms = [t.strip() for t in lhs.split(",") if t.strip()]
            if rhs:
                terms.extend([t.strip() for t in rhs.split(",") if t.strip()])

            if not terms:
                return {
                    "status": "ERROR",
                    "error_message": "No terms provided for additive dimension check.",
                }

            quantities = [_ureg.parse_expression(t) for t in terms]
            dims = [q.dimensionality for q in quantities]
            ref_dim = dims[0]

            mismatches = [{"term": terms[i], "dimensionality": str(d)} for i, d in enumerate(dims) if d != ref_dim]
            is_compatible = len(mismatches) == 0

            res = {
                "status": "VALID" if is_compatible else "DIMENSION_MISMATCH",
                "is_correct": is_compatible,
                "reference_dimensionality": str(ref_dim),
            }
            if mismatches:
                res["mismatched_terms"] = mismatches
                res["hint"] = "All additive terms must share the same physical dimension."
            return res

        else:
            return {
                "status": "ERROR",
                "error_message": f"Unsupported check_mode '{check_mode}'. Expected 'eq', 'add', or 'terms'.",
            }

    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
        }
