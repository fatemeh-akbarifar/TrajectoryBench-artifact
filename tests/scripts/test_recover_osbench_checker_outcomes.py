import json
import tempfile
import unittest
from pathlib import Path

from scripts.recover_osbench_checker_outcomes import recover_cell


def error_row(index="task-1", exit_code=127):
    output = {
        "index": index,
        "status": "task error",
        "result": {
            "result": False,
            "evaluator_status": "error",
            "evaluator_type": "check",
            "checker_exit_code": exit_code,
            "error": "Checker infrastructure error",
        },
        "history": [{"role": "agent", "content": "Act: finish", "metadata": {}}],
    }
    worker = {"detail": {"output": output}}
    return {
        "index": index,
        "error": "INTERACT_FAILED",
        "info": json.dumps(
            {"detail": "Error: Worker returned error\n" + json.dumps(worker)}
        ),
        "time": {"str": "recorded"},
    }


class RecoverOSBenchCheckerOutcomesTest(unittest.TestCase):
    def test_recovers_command_unavailable_as_incorrect_without_model_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            cell = Path(directory) / "os-std-p0c0"
            cell.mkdir()
            (cell / "runs.jsonl").write_text("", encoding="utf-8")
            (cell / "error.jsonl").write_text(
                json.dumps(error_row()) + "\n", encoding="utf-8"
            )
            recovered = recover_cell(cell, write=True)
            saved = json.loads((cell / "runs.jsonl").read_text())

        self.assertEqual(len(recovered), 1)
        self.assertEqual(saved["index"], "task-1")
        self.assertEqual(saved["output"]["status"], "completed")
        self.assertEqual(saved["output"]["result"]["evaluator_status"], "incorrect")
        self.assertEqual(
            saved["output"]["result"]["evaluator_recovery"],
            "checker_command_unavailable",
        )
        self.assertEqual(saved["output"]["result"]["output_constraint"], "c0")
        self.assertEqual(saved["output"]["result"]["repair_attempts"], 0)

    def test_does_not_recover_unexpected_checker_exit_or_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            cell = Path(directory) / "os-std-p0c0"
            cell.mkdir()
            (cell / "runs.jsonl").write_text(
                json.dumps({"index": "task-1"}) + "\n", encoding="utf-8"
            )
            rows = [error_row("task-1", 127), error_row("task-2", 2)]
            (cell / "error.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            recovered = recover_cell(cell, write=True)

        self.assertEqual(recovered, [])

    def test_is_idempotent_after_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            cell = Path(directory) / "os-std-p0c0"
            cell.mkdir()
            (cell / "runs.jsonl").write_text("", encoding="utf-8")
            (cell / "error.jsonl").write_text(
                json.dumps(error_row()) + "\n", encoding="utf-8"
            )
            recover_cell(cell, write=True)
            recovered_again = recover_cell(cell, write=True)

        self.assertEqual(recovered_again, [])

    def test_completes_metadata_on_an_existing_recovered_record(self):
        with tempfile.TemporaryDirectory() as directory:
            cell = Path(directory) / "os-std-p0c1"
            cell.mkdir()
            recovered = {
                "index": "task-1",
                "output": {
                    "status": "completed",
                    "result": {
                        "result": False,
                        "evaluator_status": "incorrect",
                        "evaluator_recovery": "checker_command_unavailable",
                    },
                },
            }
            (cell / "runs.jsonl").write_text(
                json.dumps(recovered) + "\n", encoding="utf-8"
            )
            (cell / "error.jsonl").write_text("", encoding="utf-8")

            self.assertEqual(recover_cell(cell, write=True), [])
            saved = json.loads((cell / "runs.jsonl").read_text())

        self.assertEqual(saved["output"]["result"]["output_constraint"], "c1")
        self.assertEqual(saved["output"]["result"]["repair_successes"], 0)


if __name__ == "__main__":
    unittest.main()
