import argparse
import ast
import csv
import hashlib
import json
import math
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

try:
    from src.server.tasks.dbbench.action_parser import parse_dbbench_action
except ModuleNotFoundError:
    from server.tasks.dbbench.action_parser import parse_dbbench_action


def canonical_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return f"bool:{str(value).lower()}"
    if value is None:
        return "null"
    if isinstance(value, (int, float, Decimal)):
        try:
            number = Decimal(str(value)).normalize()
            return f"number:{format(number, 'f')}"
        except InvalidOperation:
            pass
    return "string:" + str(value)


def canonical_value(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        if len(value) == 1:
            item = next(iter(value))
            try:
                number = Decimal(str(item)).normalize()
                if number.is_finite():
                    return f"singleton-number:{format(number, 'f')}"
            except (InvalidOperation, ValueError, TypeError):
                pass
        members = sorted(set(canonical_value(item) for item in value))
        return "set:" + json.dumps(members, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, dict):
        members = sorted(
            (canonical_value(key), canonical_value(item)) for key, item in value.items()
        )
        return "mapping:" + json.dumps(
            members, ensure_ascii=False, separators=(",", ":")
        )
    return canonical_scalar(value)


def normalize_final_answer(answer: Any, status: str, failure_type: str) -> str:
    raw = str(answer or "").strip()
    if not raw:
        label = failure_type if failure_type and failure_type != "none" else status
        return f"missing:{label or 'unknown'}"
    try:
        return canonical_value(ast.literal_eval(raw))
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return "raw:" + re.sub(r"\s+", " ", raw)


def normalize_sql(sql: str) -> str:
    text = (sql or "").strip()
    output = []
    quote = None
    escaped = False
    pending_space = False
    for char in text:
        if quote is not None:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\" and quote in {"'", '"'}:
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            if pending_space and output:
                output.append(" ")
            pending_space = False
            quote = char
            output.append(char)
        elif char.isspace():
            pending_space = True
        else:
            if pending_space and output:
                output.append(" ")
            pending_space = False
            output.append(char)
    normalized = "".join(output).strip()
    if normalized.endswith(";"):
        normalized = normalized[:-1].rstrip()
    return normalized


def normalized_action_sequence(history: Any, strict: bool) -> List[str]:
    if not isinstance(history, list):
        return []
    actions = []
    for message in history:
        if message.get("role") != "agent":
            continue
        parsed = parse_dbbench_action(message.get("content") or "", strict=strict)
        if parsed.valid and parsed.action.kind == "operation":
            actions.append(normalize_sql(parsed.action.sql))
    return actions


def shannon_entropy(values: Iterable[str]) -> float:
    values = list(values)
    if not values:
        return 0.0
    counts = Counter(values)
    total = len(values)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def modal_proportion(values: Iterable[str]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return max(Counter(values).values()) / len(values)


def load_raw_rows(source_files: Iterable[str]) -> Dict[Tuple[str, int], Dict[str, Any]]:
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
                key = (source, int(row["index"]))
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
        identity = (row["repetition"], row["condition"], row["episode_index"])
        if identity in identities:
            raise ValueError(f"duplicate episode identity: {identity}")
        identities.add(identity)
        lookup_key = (row["source_file"], int(row["episode_index"]))
        if lookup_key not in raw_lookup:
            raise ValueError(f"raw episode is missing for {lookup_key}")
        raw = raw_lookup[lookup_key]
        output = raw.get("output") if isinstance(raw.get("output"), dict) else {}
        result = output.get("result") if isinstance(output.get("result"), dict) else {}
        answer_key = normalize_final_answer(
            result.get("answer"), row["status"], row["failure_type"]
        )
        actions = normalized_action_sequence(
            output.get("history"), strict=row["output_constraint"] == "c1"
        )
        action_json = json.dumps(actions, ensure_ascii=False, separators=(",", ":"))
        enriched.append(
            {
                **row,
                "normalized_final_answer": answer_key,
                "normalized_action_sequence": action_json,
                "action_sequence_sha256": hashlib.sha256(
                    action_json.encode("utf-8")
                ).hexdigest(),
                "normalized_action_count": len(actions),
            }
        )

    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for row in enriched:
        groups.setdefault((row["condition"], row["episode_index"]), []).append(row)

    summaries = []
    for (condition, episode_index), rows in sorted(
        groups.items(), key=lambda item: (item[0][0], int(item[0][1]))
    ):
        if len(rows) != expected_repetitions:
            raise ValueError(
                f"{condition} task {episode_index} has {len(rows)} repetitions, "
                f"expected {expected_repetitions}"
            )
        repetitions = {int(row["repetition"]) for row in rows}
        if repetitions != set(range(1, expected_repetitions + 1)):
            raise ValueError(
                f"{condition} task {episode_index} has repetition set {repetitions}"
            )
        answer_values = [row["normalized_final_answer"] for row in rows]
        action_values = [row["action_sequence_sha256"] for row in rows]
        summaries.append(
            {
                "condition": condition,
                "p": rows[0]["p"],
                "c": rows[0]["c"],
                "episode_index": episode_index,
                "task_type": rows[0]["task_type"],
                "repetitions": len(rows),
                "official_success_rate": sum(
                    int(row["official_success"]) for row in rows
                )
                / len(rows),
                "final_answer_distinct_count": len(set(answer_values)),
                "final_answer_consistency": modal_proportion(answer_values),
                "final_answer_entropy_bits": shannon_entropy(answer_values),
                "action_sequence_distinct_count": len(set(action_values)),
                "action_sequence_consistency": modal_proportion(action_values),
                "action_sequence_entropy_bits": shannon_entropy(action_values),
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
    if args.expected_repetitions <= 0:
        parser.error("--expected-repetitions must be positive")

    episodes, groups = calculate_stability(
        read_csv(args.input), args.expected_repetitions
    )
    write_csv(episodes, args.episode_output)
    write_csv(groups, args.group_output)
    print(f"Normalized {len(episodes)} episodes.")
    print(f"Calculated stability for {len(groups)} task-condition groups.")
    print(f"Episode output: {args.episode_output}")
    print(f"Group output: {args.group_output}")


if __name__ == "__main__":
    main()
