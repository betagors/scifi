"""
SciFi Mathematical & Physics Verification Subpackage (scifi.math).

Consolidates Turing verification engines:
- Calculus: derivatives, derivation steps, boundary limits
- Units: Pint-powered physical dimension checking
- Linear Algebra: Matrix and tensor shape checking
- Convexity: Hessian analysis and definiteness checking
- Notation: LaTeX manuscript notation consistency checking
"""

from scifi.math.calculus import (
    check_limits,
    verify_derivation_step,
    verify_derivative,
)
from scifi.math.convexity import (
    check_convexity,
)
from scifi.math.linear_algebra import (
    check_matrix_shapes,
)
from scifi.math.notation import (
    check_notation,
)
from scifi.math.units import (
    check_units,
)

__all__ = [
    "verify_derivative",
    "verify_derivation_step",
    "check_limits",
    "check_units",
    "check_matrix_shapes",
    "check_convexity",
    "check_notation",
]
