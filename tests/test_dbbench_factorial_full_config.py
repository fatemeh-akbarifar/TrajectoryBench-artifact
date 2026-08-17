import unittest
from pathlib import Path

import yaml

from src.configs import ConfigLoader


ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENTS = ROOT / "configs" / "assignments"


class DBBenchFactorialFullConfigTest(unittest.TestCase):
    def test_base_assignment_contains_the_four_standard_cells(self):
        config = yaml.safe_load(
            (ASSIGNMENTS / "gpt5_dbbench_factorial_full.yaml").read_text()
        )
        expected = [
            "dbbench-std-p0c0",
            "dbbench-std-p0c1",
            "dbbench-std-p1c0",
            "dbbench-std-p1c1",
        ]

        self.assertEqual(config["assignments"][0]["agent"], ["gpt-5"])
        self.assertEqual(config["assignments"][0]["task"], expected)
        self.assertEqual(config["import"], "definition.yaml")
        self.assertEqual(config["concurrency"]["agent"]["gpt-5"], 1)
        for task in expected:
            self.assertEqual(config["concurrency"]["task"][task], 1)

    def test_repetitions_use_stable_distinct_output_directories(self):
        outputs = []
        for repetition in range(1, 6):
            config = yaml.safe_load(
                (
                    ASSIGNMENTS
                    / f"gpt5_dbbench_factorial_full_r{repetition}.yaml"
                ).read_text()
            )
            self.assertEqual(
                config["import"], "gpt5_dbbench_factorial_full.yaml"
            )
            outputs.append(config["output"])

        self.assertEqual(len(set(outputs)), 5)
        self.assertEqual(
            outputs,
            [
                f"outputs/gpt5_dbbench_factorial_full_r{repetition}"
                for repetition in range(1, 6)
            ],
        )
        self.assertFalse(any("TIMESTAMP" in output for output in outputs))

    def test_task_cells_and_tracked_agent_snapshot_are_frozen(self):
        tasks = ConfigLoader().load_from(
            ROOT / "configs" / "tasks" / "dbbench.yaml"
        )
        expected = {
            "dbbench-std-p0c0": (15, "c0", 0),
            "dbbench-std-p0c1": (15, "c1", 1),
            "dbbench-std-p1c0": (10, "c0", 0),
            "dbbench-std-p1c1": (10, "c1", 1),
        }
        for name, values in expected.items():
            parameters = tasks[name]["parameters"]
            self.assertEqual(
                (
                    parameters["max_round"],
                    parameters["output_constraint"],
                    parameters["max_repair_attempts"],
                ),
                values,
            )
            self.assertEqual(parameters["data_file"], "data/dbbench/standard.jsonl")

        agents = yaml.safe_load(
            (ROOT / "configs" / "agents" / "api_agents.yaml").read_text()
        )
        self.assertEqual(
            agents["gpt-5"]["parameters"]["body"]["model"],
            "gpt-5-2025-08-07",
        )


if __name__ == "__main__":
    unittest.main()
