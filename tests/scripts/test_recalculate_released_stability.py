import csv
import tempfile
import unittest
from pathlib import Path

from scripts.recalculate_released_stability import summarize


class RecalculateReleasedStabilityTest(unittest.TestCase):
    def test_dbbench_summary_uses_hash_frequencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "episodes.csv"
            output = root / "summary.csv"
            fields = (
                "condition",
                "p",
                "c",
                "episode_index",
                "task_type",
                "repetition",
                "official_success",
                "final_outcome_sha256",
                "action_sequence_sha256",
            )
            with source.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for repetition, final_hash, action_hash in (
                    ("1", "a", "x"),
                    ("2", "a", "y"),
                    ("3", "b", "z"),
                ):
                    writer.writerow(
                        {
                            "condition": "P0C0",
                            "p": "0",
                            "c": "0",
                            "episode_index": "1",
                            "task_type": "query",
                            "repetition": repetition,
                            "official_success": "1",
                            "final_outcome_sha256": final_hash,
                            "action_sequence_sha256": action_hash,
                        }
                    )

            summarize(source, output, "dbbench")
            with output.open(newline="", encoding="utf-8") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row["repetitions"], "3")
            self.assertEqual(row["final_answer_distinct_count"], "2")
            self.assertAlmostEqual(float(row["final_answer_consistency"]), 2 / 3)
            self.assertEqual(row["action_sequence_distinct_count"], "3")


if __name__ == "__main__":
    unittest.main()
