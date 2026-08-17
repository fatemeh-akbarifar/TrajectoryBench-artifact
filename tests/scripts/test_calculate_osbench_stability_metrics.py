import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.calculate_osbench_stability_metrics import calculate_stability


class OSBenchStabilityTest(unittest.TestCase):
    def test_calculates_five_run_action_consistency(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = []
            for repetition in range(1, 6):
                source = root / f"r{repetition}.jsonl"
                source.write_text(
                    json.dumps(
                        {
                            "index": "task-0",
                            "output": {
                                "result": {"result": True, "evaluator_status": "passed"},
                                "history": [
                                    {
                                        "role": "agent",
                                        "content": "Act: bash\n```bash\necho ok\n```",
                                    },
                                    {"role": "agent", "content": "Act: finish"},
                                ],
                            },
                        }
                    )
                    + "\n"
                )
                rows.append(
                    {
                        "repetition": str(repetition),
                        "condition": "P0C0",
                        "p": "0",
                        "c": "0",
                        "task_identity": "task-0",
                        "task_family": "stock",
                        "evaluator_type": "check",
                        "official_success": "1",
                        "source_file": str(source),
                        "output_constraint": "c0",
                        "final_agent_message": "Act: finish",
                    }
                )
            episodes, groups = calculate_stability(rows, expected_repetitions=5)
        self.assertEqual(len(episodes), 5)
        self.assertEqual(groups[0]["action_sequence_consistency"], 1.0)
        self.assertEqual(groups[0]["action_sequence_distinct_count"], 1)


if __name__ == "__main__":
    unittest.main()
