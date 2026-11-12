"""
Hypothesis testing and statistical significance audit engine.

Consolidates Gauss empirical simulation audit into a unified interface
for confidence intervals, standard errors, and sample size verification.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from scipy import stats


def audit_statistics(
    samples: Sequence[float],
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Audit empirical sample data for statistical significance and confidence intervals.

    Checks if sample size $N \\ge 30$ according to the Central Limit Theorem threshold,
    computes mean, standard error, and Student's t-distribution confidence interval.

    Args:
        samples: Array or list of numerical sample values. At least 2 points are required.
        confidence: Confidence level (between 0.0 and 1.0, default 0.95).

    Returns:
        dict: Statistical analysis results containing status, sample size, mean,
            standard error, margin of error, confidence interval, and CLT warnings.
    """
    try:
        if samples is None:
            return {
                "status": "ERROR",
                "error_message": "Samples sequence cannot be None.",
                "message": "Samples sequence cannot be None.",
            }

        arr = np.array(samples, dtype=np.float64)
        n = len(arr)

        if n < 2:
            return {
                "status": "ERROR",
                "error_message": f"At least 2 sample points required for statistical audit, got {n}.",
                "message": f"At least 2 sample points required for statistical audit, got {n}.",
            }

        if not (0.0 < confidence < 1.0):
            return {
                "status": "ERROR",
                "error_message": f"Confidence level must be strictly between 0 and 1, got {confidence}.",
                "message": f"Confidence level must be strictly between 0 and 1, got {confidence}.",
            }

        mean = float(np.mean(arr))
        std_err = float(stats.sem(arr))

        # Margin of error using Student's t-distribution with df = n - 1
        t_crit = float(stats.t.ppf((1.0 + confidence) / 2.0, df=n - 1))
        h = float(std_err * t_crit)

        is_statistically_sound = n >= 30
        ci_key = f"{int(round(confidence * 100))}%_confidence_interval"
        ci = [mean - h, mean + h]

        warning = (
            None
            if is_statistically_sound
            else f"Sample size N = {n} (< 30). Central Limit Theorem threshold not met; statistical significance may be challenged by peer reviewers."
        )

        return {
            "status": "VALID",
            "sample_size": n,
            "n": n,
            "is_statistically_sound": is_statistically_sound,
            "mean": mean,
            "standard_error": std_err,
            "confidence": confidence,
            "margin_of_error": h,
            "confidence_interval": ci,
            ci_key: ci,
            "warning": warning,
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
            "message": str(e),
        }


# Alias for backwards compatibility with gauss script
audit_sample_statistics = audit_statistics
