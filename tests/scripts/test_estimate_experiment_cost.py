import csv
import tempfile
import unittest
from pathlib import Path

from scripts.estimate_experiment_cost import estimate_cost, read_episode_rows


class ExperimentCostTest(unittest.TestCase):
    def test_estimates_observed_and_projected_cost(self):
        rows = [
            {"input_tokens": "800", "cached_input_tokens": "200", "output_tokens": "100"},
            {"input_tokens": "1200", "cached_input_tokens": "300", "output_tokens": "200"},
        ]

        result = estimate_cost(
            rows,
            input_rate_per_million="1.25",
            cached_input_rate_per_million="0.125",
            output_rate_per_million="10",
            projected_episodes=6000,
        )

        self.assertEqual(result["observed_episodes"], 2)
        self.assertEqual(result["input_tokens"], 2000)
        self.assertEqual(result["cached_input_tokens"], 500)
        self.assertEqual(result["uncached_input_tokens"], 1500)
        self.assertAlmostEqual(result["observed_total_cost_usd"], 0.0049375)
        self.assertAlmostEqual(result["mean_episode_cost_usd"], 0.00246875)
        self.assertAlmostEqual(result["projected_total_cost_usd"], 14.8125)

    def test_rejects_cached_tokens_above_input_tokens(self):
        rows = [
            {"input_tokens": "10", "cached_input_tokens": "11", "output_tokens": "1"}
        ]

        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            estimate_cost(rows, "1.25", "0.125", "10")

    def test_read_episode_rows_requires_cost_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "episodes.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["input_tokens"])
                writer.writeheader()
                writer.writerow({"input_tokens": 10})

            with self.assertRaisesRegex(ValueError, "missing required columns"):
                read_episode_rows([path])


if __name__ == "__main__":
    unittest.main()
