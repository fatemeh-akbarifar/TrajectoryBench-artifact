import math
import unittest

from scripts.analyze_dbbench_factorial import benjamini_hochberg, dispersion_ratio


class FactorialAnalysisUtilityTest(unittest.TestCase):
    def test_benjamini_hochberg_preserves_order_and_monotonicity(self):
        adjusted = benjamini_hochberg([0.01, 0.04, 0.03, math.nan])
        self.assertAlmostEqual(adjusted[0], 0.03)
        self.assertAlmostEqual(adjusted[1], 0.04)
        self.assertAlmostEqual(adjusted[2], 0.04)
        self.assertTrue(math.isnan(adjusted[3]))

    def test_dispersion_ratio(self):
        import pandas as pd

        self.assertAlmostEqual(dispersion_ratio(pd.Series([0, 1, 2, 3])), 1.1111111111111112)
        self.assertTrue(math.isnan(dispersion_ratio(pd.Series([0, 0, 0]))))


if __name__ == "__main__":
    unittest.main()
