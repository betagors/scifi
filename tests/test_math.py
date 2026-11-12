"""
Unit tests for Turing Mathematical and Physics verification engines (scifi.math).
"""

import sys
import tempfile
import unittest
from pathlib import Path

# Ensure scifi package is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scifi.math import (
    check_convexity,
    check_limits,
    check_matrix_shapes,
    check_notation,
    check_units,
    verify_derivation_step,
    verify_derivative,
)


class TestCalculus(unittest.TestCase):
    def test_verify_derivative_valid(self):
        # d/dx (x^3) = 3*x^2
        res = verify_derivative(r"x^3", "x", r"3 x^2")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])
        self.assertEqual(res["variable"], "x")
        self.assertIn("computed_derivative", res)

    def test_verify_derivative_invalid(self):
        # d/dx (x^3) != 2*x
        res = verify_derivative(r"x^3", "x", r"2 x")
        self.assertEqual(res["status"], "INVALID_DERIVATION")
        self.assertFalse(res["is_correct"])
        self.assertIn("discrepancy", res)

    def test_verify_derivative_malformed_latex(self):
        res = verify_derivative(r"\frac{1}", "x", r"x")
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("error_message", res)

    def test_verify_derivation_step_valid(self):
        # (x + 1)^2 == x^2 + 2x + 1
        res = verify_derivation_step(r"(x + 1)^2", r"x^2 + 2x + 1")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])

    def test_verify_derivation_step_invalid(self):
        res = verify_derivation_step(r"x + 1", r"x + 2")
        self.assertEqual(res["status"], "INVALID_DERIVATION")
        self.assertFalse(res["is_correct"])
        self.assertIn("discrepancy", res)

    def test_verify_derivation_step_with_assumptions(self):
        # sqrt(x^2) == x for x > 0
        res = verify_derivation_step(r"\sqrt{x^2}", r"x", assumptions=["x > 0"])
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])

    def test_verify_derivation_step_malformed(self):
        res = verify_derivation_step(r"\frac{1}", r"x")
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("error_message", res)

    def test_check_limits_finite(self):
        # lim_{x -> 0} sin(x)/x = 1
        res = check_limits(r"\frac{\sin(x)}{x}", "x", "0", "1")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])

    def test_check_limits_infinity(self):
        # lim_{N -> oo} 1/N = 0
        res = check_limits(r"\frac{1}{N}", "N", "oo", "0")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])

    def test_check_limits_divergence(self):
        # lim_{x -> 0} 1/x diverges
        res = check_limits(r"\frac{1}{x}", "x", "0", "0")
        self.assertEqual(res["status"], "INVALID_LIMIT")
        self.assertFalse(res["is_correct"])

    def test_check_limits_one_sided(self):
        # lim_{x -> 0^+} 1/x = oo
        res = check_limits(r"\frac{1}{x}", "x", "0", "oo", direction="+")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])


class TestUnits(unittest.TestCase):
    def test_check_units_equal_dimensions(self):
        res = check_units("5 watt * second", "5 joule", check_mode="eq")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])
        self.assertIn("lhs_dimensionality", res)
        self.assertIn("rhs_dimensionality", res)

    def test_check_units_dimension_mismatch(self):
        res = check_units("10 meter", "10 second", check_mode="eq")
        self.assertEqual(res["status"], "DIMENSION_MISMATCH")
        self.assertFalse(res["is_correct"])
        self.assertIn("hint", res)

    def test_check_units_additive_valid(self):
        res = check_units("10 meter, 5 meter, 2 meter", check_mode="add")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])

    def test_check_units_additive_mismatch(self):
        res = check_units("10 meter, 5 second", check_mode="add")
        self.assertEqual(res["status"], "DIMENSION_MISMATCH")
        self.assertFalse(res["is_correct"])
        self.assertIn("mismatched_terms", res)

    def test_check_units_terms_mode_valid(self):
        res = check_units("10 meter, 5 meter, 2 meter", check_mode="terms")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])

    def test_check_units_terms_mode_mismatch(self):
        res = check_units("10 meter, 5 second", check_mode="terms")
        self.assertEqual(res["status"], "DIMENSION_MISMATCH")
        self.assertFalse(res["is_correct"])

    def test_check_units_missing_rhs_in_eq(self):
        res = check_units("5 joule", check_mode="eq")
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("error_message", res)

    def test_check_units_invalid_syntax(self):
        res = check_units("5 non_existent_unit_xyz", "5 joule")
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("error_message", res)


class TestLinearAlgebra(unittest.TestCase):
    def test_check_matrix_shapes_valid_dict(self):
        dims = {"A": ["m", "n"], "B": ["n", "k"]}
        res = check_matrix_shapes("A * B", dims)
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])
        self.assertEqual(res["result_shape"], ["m", "k"])

    def test_check_matrix_shapes_valid_str(self):
        res = check_matrix_shapes("A * B", "A:m:n,B:n:k")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])
        self.assertEqual(res["result_shape"], ["m", "k"])

    def test_check_matrix_shapes_mismatch(self):
        dims = {"A": [2, 3], "B": [4, 5]}
        res = check_matrix_shapes("A * B", dims)
        self.assertEqual(res["status"], "SHAPE_MISMATCH")
        self.assertFalse(res["is_correct"])
        self.assertIn("error_message", res)

    def test_check_matrix_shapes_transpose(self):
        dims = {"A": ["m", "n"], "B": ["k", "n"]}
        res = check_matrix_shapes("A * B.T", dims)
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])
        self.assertEqual(res["result_shape"], ["m", "k"])

    def test_check_matrix_shapes_invalid_operation(self):
        res = check_matrix_shapes("A * Unknown", {"A": [2, 2]})
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("error_message", res)

    def test_check_matrix_shapes_matmult_and_unary_neg(self):
        dims = {"A": ["m", "n"], "B": ["n", "k"]}
        res = check_matrix_shapes("-A @ B", dims)
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])
        self.assertEqual(res["result_shape"], ["m", "k"])

    def test_check_matrix_shapes_ast_rejects_eval_call(self):
        dims = {"A": ["m", "n"]}
        res = check_matrix_shapes("eval('1')", dims)
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("error_message", res)

    def test_check_matrix_shapes_ast_rejects_disallowed_attribute(self):
        dims = {"A": ["m", "n"]}
        res = check_matrix_shapes("A.__class__", dims)
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("error_message", res)

    def test_check_matrix_shapes_ast_rejects_disallowed_operator(self):
        dims = {"A": ["m", "n"], "B": ["n", "k"]}
        res = check_matrix_shapes("A / B", dims)
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("error_message", res)


class TestConvexity(unittest.TestCase):
    def test_check_convexity_strictly_convex(self):
        # f(x, y) = x^2 + y^2 + x*y has positive definite Hessian
        res = check_convexity(r"x^2 + y^2 + x y", "x, y", claimed="strictly_convex")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])
        self.assertEqual(res["actual_property"], "strictly_convex")

    def test_check_convexity_convex_single_var(self):
        # f(x) = x^2 is strictly convex / convex
        res = check_convexity(r"x^2", "x", claimed="strictly_convex")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])

    def test_check_convexity_indefinite(self):
        # f(x, y) = x^2 - y^2 is a saddle
        res = check_convexity(r"x^2 - y^2", "x, y", claimed="indefinite")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])
        self.assertEqual(res["actual_property"], "indefinite")

    def test_check_convexity_mismatch(self):
        # Claiming strictly_convex for saddle point
        res = check_convexity(r"x^2 - y^2", "x, y", claimed="strictly_convex")
        self.assertEqual(res["status"], "INVALID_CONVEXITY_CLAIM")
        self.assertFalse(res["is_correct"])
        self.assertEqual(res["actual_property"], "indefinite")
        self.assertEqual(res["claimed_property"], "strictly_convex")

    def test_check_convexity_invalid_latex(self):
        res = check_convexity(r"\frac{1}", "x")
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("error_message", res)

    def test_check_convexity_strictly_concave(self):
        # f(x, y) = -(x^2 + y^2) has negative definite Hessian
        res = check_convexity(r"-(x^2 + y^2)", "x, y", claimed="strictly_concave")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])
        self.assertEqual(res["actual_property"], "strictly_concave")

    def test_check_convexity_concave_single_var(self):
        # f(x) = -x^2 is strictly concave / concave
        res = check_convexity(r"-x^2", "x", claimed="concave")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])

    def test_check_convexity_normalization(self):
        # Claim with space or hyphen: "strictly concave", "strictly-concave", "strictly-convex"
        res1 = check_convexity(r"-x^2", "x", claimed="strictly concave")
        self.assertEqual(res1["status"], "VALID")
        self.assertTrue(res1["is_correct"])

        res2 = check_convexity(r"-x^2", "x", claimed="strictly-concave")
        self.assertEqual(res2["status"], "VALID")
        self.assertTrue(res2["is_correct"])

        res3 = check_convexity(r"x^2", "x", claimed="strictly-convex")
        self.assertEqual(res3["status"], "VALID")
        self.assertTrue(res3["is_correct"])


class TestNotation(unittest.TestCase):
    def test_check_notation_consistent_raw_latex(self):
        raw_tex = r"""
        \section{Introduction}
        Let $x$ be an integer. We know $x > 0$.
        \section{Methods}
        The variable $x$ is optimized.
        """
        res = check_notation(raw_tex)
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])
        self.assertEqual(len(res["multi_variant_symbols"]), 0)

    def test_check_notation_inconsistent_raw_latex(self):
        raw_tex = r"""
        \section{Introduction}
        We define $P$ as the projection matrix.
        \begin{equation}
        \mathbf{P} v = \lambda v
        \end{equation}
        In addition, $p$ is probability.
        """
        res = check_notation(raw_tex)
        self.assertEqual(res["status"], "NOTATION_INCONSISTENCY")
        self.assertFalse(res["is_correct"])
        self.assertGreater(len(res["multi_variant_symbols"]), 0)
        variants = [item["base_symbol"] for item in res["multi_variant_symbols"]]
        self.assertIn("p", variants)

    def test_check_notation_from_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".tex", delete=False, encoding="utf-8") as f:
            f.write(r"""
            \section{Preliminaries}
            $A$ is a tensor.
            \section{Main}
            $\mathbf{A}$ is bolded here.
            """)
            temp_path = f.name

        try:
            res = check_notation(temp_path)
            self.assertEqual(res["status"], "NOTATION_INCONSISTENCY")
            self.assertFalse(res["is_correct"])
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_check_notation_missing_file(self):
        res = check_notation("non_existent_document_12345.tex")
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("error_message", res)

    def test_check_notation_section_filter(self):
        raw_tex = r"""
        \section{Intro}
        $x$ is used here.
        \section{Appendix}
        $\mathbf{x}$ is used in appendix.
        """
        # If we only scan Intro, there is only $x$, no variant conflict
        res = check_notation(raw_tex, sections=["Intro"])
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])


if __name__ == "__main__":
    unittest.main()
