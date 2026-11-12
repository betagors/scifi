"""
FastMCP Router for Mathematical & Statistical Verification (Turing & Gauss).
"""

from __future__ import annotations

from typing import Any

from scifi.math import (
    check_convexity,
    check_limits,
    check_matrix_shapes,
    check_notation,
    check_units,
    verify_derivation_step,
    verify_derivative,
)
from scifi.server.app import mcp
from scifi.stats import audit_statistics, verify_curve


@mcp.tool()
def scifi_verify_derivative(
    expr: str,
    var: str,
    claimed: str,
) -> dict[str, Any]:
    """
    Symbolically verify an analytical derivative d(expr)/d(var) against a claimed expression using SymPy.

    Args:
        expr: Mathematical expression string or LaTeX (e.g. 'x**3 + 2*x' or '\\sin(x)').
        var: Differentiation variable (e.g. 'x').
        claimed: Claimed analytical derivative to verify against.

    Returns:
        Dictionary with status, is_correct flag, computed derivative, claimed derivative, and simplified difference.
    """
    return verify_derivative(expr=expr, var=var, claimed=claimed)


@mcp.tool()
def scifi_verify_derivation_step(
    lhs: str,
    rhs: str,
    assumptions: list[str] | None = None,
) -> dict[str, Any]:
    """
    Symbolically verify an algebraic derivation step asserting that LHS == RHS using SymPy.

    Args:
        lhs: Left-hand side mathematical expression.
        rhs: Right-hand side mathematical expression.
        assumptions: Optional list of algebraic assumptions (e.g. ['x > 0', 'n >= 1']).

    Returns:
        Dictionary with status, is_equivalent flag, simplified difference, and steps.
    """
    return verify_derivation_step(lhs=lhs, rhs=rhs, assumptions=assumptions)


@mcp.tool()
def scifi_check_units(
    lhs: str,
    rhs: str | None = None,
    check_mode: str = "eq",
) -> dict[str, Any]:
    """
    Verify physical dimensional homogeneity across equations or additive terms using Pint.

    Args:
        lhs: Left-hand expression with physical units (e.g. '10 * meter / second').
        rhs: Optional right-hand expression for equality checks (e.g. '36 * kilometer / hour').
        check_mode: 'eq' for equality or 'terms' for additive term consistency.

    Returns:
        Dictionary with status, is_consistent flag, reduced units, and dimensional analysis details.
    """
    return check_units(lhs=lhs, rhs=rhs, check_mode=check_mode)


@mcp.tool()
def scifi_check_matrix_shapes(
    operation: str,
    dimensions: dict[str, list[int | str]] | str,
) -> dict[str, Any]:
    """
    Verify linear algebra matrix product, vector multiplication, or tensor contraction shapes.

    Args:
        operation: Matrix operation string (e.g. 'A * B', 'A.T * B', 'X * W + b').
        dimensions: Dictionary mapping matrix symbols to shapes (e.g. {'A': [3, 4], 'B': [4, 5]}).

    Returns:
        Dictionary with status, is_valid flag, resulting shape, and step-by-step dimension propagation.
    """
    return check_matrix_shapes(operation=operation, dimensions=dimensions)


@mcp.tool()
def scifi_check_limits(
    expr: str,
    var: str,
    point: str,
    claimed: str,
    direction: str = "+-",
) -> dict[str, Any]:
    """
    Symbolically evaluate and verify asymptotic limits lim_{var -> point} expr == claimed using SymPy.

    Args:
        expr: Mathematical expression string or LaTeX.
        var: Limit variable (e.g. 'x', 'n').
        point: Limit target point (e.g. '0', 'oo', '-oo').
        claimed: Claimed limit value to verify against.
        direction: Approach direction: '+-' (bidirectional), '+' (right), or '-' (left).

    Returns:
        Dictionary with status, is_correct flag, computed limit, and claimed limit.
    """
    return check_limits(expr=expr, var=var, point=point, claimed=claimed, direction=direction)


@mcp.tool()
def scifi_check_convexity(
    expr: str,
    var: str,
    claimed: str = "convex",
) -> dict[str, Any]:
    """
    Verify convexity or concavity of a scalar objective function via its second derivative (Hessian).

    Args:
        expr: Objective expression string or LaTeX.
        var: Optimization variable (e.g. 'x').
        claimed: Claimed property: 'convex', 'strictly convex', 'concave', or 'strictly concave'.

    Returns:
        Dictionary with status, is_convex flag, second derivative expression, and sign analysis.
    """
    return check_convexity(expr=expr, var=var, claimed=claimed)


@mcp.tool()
def scifi_check_notation(
    tex_path: str,
    sections: list[str] | None = None,
) -> dict[str, Any]:
    """
    Audit manuscript LaTeX for mathematical symbol notation consistency, collisions, and overloading.

    Args:
        tex_path: Path to LaTeX manuscript file or raw LaTeX content.
        sections: Optional list of sections to restrict the audit to.

    Returns:
        Dictionary with status, symbols_found, collisions, and notation recommendations.
    """
    return check_notation(tex_content_or_path=tex_path, sections=sections)


@mcp.tool()
def scifi_verify_curve(
    formula_latex: str,
    var_name: str,
    sim_data_path: str | None = None,
    x_vals: list[float] | None = None,
    y_vals: list[float] | None = None,
    x_col: str = "x",
    y_col: str = "y",
    rtol: float = 0.01,
    atol: float = 0.001,
) -> dict[str, Any]:
    """
    Verify that theoretical closed-form LaTeX formulas align with empirical simulation curves.

    Args:
        formula_latex: Theoretical mathematical equation (e.g. 'y = 2*x + 1' or '2*x + 1').
        var_name: Independent variable symbol (e.g. 'x').
        sim_data_path: Optional path to CSV or JSON file containing simulation points.
        x_vals: Optional list of independent variable sample values.
        y_vals: Optional list of empirical simulation values.
        x_col: Column name for x in CSV/JSON data (default: 'x').
        y_col: Column name for y in CSV/JSON data (default: 'y').
        rtol: Relative tolerance for numerical alignment (default: 0.01 = 1%).
        atol: Absolute tolerance for numerical alignment (default: 0.001).

    Returns:
        Dictionary with status, is_aligned flag, max_relative_error, max_absolute_error, and comparisons.
    """
    return verify_curve(
        formula_latex=formula_latex,
        var_name=var_name,
        sim_data_path=sim_data_path,
        x_vals=x_vals,
        y_vals=y_vals,
        x_col=x_col,
        y_col=y_col,
        rtol=rtol,
        atol=atol,
    )


@mcp.tool()
def scifi_audit_statistics(
    samples: list[float],
    confidence: float = 0.95,
) -> dict[str, Any]:
    """
    Audit empirical simulation data: compute confidence intervals and check Central Limit Theorem sample size (N >= 30).

    Args:
        samples: Array of numerical data observations.
        confidence: Confidence level for the interval (default: 0.95 for 95% CI).

    Returns:
        Dictionary with sample_size, mean, std_dev, std_error, confidence_interval, and clt_warning.
    """
    return audit_statistics(samples=samples, confidence=confidence)
