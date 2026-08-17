import unittest

import numpy as np
import pandas as pd

from scripts.analyze_osbench_factorial import analyze


class OSBenchFactorialAnalysisTest(unittest.TestCase):
    def make_frame(self):
        rows = []
        rng = np.random.default_rng(7)
        for task in range(40):
            task_effect = rng.normal(0, 0.5)
            for repetition in range(1, 6):
                for p in (0, 1):
                    for c in (0, 1):
                        steps = int(rng.poisson(4 + p + c)) + 1
                        shell = max(1, steps - 1)
                        probability = 1 / (1 + np.exp(-(-0.4 + 0.3 * p + 0.2 * c + task_effect)))
                        success = int(rng.random() < probability)
                        rows.append(
                            {
                                "repetition": repetition,
                                "condition": f"P{p}C{c}",
                                "p": p,
                                "c": c,
                                "task_identity": f"task-{task}",
                                "task_family": f"family-{task % 4}",
                                "evaluator_type": "check" if task % 5 else "match",
                                "official_success": success,
                                "approx_steps": steps,
                                "shell_actions": shell,
                                "input_tokens": 700 + 40 * steps + int(rng.integers(30)),
                                "output_tokens": 80 + 10 * steps + int(rng.integers(20)),
                                "total_tokens": 800 + 50 * steps + int(rng.integers(30)),
                                "completed_indicator": int(rng.random() > 0.08),
                                "is_format_error": int(rng.random() < 0.08),
                                "is_invalid_action": int(rng.random() < 0.08),
                                "is_task_limit": int(rng.random() < 0.08),
                                "repair_attempted_indicator": int(c and rng.random() < 0.12),
                                "repair_succeeded_indicator": 0,
                            }
                        )
        return pd.DataFrame(rows)

    def test_produces_finite_clustered_factorial_results(self):
        effects, descriptions, diagnostics, cross_validation, comparison = analyze(
            self.make_frame()
        )
        self.assertEqual(set(effects[effects.outcome == "official_success"].term), {"p", "c", "p:c"})
        self.assertTrue(np.isfinite(effects["estimate"]).all())
        self.assertTrue(len(descriptions) > 0)
        self.assertEqual(len(cross_validation["folds"]), 5)
        self.assertTrue(np.isfinite(comparison["likelihood_ratio"]))
        self.assertTrue(all(item.get("converged") is not False for item in diagnostics))


if __name__ == "__main__":
    unittest.main()
