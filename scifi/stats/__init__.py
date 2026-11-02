"""
SciFi Statistics & Numerical Subpackage (scifi.stats).

Consolidates Gauss and Turing statistical and curve verification engines:
- Curve Fitting & Verification: Compares analytical formulas against simulation data
- Hypothesis Testing: Statistical significance, confidence intervals, sample size audit
"""

from scifi.stats.curve_fit import (
    verify_curve,
)
from scifi.stats.hypothesis import (
    audit_sample_statistics,
    audit_statistics,
)

__all__ = [
    "verify_curve",
    "audit_statistics",
    "audit_sample_statistics",
]
