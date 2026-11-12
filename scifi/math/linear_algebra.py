"""
Matrix and tensor shape verification engine (scifi.math.linear_algebra).
"""

from __future__ import annotations

import ast
from typing import Any
import sympy as sp
from sympy.matrices.expressions import MatrixSymbol

try:
    from sympy.matrices.common import ShapeError
except ImportError:
    from sympy.matrices.exceptions import ShapeError

_ALLOWED_OPERATORS = (ast.Add, ast.Sub, ast.Mult, ast.MatMult)
_ALLOWED_UNARY = (ast.USub, ast.UAdd)


def _validate_operation(operation: str) -> None:
    """Validate matrix arithmetic expression AST to prevent unsafe execution.

    Only allows binary operations (+, -, *, @), unary operations (+, -),
    variable names, numeric constants, and .T transpose attribute access.
    """
    tree = ast.parse(operation.strip(), mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.Load, *_ALLOWED_OPERATORS, *_ALLOWED_UNARY)):
            continue
        elif isinstance(node, ast.BinOp):
            if not isinstance(node.op, _ALLOWED_OPERATORS):
                raise ValueError(f"Disallowed binary operator '{type(node.op).__name__}' in operation.")
        elif isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, _ALLOWED_UNARY):
                raise ValueError(f"Disallowed unary operator '{type(node.op).__name__}' in operation.")
        elif isinstance(node, ast.Attribute):
            if node.attr != "T":
                raise ValueError(f"Disallowed attribute access '.{node.attr}' in operation. Only '.T' is permitted.")
        elif isinstance(node, (ast.Name, ast.Constant)):
            continue
        else:
            raise ValueError(f"Disallowed syntax element '{type(node).__name__}' in matrix operation.")


def _parse_dimensions(
    dimensions: dict[str, list[int | str]] | str,
) -> tuple[dict[str, MatrixSymbol], dict[str, sp.Symbol]]:
    """
    Parse dimensions from either a dict or spec string into MatrixSymbol objects.
    """
    matrices: dict[str, MatrixSymbol] = {}
    dim_syms: dict[str, sp.Symbol] = {}

    def as_dim(tok: int | str) -> int | sp.Symbol:
        try:
            return int(tok)
        except ValueError:
            s_tok = str(tok).strip()
            if s_tok not in dim_syms:
                dim_syms[s_tok] = sp.Symbol(s_tok, positive=True, integer=True)
            return dim_syms[s_tok]

    if isinstance(dimensions, str):
        for entry in dimensions.split(","):
            parts = entry.strip().split(":")
            if len(parts) != 3:
                raise ValueError(
                    f"Invalid matrix specification '{entry}'. Expected NAME:ROWS:COLS format."
                )
            name, rows_tok, cols_tok = parts
            matrices[name.strip()] = MatrixSymbol(
                name.strip(), as_dim(rows_tok.strip()), as_dim(cols_tok.strip())
            )
    elif isinstance(dimensions, dict):
        for name, shape in dimensions.items():
            if not isinstance(shape, (list, tuple)) or len(shape) != 2:
                raise ValueError(
                    f"Matrix '{name}' shape must be a list/tuple of [rows, cols]."
                )
            r_tok, c_tok = shape
            matrices[name.strip()] = MatrixSymbol(
                name.strip(), as_dim(r_tok), as_dim(c_tok)
            )
    else:
        raise TypeError(
            f"dimensions must be a dict or a string, got {type(dimensions).__name__}"
        )

    return matrices, dim_syms


def check_matrix_shapes(
    operation: str,
    dimensions: dict[str, list[int | str]] | str,
) -> dict[str, Any]:
    """
    Validate matrix dimension compatibility and compute the resulting expression shape.

    Args:
        operation: Matrix arithmetic expression (e.g., 'A * B', 'A * B - C', 'A * B.T').
        dimensions: Dict of shapes (e.g. {'A': ['m', 'n']}) or string spec ('A:m:n,B:n:k').
    """
    try:
        _validate_operation(operation)
        matrices, _ = _parse_dimensions(dimensions)
        namespace: dict[str, Any] = {**matrices}
        namespace.update({
            "Transpose": sp.transpose,
            "Inverse": sp.Inverse,
            "Identity": sp.Identity,
        })

        expr = eval(operation, {"__builtins__": {}}, namespace)
        shape = expr.shape

        return {
            "status": "VALID",
            "is_correct": True,
            "operation": operation,
            "result_shape": [str(s) for s in shape],
            "matrices": {
                k: {"rows": str(v.shape[0]), "cols": str(v.shape[1])}
                for k, v in matrices.items()
            },
        }
    except ShapeError as e:
        return {
            "status": "SHAPE_MISMATCH",
            "is_correct": False,
            "error_message": str(e),
            "hint": "Matrix dimensions are incompatible for the requested operation.",
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
            "hint": "Ensure matrix names match declared matrices and expression syntax is valid.",
        }
