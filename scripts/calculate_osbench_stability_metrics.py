import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

try:
    from src.server.tasks.os_interaction.action_parser import parse_osbench_action
except ModuleNotFoundError:
    from server.tasks.os_interaction.action_parser import parse_osbench_action


def modal_proportion(values: Iterable[str]) -> float:
    values = list(values)
    return max(Counter(values).values()) / len(values) if values else 0.0


def shannon_entropy(values: Iterable[str]) -> float:
    values = list(values)
    if not values:
        return 0.0
    counts = Counter(values)
    return -sum((count / len(values)) * math.log2(count / len(values)) for count in counts.values())


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def normalized_trajectory(history: Any, strict: bool) -> List[Dict[str, str]]:
    if not isinstance(history, list):
        return []
    actions = []
    for item in history:
        if item.get("role") != "agent":
            continue
        parsed = parse_osbench_action(item.get("content") or "", strict=strict)
        if not parsed.valid:
            continue
        actions.append(
            {
                "action": str(parsed.action),
                "content": normalize_text(parsed.content),
            }
        )
    return actions


def final_agent_message(history: Any) -> str:
    if not isinstance(history, list):
        return ""
    for item in reversed(history):
        if item.get("role") == "agent":
            return normalize_text(item.get("content"))
    return ""


def load_raw_rows(source_files: Iterable[str]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    lookup = {}
    for source in sorted(set(source_files)):
        path = Path(source)
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
                key = (source, str(row["index"]))
                if key in lookup:
                    raise ValueError(f"duplicate raw episode lookup key: {key}")
                lookup[key] = row
    return lookup


def calculate_stability(
    episode_rows: List[Dict[str, str]], expected_repetitions: int = 5
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    raw_lookup = load_raw_rows(row["source_file"] for row in episode_rows)
    enriched = []
    identities = set()
    for row in episode_rows:
        identity = (int(row["repetition"]), row["condition"], row["task_identity"])
        if identity in identities:
            raise ValueError(f"duplicate episode identity: {identity}")
        identities.add(identity)
        raw = raw_lookup[(row["source_file"], row["task_identity"])]
        output = raw.get("output") if isinstance(raw.get("output"), dict) else {}
        result = output.get("result") if isinstance(output.get("result"), dict) else {}
        history = output.get("history")
        final_key = json.dumps(
            {
                "success": bool(result.get("result")),
                "evaluator_status": str(result.get("evaluator_status") or ""),
                "terminal_action": final_agent_message(history),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        trajectory = normalized_trajectory(history, row["output_constraint"] == "c1")
        trajectory_json = json.dumps(trajectory, ensure_ascii=False, separators=(",", ":"))
        enriched.append(
            {
                **row,
                "normalized_final_outcome": final_key,
                "normalized_action_sequence": trajectory_json,
                "action_sequence_sha256": hashlib.sha256(trajectory_json.encode()).hexdigest(),
                "normalized_action_count": len(trajectory),
            }
        )

    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for row in enriched:
        groups.setdefault((row["condition"], row["task_identity"]), []).append(row)

    summaries = []
    expected_set = set(range(1, expected_repetitions + 1))
    for (condition, task_identity), rows in sorted(groups.items()):
        repetitions = {int(row["repetition"]) for row in rows}
        if len(rows) != expected_repetitions or repetitions != expected_set:
            raise ValueError(f"{condition} task {task_identity} has repetition set {repetitions}")
        outcomes = [row["normalized_final_outcome"] for row in rows]
        trajectories = [row["action_sequence_sha256"] for row in rows]
        summaries.append(
            {
                "condition": condition,
                "p": rows[0]["p"],
                "c": rows[0]["c"],
                "task_identity": task_identity,
                "task_family": rows[0]["task_family"],
                "evaluator_type": rows[0]["evaluator_type"],
                "repetitions": len(rows),
                "official_success_rate": sum(int(row["official_success"]) for row in rows) / len(rows),
                "final_outcome_distinct_count": len(set(outcomes)),
                "final_outcome_consistency": modal_proportion(outcomes),
                "final_outcome_entropy_bits": shannon_entropy(outcomes),
                "action_sequence_distinct_count": len(set(trajectories)),
                "action_sequence_consistency": modal_proportion(trajectories),
                "action_sequence_entropy_bits": shannon_entropy(trajectories),
            }
        )
    return enriched, summaries


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    if not rows:
        raise ValueError(f"no rows available for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--expected-repetitions", type=int, default=5)
    parser.add_argument("--episode-output", required=True, type=Path)
    parser.add_argument("--group-output", required=True, type=Path)
    args = parser.parse_args()
    episodes, groups = calculate_stability(read_csv(args.input), args.expected_repetitions)
    write_csv(episodes, args.episode_output)
    write_csv(groups, args.group_output)
    print(f"Normalized {len(episodes)} OSBench episodes.")
    print(f"Calculated stability for {len(groups)} task-condition groups.")


if __name__ == "__main__":
    main()
