import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/analyze_cross_environment_rankings.py"
SPEC = importlib.util.spec_from_file_location("rankings", SCRIPT)
rankings = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(rankings)


class CrossEnvironmentRankingTest(unittest.TestCase):
    def test_average_ranks_respect_direction_and_ties(self):
        values = {"P0C0": 4, "P0C1": 2, "P1C0": 2, "P1C1": 1}
        self.assertEqual(
            rankings.average_ranks(values, "lower"),
            {"P1C1": 1, "P0C1": 2.5, "P1C0": 2.5, "P0C0": 4},
        )
        self.assertEqual(rankings.average_ranks(values, "higher")["P0C0"], 1)

    def test_domain_balancing_does_not_overweight_large_domains(self):
        utilities = {
            metric: {condition: 0.0 for condition in rankings.CONDITIONS}
            for metric in rankings.METRICS
        }
        utilities["success"]["P0C0"] = 1.0
        for metric in rankings.DOMAINS["efficiency"]:
            utilities[metric]["P0C1"] = 1.0
        for metric in rankings.DOMAINS["variability"]:
            utilities[metric]["P1C0"] = 1.0
        scores = rankings.aggregate_scheme(
            utilities, rankings.SCHEMES["core_domain_balanced"]
        )
        self.assertAlmostEqual(scores["P0C0"], 1 / 3)
        self.assertAlmostEqual(scores["P0C1"], 1 / 3)
        self.assertAlmostEqual(scores["P1C0"], 1 / 3)

    def test_cross_environment_scope_weights_environments_equally(self):
        def environment(winner):
            metrics = {}
            for metric in rankings.METRICS:
                metrics[metric] = {
                    condition: (1.0 if condition == winner else 0.0)
                    for condition in rankings.CONDITIONS
                }
            return metrics

        rows, summary = rankings.analyze(
            {"dbbench": environment("P0C0"), "osbench": environment("P1C1")}
        )
        success = summary["cross_environment"]["success_only"]
        self.assertEqual(success["ranks"]["P0C0"], 1.5)
        self.assertEqual(success["ranks"]["P1C1"], 1.5)
        self.assertEqual(len([r for r in rows if r["scope"] == "cross_environment"]), 16)

    def test_real_inputs_have_all_conditions_and_schemes(self):
        environments = {
            "dbbench": rankings.load_environment_metrics(
                "dbbench",
                ROOT / "results/dbbench_factorial_analysis/cell_descriptives.csv",
                ROOT / "results/dbbench_factorial_stability_metrics.csv",
            ),
            "osbench": rankings.load_environment_metrics(
                "osbench",
                ROOT / "results/osbench_factorial_analysis/cell_descriptives.csv",
                ROOT / "results/osbench_factorial_stability_metrics.csv",
            ),
        }
        rows, summary = rankings.analyze(environments)
        self.assertEqual(set(summary["cross_environment"]), set(rankings.SCHEMES))
        self.assertEqual(
            len([row for row in rows if row["scope"] == "cross_environment"]), 16
        )


if __name__ == "__main__":
    unittest.main()
