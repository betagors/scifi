"""
Unit tests for Gauss & Turing Numerical and Statistical engines (scifi.stats).
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure scifi package is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scifi.stats import (
    audit_statistics,
    verify_curve,
)


class TestVerifyCurve(unittest.TestCase):
    def test_verify_curve_inline_valid_linear(self):
        """Verify linear equation y = 2x with inline arrays."""
        x_vals = [0.0, 1.0, 2.0, 3.0, 4.0]
        y_vals = [0.0, 2.0, 4.0, 6.0, 8.0]
        res = verify_curve(
            formula_latex=r"2 x",
            var_name="x",
            x_vals=x_vals,
            y_vals=y_vals,
        )
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])
        self.assertAlmostEqual(res["max_error"], 0.0, places=5)
        self.assertEqual(res["sample_points_checked"], 5)
        self.assertTrue(res["monotonicity_consistent"])

    def test_verify_curve_inline_valid_fraction(self):
        """Verify 1/(1+x^2) with inline arrays."""
        x_vals = [0.0, 1.0, 2.0, 3.0]
        y_vals = [1.0 / (1.0 + x**2) for x in x_vals]
        res = verify_curve(
            formula_latex=r"\frac{1}{1 + x^2}",
            var_name="x",
            x_vals=x_vals,
            y_vals=y_vals,
            rtol=1e-3,
            atol=1e-4,
        )
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])
        self.assertLess(res["max_error"], 1e-4)

    def test_verify_curve_csv_file(self):
        """Verify reading from CSV simulation file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "sim.csv")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("x,y\n")
                f.write("0.0,0.0\n")
                f.write("1.0,1.0\n")
                f.write("2.0,4.0\n")
                f.write("3.0,9.0\n")

            res = verify_curve(
                formula_latex=r"x^2",
                var_name="x",
                sim_data_path=csv_path,
                x_col="x",
                y_col="y",
            )
            self.assertEqual(res["status"], "VALID")
            self.assertTrue(res["is_correct"])
            self.assertEqual(res["sample_points_checked"], 4)

    def test_verify_curve_json_dict_file(self):
        """Verify reading from JSON simulation file with column arrays."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = os.path.join(tmpdir, "sim.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({"x": [1.0, 2.0, 3.0], "y": [3.0, 6.0, 9.0]}, f)

            res = verify_curve(
                formula_latex=r"3 x",
                var_name="x",
                sim_data_path=json_path,
            )
            self.assertEqual(res["status"], "VALID")
            self.assertTrue(res["is_correct"])
            self.assertEqual(res["sample_points_checked"], 3)

    def test_verify_curve_json_records_file(self):
        """Verify reading from JSON simulation file with list of records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = os.path.join(tmpdir, "records.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump([
                    {"x": 1.0, "y": 2.0},
                    {"x": 2.0, "y": 4.0},
                    {"x": 3.0, "y": 6.0},
                ], f)

            res = verify_curve(
                formula_latex=r"2 x",
                var_name="x",
                sim_data_path=json_path,
            )
            self.assertEqual(res["status"], "VALID")
            self.assertTrue(res["is_correct"])
            self.assertEqual(res["sample_points_checked"], 3)

    def test_verify_curve_mismatch(self):
        """Verify detection of mismatch between curve and simulation points."""
        x_vals = [1.0, 2.0, 3.0]
        y_vals = [10.0, 20.0, 30.0]  # formula predicts 2, 4, 6
        res = verify_curve(
            formula_latex=r"2 x",
            var_name="x",
            x_vals=x_vals,
            y_vals=y_vals,
        )
        self.assertEqual(res["status"], "CURVE_MISMATCH")
        self.assertFalse(res["is_correct"])
        self.assertGreater(res["max_error"], 5.0)
        self.assertIsNotNone(res["worst_point"])
        self.assertEqual(res["worst_point"]["x"], 3.0)

    def test_verify_curve_missing_file(self):
        """Verify error handling on non-existent file path."""
        res = verify_curve(
            formula_latex=r"2 x",
            var_name="x",
            sim_data_path="non_existent_data_file.csv",
        )
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("error_message", res)

    def test_verify_curve_invalid_latex(self):
        """Verify error handling when LaTeX syntax is malformed."""
        res = verify_curve(
            formula_latex=r"\frac{1}{{{broken",
            var_name="x",
            x_vals=[1.0, 2.0],
            y_vals=[1.0, 2.0],
        )
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("error_message", res)

    def test_verify_curve_empty_data(self):
        """Verify error handling when data is empty."""
        res = verify_curve(
            formula_latex=r"2 x",
            var_name="x",
            x_vals=[],
            y_vals=[],
        )
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("error_message", res)

    def test_verify_curve_mismatched_lengths(self):
        """Verify error handling when x and y have mismatched lengths."""
        res = verify_curve(
            formula_latex=r"2 x",
            var_name="x",
            x_vals=[1.0, 2.0],
            y_vals=[1.0],
        )
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("error_message", res)

    def test_verify_curve_division_by_zero(self):
        """Verify error handling when evaluation hits division by zero / nan / inf."""
        res = verify_curve(
            formula_latex=r"\frac{1}{x}",
            var_name="x",
            x_vals=[0.0, 1.0],
            y_vals=[0.0, 1.0],
        )
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("error_message", res)

    def test_verify_curve_no_data_specified(self):
        """Verify error handling when neither sim_data_path nor x_vals/y_vals are passed."""
        res = verify_curve(
            formula_latex=r"2 x",
            var_name="x",
        )
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("error_message", res)


class TestAuditStatistics(unittest.TestCase):
    def test_audit_statistics_sound_n_ge_30(self):
        """Verify sample statistics calculation with N >= 30."""
        samples = [float(i) for i in range(35)]
        res = audit_statistics(samples, confidence=0.95)
        self.assertEqual(res["status"], "VALID")
        self.assertEqual(res["sample_size"], 35)
        self.assertTrue(res["is_statistically_sound"])
        self.assertIsNone(res["warning"])
        self.assertAlmostEqual(res["mean"], 17.0, places=5)
        self.assertGreater(res["standard_error"], 0.0)
        self.assertGreater(res["margin_of_error"], 0.0)
        low, high = res["confidence_interval"]
        self.assertLess(low, 17.0)
        self.assertGreater(high, 17.0)

    def test_audit_statistics_warning_n_lt_30(self):
        """Verify sample statistics with N < 30 returns warning regarding CLT."""
        samples = [1.0, 2.0, 3.0, 4.0, 5.0]
        res = audit_statistics(samples, confidence=0.95)
        self.assertEqual(res["status"], "VALID")
        self.assertEqual(res["sample_size"], 5)
        self.assertFalse(res["is_statistically_sound"])
        self.assertIsNotNone(res["warning"])
        self.assertIn("30", res["warning"])
        self.assertAlmostEqual(res["mean"], 3.0, places=5)

    def test_audit_statistics_error_n_lt_2(self):
        """Verify error status when sample size is less than 2."""
        res_single = audit_statistics([42.0])
        self.assertEqual(res_single["status"], "ERROR")
        self.assertIn("error_message", res_single)

        res_empty = audit_statistics([])
        self.assertEqual(res_empty["status"], "ERROR")
        self.assertIn("error_message", res_empty)

    def test_audit_statistics_custom_confidence(self):
        """Verify confidence intervals scale with higher confidence level."""
        samples = [float(i) for i in range(50)]
        res_90 = audit_statistics(samples, confidence=0.90)
        res_99 = audit_statistics(samples, confidence=0.99)
        self.assertLess(res_90["margin_of_error"], res_99["margin_of_error"])


if __name__ == "__main__":
    unittest.main()
