import unittest

import pandas as pd

from scripts.build_dbbench_results_report import ordered_conditions, select_effects


class DBBenchResultsReportTest(unittest.TestCase):
    def test_orders_factorial_conditions(self):
        frame = pd.DataFrame(
            {"condition": ["P1C1", "P0C1", "P1C0", "P0C0"], "mean": range(4)}
        )
        ordered = ordered_conditions(frame)
        self.assertEqual(
            ordered["condition"].astype(str).tolist(),
            ["P0C0", "P0C1", "P1C0", "P1C1"],
        )

    def test_selects_and_labels_primary_effects(self):
        effects = pd.DataFrame(
            {
                "outcome": ["official_success"] * 3 + ["total_tokens"],
                "term": ["p:c", "c", "p", "p"],
            }
        )
        selected = select_effects(effects, "official_success")
        self.assertEqual(selected["term"].tolist(), ["p", "c", "p:c"])
        self.assertEqual(
            selected["term_label"].tolist(), ["P1 vs P0", "C1 vs C0", "P × C"]
        )


if __name__ == "__main__":
    unittest.main()
