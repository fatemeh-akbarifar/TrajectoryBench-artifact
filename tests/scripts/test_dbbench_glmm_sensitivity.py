import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESULT = ROOT / "thesis_protocol/dbbench_success_glmm_sensitivity.json"
SCRIPT = ROOT / "scripts/fit_dbbench_success_glmm.R"
DOCKERFILE = ROOT / "analysis/r-glmm/Dockerfile"


class DBBenchGLMMSensitivityTest(unittest.TestCase):
    def setUp(self):
        self.result = json.loads(RESULT.read_text(encoding="utf-8"))

    def test_uses_audited_dataset_and_planned_model(self):
        dataset = self.result["dataset"]
        self.assertEqual(dataset["observations"], 6000)
        self.assertEqual(dataset["tasks"], 300)
        self.assertEqual(
            dataset["sha256"],
            "a3c2f12b014ae0b3e90bde1a57ec30635035217da13f0047e1d33f013a0843f8",
        )
        self.assertEqual(
            dataset["formula"], "official_success ~ p * c + (1 | episode_index)"
        )
        self.assertIn("sensitivity", self.result["analysis_role"])
        self.assertIn("primary", self.result["analysis_role"])

    def test_records_complete_diagnostics(self):
        diagnostic = self.result["diagnostics"]
        self.assertTrue(diagnostic["converged"])
        self.assertEqual(diagnostic["optimizer_code"], 0)
        self.assertEqual(diagnostic["convergence_messages"], [])
        self.assertEqual(diagnostic["warnings"], [])
        self.assertFalse(diagnostic["singular_fit"])
        self.assertGreater(diagnostic["random_intercept_variance"], 0)
        self.assertLess(diagnostic["max_absolute_gradient"], 0.001)
        self.assertGreater(diagnostic["hessian_min_eigenvalue"], 0)

    def test_records_all_effects_and_gee_comparison(self):
        expected = {"p", "c", "p:c"}
        effects = {row["term"]: row for row in self.result["fixed_effects"]}
        comparisons = {
            row["term"]: row
            for row in self.result["comparison_with_primary_gee"]
        }
        self.assertEqual(set(effects), expected)
        self.assertEqual(set(comparisons), expected)
        for term in expected:
            row = effects[term]
            self.assertLess(row["odds_ratio_ci_lower"], row["odds_ratio"])
            self.assertGreater(row["odds_ratio_ci_upper"], row["odds_ratio"])
            self.assertGreaterEqual(row["p_value"], 0)
            self.assertLessEqual(row["p_value"], 1)
            self.assertTrue(comparisons[term]["same_direction"])

    def test_reproduction_environment_is_pinned(self):
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("r-base@sha256:", dockerfile)
        self.assertIn('optimizer = "bobyqa"', script)
        self.assertIn("nAGQ = 10", script)
        self.assertIn("isSingular(model, tol = 1e-4)", script)


if __name__ == "__main__":
    unittest.main()
