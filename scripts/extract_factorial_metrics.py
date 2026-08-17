import argparse
import ast
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

try:
    from scripts.extract_episode_metrics import extract_episode, summarize
except ModuleNotFoundError:
    from extract_episode_metrics import extract_episode, summarize


CELL_FACTORS = {
    "dbbench-std-p0c0": ("P0C0", 0, 0),
    "dbbench-std-p0c1": ("P0C1", 0, 1),
    "dbbench-std-p1c0": ("P1C0", 1, 0),
    "dbbench-std-p1c1": ("P1C1", 1, 1),
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


def load_targets(dataset_path: Path) -> List[Dict[str, Any]]:
    targets = []
    for entry in read_jsonl(dataset_path):
        task_type = entry["type"][0]
        target = (
            entry["answer_md5"]
            if task_type in {"INSERT", "DELETE", "UPDATE"}
            else entry["label"]
        )
        targets.append({"task_type": task_type, "target": target})
    return targets


def official_success(answer: Any, task_type: str, target: Any) -> int:
    if task_type in {"INSERT", "DELETE", "UPDATE"}:
        return int(str(answer) == str(target))

    try:
        parsed = ast.literal_eval(str(answer).strip())
        predicted = list(parsed)
    except (ValueError, SyntaxError, TypeError):
        predicted = [answer]

    if len(predicted) == 1 and len(target) == 1:
        try:
            return int(float(predicted[0]) == float(target[0]))
        except (ValueError, TypeError):
            return int(predicted[0] == target[0])

    try:
        return int(set(predicted) == set(target))
    except TypeError:
        return 0


def write_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    if not rows:
        raise ValueError(f"no rows available for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def extract_factorial_dataset(
    run_dirs: Iterable[Path],
    dataset_path: Path,
    expected_per_cell: int = 300,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    run_dirs = list(run_dirs)
    targets = load_targets(dataset_path)
    if len(targets) != expected_per_cell:
        raise ValueError(
            f"dataset contains {len(targets)} tasks, expected {expected_per_cell}"
        )

    episodes = []
    summaries = []
    identities = set()
    task_condition_counts = Counter()
    reference_indices = set(range(expected_per_cell))

    for repetition, run_dir in enumerate(run_dirs, start=1):
        for task_name, (condition, p, c) in CELL_FACTORS.items():
            runs_path = run_dir / "gpt-5" / task_name / "runs.jsonl"
            overall_path = run_dir / "gpt-5" / task_name / "overall.json"
            raw_rows = read_jsonl(runs_path)
            indices = [row.get("index") for row in raw_rows]
            if len(raw_rows) != expected_per_cell or set(indices) != reference_indices:
                raise ValueError(
                    f"{runs_path} does not contain exactly the expected task indices"
                )
            if len(indices) != len(set(indices)):
                raise ValueError(f"{runs_path} contains duplicate task indices")

            cell_rows = []
            for raw in raw_rows:
                index = raw["index"]
                identity = (repetition, condition, index)
                if identity in identities:
                    raise ValueError(f"duplicate episode identity: {identity}")
                identities.add(identity)
                task_condition_counts[(condition, index)] += 1

                row = extract_episode(raw, runs_path)
                target = targets[index]
                raw_answer = (
                    raw.get("output", {}).get("result", {}).get("answer", "")
                    if isinstance(raw.get("output", {}).get("result"), dict)
                    else ""
                )
                query_task = target["task_type"] not in {"INSERT", "DELETE", "UPDATE"}
                row = {
                    "repetition": repetition,
                    "condition": condition,
                    "p": p,
                    "c": c,
                    "task_name": task_name,
                    "task_type": target["task_type"],
                    "official_success": (
                        official_success(raw_answer, target["task_type"], target["target"])
                        if query_task
                        else ""
                    ),
                    "official_success_source": (
                        "saved_query_score" if query_task else "pending_mutation_replay"
                    ),
                    **row,
                }
                episodes.append(row)
                cell_rows.append(row)

            query_rows = [row for row in cell_rows if row["official_success"] != ""]
            official_mean = sum(row["official_success"] for row in query_rows) / len(
                query_rows
            )
            overall = json.loads(overall_path.read_text(encoding="utf-8"))
            recorded_mean = overall.get("custom", {}).get("SELECT_accuracy")
            if recorded_mean is None or abs(official_mean - recorded_mean) > 1e-12:
                raise ValueError(
                    f"{task_name} repetition {repetition} episode scores average to "
                    f"{official_mean}, but overall.json reports SELECT accuracy "
                    f"{recorded_mean}"
                )

            summaries.append(
                {
                    "repetition": repetition,
                    "condition": condition,
                    "p": p,
                    "c": c,
                    "official_select_accuracy": official_mean,
                    **summarize(cell_rows),
                }
            )

    expected_repetitions = len(run_dirs)
    unexpected_counts = {
        identity: count
        for identity, count in task_condition_counts.items()
        if count != expected_repetitions
    }
    if unexpected_counts:
        raise ValueError(
            "task-condition groups do not all contain the expected number of "
            f"repetitions: {unexpected_counts}"
        )

    episodes.sort(key=lambda row: (row["repetition"], row["condition"], row["episode_index"]))
    summaries.sort(key=lambda row: (row["repetition"], row["condition"]))
    return episodes, summaries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", action="append", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--expected-per-cell", type=int, default=300)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()
    if args.expected_per_cell <= 0:
        parser.error("--expected-per-cell must be positive")

    episodes, summaries = extract_factorial_dataset(
        args.run_dir, args.dataset, args.expected_per_cell
    )
    write_csv(episodes, args.output)
    write_csv(summaries, args.summary)
    print(f"Extracted {len(episodes)} episodes across {len(args.run_dir)} repetitions.")
    print(f"Episode metrics: {args.output}")
    print(f"Cell summaries: {args.summary}")


if __name__ == "__main__":
    main()
