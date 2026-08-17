import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


RECOVERABLE_CHECKER_EXIT_CODES = {126, 127}


def constraint_for_cell(cell_dir: Path) -> str:
    name = cell_dir.name
    if name.endswith("c0"):
        return "c0"
    if name.endswith("c1"):
        return "c1"
    raise ValueError(f"cannot infer output constraint from cell name {name!r}")


def complete_recovery_metadata(row: Dict[str, Any], constraint: str) -> bool:
    result = row.get("output", {}).get("result", {})
    if result.get("evaluator_recovery") != "checker_command_unavailable":
        return False
    expected = {
        "output_constraint": constraint,
        "repair_attempts": result.get("repair_attempts", 0),
        "repair_successes": result.get("repair_successes", 0),
        "repair_rejection_reasons": result.get("repair_rejection_reasons", []),
    }
    changed = any(result.get(key) != value for key, value in expected.items())
    result.update(expected)
    return changed


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
    return rows


def nested_task_output(error_row: Dict[str, Any]) -> Dict[str, Any]:
    if error_row.get("error") != "INTERACT_FAILED":
        return {}
    try:
        outer = json.loads(error_row["info"])
        detail = outer["detail"]
        prefix = "Error: Worker returned error\n"
        if not detail.startswith(prefix):
            return {}
        worker = json.loads(detail[len(prefix):])
        return worker["detail"]["output"]
    except (KeyError, TypeError, json.JSONDecodeError):
        return {}


def recover_cell(cell_dir: Path, write: bool = False) -> List[Dict[str, Any]]:
    runs_path = cell_dir / "runs.jsonl"
    error_path = cell_dir / "error.jsonl"
    constraint = constraint_for_cell(cell_dir)
    existing = read_jsonl(runs_path)
    existing_indices = {row.get("index") for row in existing}
    existing_changed = any(
        complete_recovery_metadata(row, constraint) for row in existing
    )
    recovered = []

    for error_row in read_jsonl(error_path):
        task_output = nested_task_output(error_row)
        result = task_output.get("result", {})
        index = task_output.get("index")
        if (
            not index
            or index in existing_indices
            or result.get("evaluator_type") != "check"
            or result.get("evaluator_status") != "error"
            or result.get("checker_exit_code") not in RECOVERABLE_CHECKER_EXIT_CODES
        ):
            continue

        recovered_result = dict(result)
        recovered_result.update(
            {
                "result": False,
                "evaluator_status": "incorrect",
                "error": "",
                "evaluator_recovery": "checker_command_unavailable",
                "original_evaluator_error": result.get("error", ""),
                "output_constraint": constraint,
                "repair_attempts": result.get("repair_attempts", 0),
                "repair_successes": result.get("repair_successes", 0),
                "repair_rejection_reasons": result.get(
                    "repair_rejection_reasons", []
                ),
            }
        )
        recovered_row = {
            "index": index,
            "error": None,
            "info": None,
            "output": {
                **task_output,
                "status": "completed",
                "result": recovered_result,
            },
            "time": error_row.get("time", {}),
        }
        recovered.append(recovered_row)
        existing_indices.add(index)

    if write and (existing_changed or recovered):
        mode = "w" if existing_changed else "a"
        with runs_path.open(mode, encoding="utf-8") as handle:
            if existing_changed:
                for row in existing:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            for row in recovered:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return recovered


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    agent_dir = args.run_dir / "gpt-5"
    recovered = []
    for cell_dir in sorted(path for path in agent_dir.glob("os-std-p*c*") if path.is_dir()):
        for row in recover_cell(cell_dir, write=args.write):
            recovered.append((cell_dir.name, row["index"]))

    mode = "recovered" if args.write else "recoverable"
    print(f"{len(recovered)} {mode} checker outcome(s).")
    for cell, index in recovered:
        print(f"{cell}: {index}")


if __name__ == "__main__":
    main()
