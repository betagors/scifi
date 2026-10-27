#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "sympy",
# ]
# ///
"""
Turing – Matrix Dimension & Tensor Shape Verifier.

Validates symbolic matrix expressions without substituting concrete numbers.
Raises ShapeError for mismatched products and reports the result as JSON.

Usage
-----
python verify_matrix_shapes.py \
    --matrices "A:m:n,B:n:k" \
    --expr "A * B"

python verify_matrix_shapes.py \
    --matrices "A:m:n,B:n:k,C:m:k" \
    --expr "A * B - C"

Matrices are specified as NAME:ROWS:COLS.
Symbols used in dimensions (m, n, k, ...) are treated as generic positive integers.
"""
import argparse
import json
import sympy as sp
from sympy.matrices.expressions import MatrixSymbol

# SymPy >= 1.12 moved ShapeError; support both locations.
try:
    from sympy.matrices.common import ShapeError as _ShapeError
except ImportError:
    from sympy.matrices.exceptions import ShapeError as _ShapeError

def parse_matrices(spec: str) -> dict:
    """
    Parse "A:m:n,B:n:k" into {name: MatrixSymbol}.
    Dimension tokens that are integers are converted; otherwise treated as Symbols.
    """
    result = {}
    dim_syms = {}
    for entry in spec.split(","):
        parts = entry.strip().split(":")
        if len(parts) != 3:
            raise ValueError(f"Invalid matrix spec '{entry}'. Expected NAME:ROWS:COLS.")
        name, rows_tok, cols_tok = parts

        def as_dim(tok):
            try:
                return int(tok)
            except ValueError:
                if tok not in dim_syms:
                    dim_syms[tok] = sp.Symbol(tok, positive=True, integer=True)
                return dim_syms[tok]

        result[name] = MatrixSymbol(name, as_dim(rows_tok), as_dim(cols_tok))
    return result

def verify_shape(matrices_spec: str, expr_str: str) -> dict:
    try:
        matrices = parse_matrices(matrices_spec)
        # Build a local namespace for eval with sympy basics
        namespace = {**matrices}
        namespace.update({
            "Transpose": sp.transpose,
            "Inverse": sp.Inverse,
            "Identity": sp.Identity,
        })
        expr = eval(expr_str, {"__builtins__": {}}, namespace)
        shape = expr.shape
        return {
            "status": "VALID",
            "is_correct": True,
            "expression": expr_str,
            "result_shape": [str(s) for s in shape],
            "matrices": {
                k: {"rows": str(v.shape[0]), "cols": str(v.shape[1])}
                for k, v in matrices.items()
            },
        }
    except _ShapeError as e:
        return {
            "status": "SHAPE_ERROR",
            "is_correct": False,
            "error_message": str(e),
            "hint": "Matrix dimensions are incompatible for the requested operation.",
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
            "hint": "Ensure matrix names in --expr exactly match those declared in --matrices.",
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Turing: Matrix dimension & tensor shape verifier"
    )
    parser.add_argument(
        "--matrices", required=True,
        help="Comma-separated list of matrix specs: NAME:ROWS:COLS (e.g. A:m:n,B:n:k)"
    )
    parser.add_argument(
        "--expr", required=True,
        help="Symbolic matrix expression to evaluate (e.g. 'A * B - C')"
    )
    args = parser.parse_args()
    res = verify_shape(args.matrices, args.expr)
    print(json.dumps(res, indent=2))
