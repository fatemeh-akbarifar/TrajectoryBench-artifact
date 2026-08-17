import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import yaml

from scripts.validate_factorial_run import (
    CELL_SPECS,
    OSBENCH_SMOKE_CELL_SPECS,
    validate_run,
)


class FactorialRunValidationTest(unittest.TestCase):
    def make_row(self, index, constraint, model="gpt-5-2025-08-07"):
        return {
            "index": index,
            "error": None,
            "output": {
                "status": "completed",
                "result": {
                    "answer": '["ok"]',
                    "type": "other",
                    "error": "",
                    "output_constraint": constraint,
                    "repair_attempts": 0,
                    "repair_successes": 0,
                    "repair_rejection_reasons": [],
                },
                "history": [
                    {"role": "user", "content": "question", "metadata": {}},
                    {
                        "role": "agent",
                        "content": 'Action: Answer\nFinal Answer: ["ok"]',
                        "metadata": {
                            "response_id": f"response-{index}",
                            "model": model,
                            "finish_reason": "stop",
                            "usage": {
                                "prompt_tokens": 100,
                                "completion_tokens": 20,
                                "total_tokens": 120,
                                "prompt_tokens_details": {"cached_tokens": 10},
                            },
                        },
                    },
                ],
            },
        }

    def build_run(self, root: Path, model="gpt-5-2025-08-07"):
        tasks = {}
        for cell, spec in CELL_SPECS.items():
            tasks[cell] = {
                "parameters": {
                    "max_round": spec["rounds"],
                    "output_constraint": spec["constraint"],
                    "max_repair_attempts": spec["repairs"],
                }
            }
        config = {
            "definition": {
                "agent": {
                    "gpt-5": {
                        "parameters": {
                            "headers": {"Authorization": "<redacted>"},
                            "body": {"model": model},
                        }
                    }
                },
                "task": tasks,
            }
        }
        (root / "config.yaml").write_text(yaml.safe_dump(config))

        for cell, spec in CELL_SPECS.items():
            cell_dir = root / "gpt-5" / cell
            cell_dir.mkdir(parents=True)
            rows = [
                self.make_row(index, spec["constraint"], model=model)
                for index in (0, 1)
            ]
            (cell_dir / "runs.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows)
            )
            (cell_dir / "overall.json").write_text(
                json.dumps(
                    {"total": 2, "custom": {"SELECT_accuracy": 0.5}}
                )
            )

    def validate(self, root: Path):
        return validate_run(
            run_dir=root,
            expected_per_cell=2,
            expected_model="gpt-5-2025-08-07",
            input_rate=Decimal("1.25"),
            cached_input_rate=Decimal("0.125"),
            output_rate=Decimal("10"),
        )

    def test_accepts_complete_matched_factorial_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_run(root)

            report = self.validate(root)

        self.assertTrue(report["valid"])
        self.assertEqual(report["expected_total"], 8)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["cost"]["observed_episodes"], 8)
        self.assertEqual(report["cost"]["input_tokens"], 800)
        self.assertEqual(report["cost"]["cached_input_tokens"], 80)
        self.assertEqual(report["cost"]["output_tokens"], 160)

    def test_rejects_duplicate_indices_and_unexpected_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_run(root, model="moving-model")
            cell = "dbbench-std-p0c0"
            runs_path = root / "gpt-5" / cell / "runs.jsonl"
            duplicate = self.make_row(0, "c0", model="moving-model")
            runs_path.write_text(json.dumps(duplicate) + "\n" + json.dumps(duplicate) + "\n")

            report = self.validate(root)

        self.assertFalse(report["valid"])
        self.assertTrue(any("duplicate episode indices" in e for e in report["errors"]))
        self.assertTrue(any("configured model" in e for e in report["errors"]))
        self.assertTrue(any("unexpected models" in e for e in report["errors"]))

    def test_accepts_a_separate_configured_model_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_run(root)
            config_path = root / "config.yaml"
            config = yaml.safe_load(config_path.read_text())
            config["definition"]["agent"]["gpt-5"]["parameters"]["body"][
                "model"
            ] = "gpt-5"
            config_path.write_text(yaml.safe_dump(config))

            report = validate_run(
                run_dir=root,
                expected_per_cell=2,
                expected_model="gpt-5-2025-08-07",
                expected_configured_model="gpt-5",
                input_rate=Decimal("1.25"),
                cached_input_rate=Decimal("0.125"),
                output_rate=Decimal("10"),
                cell_specs=CELL_SPECS,
            )

        self.assertTrue(report["valid"])

    def test_accepts_a_historical_error_after_successful_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_run(root)
            cell = "dbbench-std-p0c0"
            error_path = root / "gpt-5" / cell / "error.jsonl"
            error_path.write_text(json.dumps({"index": 0, "error": "temporary"}) + "\n")

            report = self.validate(root)

        self.assertTrue(report["valid"])
        self.assertTrue(
            any("historical task-client errors" in warning for warning in report["warnings"])
        )

    def test_rejects_an_unresolved_task_client_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_run(root)
            cell = "dbbench-std-p0c0"
            error_path = root / "gpt-5" / cell / "error.jsonl"
            error_path.write_text(json.dumps({"index": 99, "error": "temporary"}) + "\n")

            report = self.validate(root)

        self.assertFalse(report["valid"])
        self.assertTrue(
            any("unresolved task-client errors" in error for error in report["errors"])
        )

    def test_accepts_complete_osbench_smoke_with_historical_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks = {}
            for cell, spec in OSBENCH_SMOKE_CELL_SPECS.items():
                tasks[cell] = {
                    "parameters": {
                        "round_limit": spec["rounds"],
                        "output_constraint": spec["constraint"],
                        "max_repair_attempts": spec["repairs"],
                    }
                }
            config = {
                "definition": {
                    "agent": {
                        "gpt-5": {
                            "parameters": {
                                "headers": {"Authorization": "<redacted>"},
                                "body": {"model": "gpt-5"},
                            }
                        }
                    },
                    "task": tasks,
                }
            }
            (root / "config.yaml").write_text(yaml.safe_dump(config))
            for cell, spec in OSBENCH_SMOKE_CELL_SPECS.items():
                cell_dir = root / "gpt-5" / cell
                cell_dir.mkdir(parents=True)
                rows = [self.make_row(i, spec["constraint"]) for i in (0, 1)]
                for index, row in enumerate(rows):
                    row["output"]["result"].update(
                        {"result": index == 0, "evaluator_status": "correct" if index == 0 else "incorrect"}
                    )
                (cell_dir / "runs.jsonl").write_text(
                    "".join(json.dumps(row) + "\n" for row in rows)
                )
                (cell_dir / "overall.json").write_text(
                    json.dumps({"total": 2, "custom": {"overall": {"acc": 0.5}}})
                )
            error_path = root / "gpt-5" / "os-smoke-p0c0" / "error.jsonl"
            error_path.write_text(json.dumps({"index": 0, "error": "temporary"}) + "\n")

            report = validate_run(
                run_dir=root,
                expected_per_cell=2,
                expected_model="gpt-5-2025-08-07",
                expected_configured_model="gpt-5",
                input_rate=Decimal("1.25"),
                cached_input_rate=Decimal("0.125"),
                output_rate=Decimal("10"),
                cell_specs=OSBENCH_SMOKE_CELL_SPECS,
                projected_episodes=2880,
            )

        self.assertTrue(report["valid"])
        self.assertEqual(report["expected_total"], 8)
        self.assertEqual(report["cost"]["projected_episodes"], 2880)
        self.assertTrue(any("historical" in item for item in report["warnings"]))


if __name__ == "__main__":
    unittest.main()
