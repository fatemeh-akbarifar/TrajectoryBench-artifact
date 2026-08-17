import json
import tempfile
import unittest
from pathlib import Path

from scripts.extract_osbench_factorial_metrics import (
    CELL_FACTORS,
    extract_osbench_dataset,
)


class OSBenchFactorialExtractionTest(unittest.TestCase):
    def make_runs(self, root: Path, accuracy: float = 1.0):
        run_dirs = []
        for repetition in range(1, 3):
            run_dir = root / f"r{repetition}"
            run_dirs.append(run_dir)
            for task_name in CELL_FACTORS:
                cell = run_dir / "gpt-5" / task_name
                cell.mkdir(parents=True)
                row = {
                    "index": "std-001-stock-00000",
                    "error": None,
                    "output": {
                        "status": "completed",
                        "result": {
                            "result": True,
                            "evaluator_status": "passed",
                            "evaluator_type": "check",
                            "output_constraint": task_name[-2:],
                            "file": "data/os_interaction/data/1/stock.json",
                            "repair_attempts": 0,
                            "repair_successes": 0,
                        },
                        "history": [
                            {"role": "agent", "content": "Act: finish", "metadata": {}}
                        ],
                    },
                    "time": {"str": ""},
                }
                (cell / "runs.jsonl").write_text(json.dumps(row) + "\n")
                (cell / "overall.json").write_text(
                    json.dumps({"custom": {"overall": {"acc": accuracy}}})
                )
        return run_dirs

    def test_extracts_balanced_saved_evaluator_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            episodes, summaries = extract_osbench_dataset(
                self.make_runs(Path(tmp)), expected_per_cell=1
            )
        self.assertEqual(len(episodes), 8)
        self.assertEqual(len(summaries), 8)
        self.assertTrue(all(row["official_success"] == 1 for row in episodes))
        self.assertEqual({row["task_family"] for row in episodes}, {"stock"})

    def test_rejects_accuracy_disagreement(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dirs = self.make_runs(Path(tmp), accuracy=0.0)
            with self.assertRaisesRegex(ValueError, "does not match"):
                extract_osbench_dataset(run_dirs, expected_per_cell=1)

    def test_recovers_task_invariant_evaluator_type_for_unevaluated_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dirs = self.make_runs(Path(tmp))
            path = run_dirs[0] / "gpt-5" / "os-std-p0c0" / "runs.jsonl"
            row = json.loads(path.read_text())
            row["output"]["result"].pop("evaluator_type")
            path.write_text(json.dumps(row) + "\n")
            episodes, _ = extract_osbench_dataset(run_dirs, expected_per_cell=1)
        recovered = [
            row
            for row in episodes
            if row["repetition"] == 1 and row["condition"] == "P0C0"
        ][0]
        self.assertEqual(recovered["evaluator_type"], "check")


if __name__ == "__main__":
    unittest.main()
