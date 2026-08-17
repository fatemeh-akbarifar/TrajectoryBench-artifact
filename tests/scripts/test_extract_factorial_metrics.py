import json
import tempfile
import unittest
from pathlib import Path

from scripts.extract_factorial_metrics import (
    CELL_FACTORS,
    extract_factorial_dataset,
    official_success,
)


class FactorialMetricsExtractionTest(unittest.TestCase):
    def test_official_success_matches_dbbench_comparison_rules(self):
        self.assertEqual(official_success("['a', 'b']", "other", ["b", "a"]), 1)
        self.assertEqual(official_success("  ['answer']", "other", ["answer"]), 1)
        self.assertEqual(official_success("['2']", "counting", ["2.0"]), 1)
        self.assertEqual(official_success("not a list", "other", ["answer"]), 0)
        self.assertEqual(official_success("hash", "UPDATE", "hash"), 1)

    def test_extracts_balanced_repeated_factorial_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = root / "dataset.jsonl"
            dataset.write_text(
                json.dumps({"type": ["other"], "label": ["ok"]}) + "\n",
                encoding="utf-8",
            )
            run_dirs = []
            for repetition in range(1, 3):
                run_dir = root / f"r{repetition}"
                run_dirs.append(run_dir)
                for task_name in CELL_FACTORS:
                    cell_dir = run_dir / "gpt-5" / task_name
                    cell_dir.mkdir(parents=True)
                    row = {
                        "index": 0,
                        "error": None,
                        "output": {
                            "status": "completed",
                            "result": {
                                "answer": "['ok']",
                                "type": "other",
                                "error": "",
                                "output_constraint": task_name[-2:],
                            },
                            "history": [],
                        },
                        "time": {"str": ""},
                    }
                    (cell_dir / "runs.jsonl").write_text(
                        json.dumps(row) + "\n", encoding="utf-8"
                    )
                    (cell_dir / "overall.json").write_text(
                        json.dumps({"custom": {"SELECT_accuracy": 1.0}}),
                        encoding="utf-8",
                    )

            episodes, summaries = extract_factorial_dataset(
                run_dirs, dataset, expected_per_cell=1
            )

            self.assertEqual(len(episodes), 8)
            self.assertEqual(len(summaries), 8)
            self.assertEqual({row["repetition"] for row in episodes}, {1, 2})
            self.assertEqual(
                {row["condition"] for row in episodes},
                {"P0C0", "P0C1", "P1C0", "P1C1"},
            )
            self.assertTrue(all(row["official_success"] == 1 for row in episodes))

    def test_rejects_episode_score_that_disagrees_with_overall(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = root / "dataset.jsonl"
            dataset.write_text(
                json.dumps({"type": ["other"], "label": ["ok"]}) + "\n",
                encoding="utf-8",
            )
            run_dir = root / "r1"
            for task_name in CELL_FACTORS:
                cell_dir = run_dir / "gpt-5" / task_name
                cell_dir.mkdir(parents=True)
                row = {
                    "index": 0,
                    "error": None,
                    "output": {
                        "status": "completed",
                        "result": {"answer": "['ok']", "type": "other"},
                        "history": [],
                    },
                    "time": {"str": ""},
                }
                (cell_dir / "runs.jsonl").write_text(
                    json.dumps(row) + "\n", encoding="utf-8"
                )
                (cell_dir / "overall.json").write_text(
                        json.dumps({"custom": {"SELECT_accuracy": 0.0}}),
                    encoding="utf-8",
                )

            with self.assertRaisesRegex(ValueError, "SELECT accuracy"):
                extract_factorial_dataset([run_dir], dataset, expected_per_cell=1)


if __name__ == "__main__":
    unittest.main()
