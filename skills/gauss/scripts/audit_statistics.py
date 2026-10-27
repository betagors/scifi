#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "numpy",
#     "scipy",
# ]
# ///
import argparse
import json
import numpy as np
from scipy import stats


def audit_sample_statistics(data_array: list[float], confidence: float = 0.95) -> dict:
    arr = np.array(data_array, dtype=np.float64)
    n = len(arr)
    if n < 2:
        return {"status": "ERROR", "message": "At least 2 sample points required for statistical audit."}

    mean = float(np.mean(arr))
    std_err = float(stats.sem(arr))
    h = float(std_err * stats.t.ppf((1 + confidence) / 2.0, n - 1))

    # Flag small sample size (CLT threshold)
    is_statistically_sound = n >= 30

    ci_key = f"{int(confidence * 100)}%_confidence_interval"

    return {
        "status": "VALID",
        "sample_size": n,
        "is_statistically_sound": is_statistically_sound,
        "mean": mean,
        "standard_error": std_err,
        ci_key: [mean - h, mean + h],
        "margin_of_error": h,
        "warning": None
        if is_statistically_sound
        else "Sample size N < 30. Reviewers may challenge statistical significance.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit empirical simulation confidence intervals")
    parser.add_argument("--samples", nargs="+", type=float, required=True, help="List of sample values")
    parser.add_argument("--conf", type=float, default=0.95, help="Confidence level (e.g. 0.95)")
    args = parser.parse_args()
    print(json.dumps(audit_sample_statistics(args.samples, args.conf), indent=2))
