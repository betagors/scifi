"""
Math and Statistics Subcommand Handlers (`sf math`, `sf stats`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_math(args: argparse.Namespace) -> int:
    """Execute Turing mathematical verification subcommands (`sf math`)."""
    from scifi.math import (
        check_convexity,
        check_limits,
        check_matrix_shapes,
        check_notation,
        check_units,
        verify_derivation_step,
        verify_derivative,
    )

    sub = getattr(args, "math_command", None)
    if sub == "derivative":
        res = verify_derivative(args.expression, args.variable, args.claimed)
    elif sub == "step":
        res = verify_derivation_step(args.lhs, args.rhs, assumptions=args.assumptions)
    elif sub == "units":
        res = check_units(args.expression, check_mode=args.mode)
    elif sub == "shapes":
        try:
            shapes_dict = json.loads(args.shapes)
        except Exception as e:
            print(f"[ERROR] Invalid JSON for --shapes: {e}", file=sys.stderr)
            return 1
        res = check_matrix_shapes(args.expression, shapes_dict)
    elif sub == "limits":
        res = check_limits(
            args.expression, args.variable, point=args.tends_to, claimed=args.expected, direction=args.direction
        )
    elif sub == "convexity":
        res = check_convexity(args.expression, args.variables)
    elif sub == "notation":
        res = check_notation(args.target)
    else:
        print(
            "[ERROR] Specify a math subcommand: derivative, step, units, shapes, limits, convexity, notation",
            file=sys.stderr,
        )
        return 1

    print(json.dumps(res, indent=2))
    return 0 if res.get("is_correct", res.get("status") in ("VALID", "SUCCESS")) else 1


def cmd_stats(args: argparse.Namespace) -> int:
    """Execute Gauss statistical & curve verification subcommands (`sf stats`)."""
    from scifi.stats import audit_statistics, verify_curve

    sub = getattr(args, "stats_command", None)
    if sub == "curve":
        res = verify_curve(
            args.formula,
            getattr(args, "var_name", "x") or "x",
            sim_data_path=args.data_path,
            x_col=args.x_col,
            y_col=args.y_col,
            rtol=getattr(args, "tolerance", 1e-2),
        )
    elif sub == "audit":
        raw = args.values
        try:
            if raw.strip().startswith("[") or raw.strip().startswith("{") or Path(raw).exists():
                parsed_input = json.loads(raw) if raw.strip().startswith(("[", "{")) else raw
            else:
                parsed_input = [float(x.strip()) for x in raw.split(",") if x.strip()]
        except Exception:
            parsed_input = raw
        res = audit_statistics(parsed_input, confidence=args.confidence)
    else:
        print("[ERROR] Specify a stats subcommand: curve, audit", file=sys.stderr)
        return 1

    print(json.dumps(res, indent=2))
    return 0 if res.get("status") in ("VALID", "SUCCESS") else 1
