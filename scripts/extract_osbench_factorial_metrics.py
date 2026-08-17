import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

try:
    from scripts.extract_episode_metrics import extract_episode
except ModuleNotFoundError:
    from extract_episode_metrics import extract_episode


CELL_FACTORS = {
    "os-std-p0c0": ("P0C0", 0, 0),
    "os-std-p0c1": ("P0C1", 0, 1),
    "os-std-p1c0": ("P1C0", 1, 0),
    "os-std-p1c1": ("P1C1", 1, 1),
}


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
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


def write_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    if not rows:
        raise ValueError(f"no rows available for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def task_family(result: Dict[str, Any], identity: str) -> str:
    file_value = result.get("file")
    if file_value:
        return Path(str(file_value)).stem
    parts = identity.split("-")
    return "-".join(parts[2:-1]) if len(parts) > 3 else identity


def shell_action_count(history: Any) -> int:
    if not isinstance(history, list):
        return 0
    return sum(
        1
        for item in history
        if item.get("role") == "agent"
        and "act: bash" in str(item.get("content") or "").lower()
    )


def extract_osbench_dataset(
    run_dirs: Iterable[Path], expected_per_cell: int = 144
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    run_dirs = list(run_dirs)
    if not run_dirs:
        raise ValueError("at least one run directory is required")

    episodes: List[Dict[str, Any]] = []
    summaries: List[Dict[str, Any]] = []
    identities = set()
    task_condition_counts = Counter()
    reference_indices = None
    evaluator_types: Dict[str, str] = {}

    # Task-limit and agent-validation records may end before the evaluator runs.
    # Recover only the task-invariant evaluator type from another repetition/cell.
    for run_dir in run_dirs:
        for task_name in CELL_FACTORS:
            for raw in read_jsonl(run_dir / "gpt-5" / task_name / "runs.jsonl"):
                output = raw.get("output") if isinstance(raw.get("output"), dict) else {}
                result = output.get("result") if isinstance(output.get("result"), dict) else {}
                evaluator_type = str(result.get("evaluator_type") or "")
                if not evaluator_type:
                    continue
                index = str(raw["index"])
                previous = evaluator_types.setdefault(index, evaluator_type)
                if previous != evaluator_type:
                    raise ValueError(f"task {index} has inconsistent evaluator types")

    for repetition, run_dir in enumerate(run_dirs, start=1):
        for task_name, (condition, p, c) in CELL_FACTORS.items():
            cell_dir = run_dir / "gpt-5" / task_name
            runs_path = cell_dir / "runs.jsonl"
            overall_path = cell_dir / "overall.json"
            raw_rows = read_jsonl(runs_path)
            indices = [str(row.get("index")) for row in raw_rows]
            index_set = set(indices)
            if len(raw_rows) != expected_per_cell or len(index_set) != expected_per_cell:
                raise ValueError(
                    f"{runs_path} does not contain {expected_per_cell} unique identities"
                )
            if reference_indices is None:
                reference_indices = index_set
            elif index_set != reference_indices:
                raise ValueError(f"{runs_path} task identities differ from the reference cell")

            cell_rows = []
            for raw in raw_rows:
                index = str(raw["index"])
                identity = (repetition, condition, index)
                if identity in identities:
                    raise ValueError(f"duplicate episode identity: {identity}")
                identities.add(identity)
                task_condition_counts[(condition, index)] += 1

                output = raw.get("output") if isinstance(raw.get("output"), dict) else {}
                result = output.get("result") if isinstance(output.get("result"), dict) else {}
                success = result.get("result")
                if not isinstance(success, bool):
                    raise ValueError(f"{runs_path} identity {index} lacks a boolean evaluator result")
                evaluator_type = str(result.get("evaluator_type") or evaluator_types.get(index, ""))
                if evaluator_type not in {"check", "match"}:
                    raise ValueError(f"{runs_path} identity {index} has invalid evaluator type")

                base = extract_episode(raw, runs_path)
                history = output.get("history")
                row = {
                    "repetition": repetition,
                    "condition": condition,
                    "p": p,
                    "c": c,
                    "task_name": task_name,
                    "task_identity": index,
                    "task_family": task_family(result, index),
                    "evaluator_type": evaluator_type,
                    "official_success": int(success),
                    "official_success_source": "saved_osbench_evaluator_result",
                    "shell_actions": shell_action_count(history),
                    **base,
                }
                episodes.append(row)
                cell_rows.append(row)

            overall = json.loads(overall_path.read_text(encoding="utf-8"))
            recorded_accuracy = overall.get("custom", {}).get("overall", {}).get("acc")
            observed_accuracy = sum(row["official_success"] for row in cell_rows) / len(cell_rows)
            if recorded_accuracy is None or abs(observed_accuracy - float(recorded_accuracy)) > 1e-12:
                raise ValueError(
                    f"{task_name} repetition {repetition} episode accuracy {observed_accuracy} "
                    f"does not match overall.json accuracy {recorded_accuracy}"
                )
            summaries.append(
                {
                    "repetition": repetition,
                    "condition": condition,
                    "p": p,
                    "c": c,
                    "episodes": len(cell_rows),
                    "official_accuracy": observed_accuracy,
                    "completed_rate": sum(row["completed_indicator"] for row in cell_rows) / len(cell_rows),
                    "avg_steps": sum(row["approx_steps"] for row in cell_rows) / len(cell_rows),
                    "avg_shell_actions": sum(row["shell_actions"] for row in cell_rows) / len(cell_rows),
                    "avg_total_tokens": sum(row["total_tokens"] for row in cell_rows) / len(cell_rows),
                    "repair_attempt_rate": sum(row["repair_attempted_indicator"] for row in cell_rows) / len(cell_rows),
                }
            )

    expected_repetitions = len(run_dirs)
    unexpected = {
        key: count
        for key, count in task_condition_counts.items()
        if count != expected_repetitions
    }
    if unexpected:
        raise ValueError(f"unbalanced task-condition repetition counts: {unexpected}")

    episodes.sort(key=lambda row: (row["repetition"], row["condition"], row["task_identity"]))
    summaries.sort(key=lambda row: (row["repetition"], row["condition"]))
    return episodes, summaries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", action="append", required=True, type=Path)
    parser.add_argument("--expected-per-cell", type=int, default=144)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()
    if args.expected_per_cell <= 0:
        parser.error("--expected-per-cell must be positive")
    episodes, summaries = extract_osbench_dataset(args.run_dir, args.expected_per_cell)
    write_csv(episodes, args.output)
    write_csv(summaries, args.summary)
    print(f"Extracted {len(episodes)} OSBench episodes across {len(args.run_dir)} repetitions.")
    print(f"Episode metrics: {args.output}")
    print(f"Cell summaries: {args.summary}")


if __name__ == "__main__":
    main()
