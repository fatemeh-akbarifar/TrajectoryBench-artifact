import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from scripts.extract_factorial_metrics import load_targets
from src.server.tasks.dbbench import build_init_sql, calculate_mutation_answer
from src.server.tasks.dbbench.Interaction import Container
from src.server.tasks.dbbench.action_parser import parse_dbbench_action


MUTATION_TYPES = {"INSERT", "DELETE", "UPDATE"}


def executed_sql(history: Any, strict: bool, max_round: int) -> List[str]:
    if not isinstance(history, list):
        return []
    statements = []
    for message in history:
        if message.get("role") != "agent":
            continue
        parsed = parse_dbbench_action(message.get("content") or "", strict=strict)
        if not parsed.valid:
            continue
        if parsed.action.kind == "answer":
            break
        if len(statements) >= max_round:
            break
        statements.append(parsed.action.sql)
    return statements


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    if not rows:
        raise ValueError("no rescored rows to write")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def load_raw_episode(source_file: str, index: int, cache) -> Dict[str, Any]:
    if source_file not in cache:
        rows = {}
        with Path(source_file).open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"{source_file}:{line_number}: invalid JSON: {exc}"
                    ) from exc
                if row["index"] in rows:
                    raise ValueError(
                        f"{source_file} contains duplicate index {row['index']}"
                    )
                rows[row["index"]] = row
        cache[source_file] = rows
    try:
        return cache[source_file][index]
    except KeyError as exc:
        raise ValueError(f"{source_file} does not contain index {index}") from exc


def rescore_mutations(
    episode_rows: List[Dict[str, str]], dataset_path: Path, container
) -> List[Dict[str, Any]]:
    dataset = []
    with dataset_path.open(encoding="utf-8") as handle:
        dataset = [json.loads(line) for line in handle if line.strip()]
    targets = load_targets(dataset_path)
    raw_cache = {}
    rescored = []

    for row in episode_rows:
        task_type = row["task_type"]
        if task_type not in MUTATION_TYPES:
            if row["official_success"] == "":
                raise ValueError("query episode is missing its official score")
            rescored.append(
                {
                    **row,
                    "mutation_replay_action_count": "",
                    "mutation_replay_answer": "",
                }
            )
            continue

        index = int(row["episode_index"])
        entry = dataset[index]
        raw = load_raw_episode(row["source_file"], index, raw_cache)
        output = raw.get("output") if isinstance(raw.get("output"), dict) else {}
        history = output.get("history")
        max_round = 10 if row["p"] == "1" else 15
        statements = executed_sql(
            history, strict=row["c"] == "1", max_round=max_round
        )
        db = entry["table"]["table_name"]
        init_sql, init_data = build_init_sql(entry)
        try:
            container.execute(init_sql, data=init_data)
            for statement in statements:
                container.execute(statement, db)
            observed = calculate_mutation_answer(container, entry)
        finally:
            container.execute(f"DROP DATABASE IF EXISTS `{db}`")

        target = str(targets[index]["target"])
        rescored.append(
            {
                **row,
                "official_success": int(observed == target),
                "official_success_source": "replayed_mutation_state",
                "mutation_replay_action_count": len(statements),
                "mutation_replay_answer": observed,
            }
        )
        if len(rescored) % 250 == 0:
            print(f"Processed {len(rescored)} of {len(episode_rows)} episodes.", flush=True)

    expected_mutations = sum(
        1 for row in episode_rows if row["task_type"] in MUTATION_TYPES
    )
    replayed = sum(
        row.get("official_success_source") == "replayed_mutation_state"
        for row in rescored
    )
    if replayed != expected_mutations:
        raise ValueError(f"rescored {replayed} mutations, expected {expected_mutations}")
    if any(row["official_success"] == "" for row in rescored):
        raise ValueError("rescored dataset still contains missing official outcomes")
    return rescored


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    container = Container()
    try:
        rows = rescore_mutations(read_csv(args.input), args.dataset, container)
    finally:
        container.delete()
    write_csv(rows, args.output)
    mutation_count = sum(
        row["official_success_source"] == "replayed_mutation_state" for row in rows
    )
    print(f"Wrote {len(rows)} episodes with complete official outcomes.")
    print(f"Replayed mutation episodes: {mutation_count}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
