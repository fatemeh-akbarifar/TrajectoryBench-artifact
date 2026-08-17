import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


ERROR_PATTERNS = {
    "sql_error": [
        "syntax error",
        "mysql",
        "42000",
        "does not exist",
        "unknown column",
        "unknown table",
    ],
    "format_error": [
        "cannot match any pattern",
        "invalid format",
        "format",
        "parse",
        "parser",
    ],
    "invalid_action": [
        "invalid action",
        "action failed",
        "not executable",
    ],
    "context_limit": [
        "context limit",
        "maximum context",
        "context length",
        "token limit",
    ],
    "task_limit": [
        "task limit reached",
        "max turns",
        "maximum turns",
    ],
}


def safe_get(d: Dict[str, Any], path: List[str], default=None):
    cur = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def normalize_text(x: Any) -> str:
    if x is None:
        return ""
    return str(x).replace("\n", " ").strip()


def get_history(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    history = safe_get(row, ["output", "history"], [])
    return history if isinstance(history, list) else []


def count_role(history: List[Dict[str, Any]], role: str) -> int:
    return sum(1 for h in history if h.get("role") == role)


def final_agent_message(history: List[Dict[str, Any]]) -> str:
    for h in reversed(history):
        if h.get("role") == "agent":
            return normalize_text(h.get("content"))
    return ""


def all_text(row: Dict[str, Any]) -> str:
    parts = [
        normalize_text(row.get("error")),
        normalize_text(safe_get(row, ["output", "status"])),
        normalize_text(safe_get(row, ["output", "result", "answer"])),
        normalize_text(safe_get(row, ["output", "result", "error"])),
    ]

    for h in get_history(row):
        parts.append(normalize_text(h.get("content")))

    return " ".join(parts).lower()


def contains_any(text: str, patterns: List[str]) -> bool:
    return any(p.lower() in text for p in patterns)


def classify_failure_type(row: Dict[str, Any]) -> str:
    status = normalize_text(safe_get(row, ["output", "status"])).lower()


    if status == "completed" and row.get("error") is None:
        return "none"

    text = all_text(row)

    if "task limit reached" in status:
        return "task_limit"

    for label, patterns in ERROR_PATTERNS.items():
        if label == "sql_error":
            continue
        if contains_any(text, patterns):
            return label

    if contains_any(text, ERROR_PATTERNS["sql_error"]):
        return "sql_error"

    if row.get("error"):
        return "top_level_error"

    if status and status != "completed":
        return status.replace(" ", "_")

    return "unknown"


def is_completed(row: Dict[str, Any]) -> bool:
    return row.get("error") is None and safe_get(row, ["output", "status"]) == "completed"


def count_sql_operations(history: List[Dict[str, Any]]) -> int:
    count = 0
    for h in history:
        if h.get("role") == "agent":
            content = normalize_text(h.get("content")).lower()
            if "action: operation" in content or "```sql" in content:
                count += 1
    return count


def count_final_answers(history: List[Dict[str, Any]]) -> int:
    count = 0
    for h in history:
        if h.get("role") == "agent":
            content = normalize_text(h.get("content")).lower()
            if "action: answer" in content or "final answer:" in content:
                count += 1
    return count


def count_sql_errors(history: List[Dict[str, Any]]) -> int:
    count = 0
    for h in history:
        if h.get("role") == "user":
            content = normalize_text(h.get("content")).lower()
            if any(x in content for x in ["42000", "syntax error", "does not exist", "unknown column", "unknown table"]):
                count += 1
    return count


def agent_response_metadata(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    metadata = []
    for item in history:
        if item.get("role") != "agent":
            continue
        value = item.get("metadata")
        if isinstance(value, dict) and value:
            metadata.append(value)
    return metadata


def sum_usage(metadata: List[Dict[str, Any]], key: str) -> int:
    total = 0
    for item in metadata:
        usage = item.get("usage")
        if isinstance(usage, dict):
            value = usage.get(key)
            if isinstance(value, (int, float)):
                total += int(value)
    return total


def sum_reasoning_tokens(metadata: List[Dict[str, Any]]) -> int:
    total = 0
    for item in metadata:
        usage = item.get("usage")
        if not isinstance(usage, dict):
            continue
        details = usage.get("completion_tokens_details")
        if not isinstance(details, dict):
            continue
        value = details.get("reasoning_tokens")
        if isinstance(value, (int, float)):
            total += int(value)
    return total


def sum_cached_input_tokens(metadata: List[Dict[str, Any]]) -> int:
    total = 0
    for item in metadata:
        usage = item.get("usage")
        if not isinstance(usage, dict):
            continue
        details = usage.get("prompt_tokens_details")
        if not isinstance(details, dict):
            continue
        value = details.get("cached_tokens")
        if isinstance(value, (int, float)):
            total += int(value)
    return total


def distinct_metadata_values(metadata: List[Dict[str, Any]], key: str) -> str:
    values = {
        normalize_text(item.get(key))
        for item in metadata
        if normalize_text(item.get(key))
    }
    return "|".join(sorted(values))


def extract_episode(row: Dict[str, Any], source_file: Path) -> Dict[str, Any]:
    history = get_history(row)
    response_metadata = agent_response_metadata(history)
    result = safe_get(row, ["output", "result"], {})
    result = result if isinstance(result, dict) else {}

    agent_messages = count_role(history, "agent")
    user_messages = count_role(history, "user")
    sql_operations = count_sql_operations(history)
    sql_errors = count_sql_errors(history)

    status = normalize_text(safe_get(row, ["output", "status"]))
    completed = is_completed(row)
    failure_type = classify_failure_type(row)
    repair_attempts = int(result.get("repair_attempts") or 0)
    repair_successes = int(result.get("repair_successes") or 0)
    rejection_reasons = result.get("repair_rejection_reasons")
    if not isinstance(rejection_reasons, list):
        rejection_reasons = []

    return {
        "source_file": str(source_file),
        "episode_index": row.get("index"),
        "timestamp": normalize_text(safe_get(row, ["time", "str"])),
        "status": status,
        "completed_indicator": int(completed),
        "failure_type": failure_type,
        "top_error_present": int(row.get("error") is not None),
        "result_type": normalize_text(result.get("type")),
        "result_answer": normalize_text(result.get("answer"))[:300],
        "result_error": normalize_text(result.get("error"))[:300],
        "output_constraint": normalize_text(result.get("output_constraint")),
        "repair_attempts": repair_attempts,
        "repair_successes": repair_successes,
        "repair_attempted_indicator": int(repair_attempts > 0),
        "repair_succeeded_indicator": int(repair_successes > 0),
        "repair_rejection_reasons": "|".join(
            normalize_text(reason) for reason in rejection_reasons
        ),
        "history_length": len(history),
        "agent_messages": agent_messages,
        "user_messages": user_messages,
        "approx_steps": agent_messages,
        "sql_operations": sql_operations,
        "tool_calls_proxy": sql_operations,
        "final_answer_count": count_final_answers(history),
        "sql_error_count": sql_errors,
        "has_sql_error": int(sql_errors > 0),
        "input_tokens": sum_usage(response_metadata, "prompt_tokens"),
        "cached_input_tokens": sum_cached_input_tokens(response_metadata),
        "output_tokens": sum_usage(response_metadata, "completion_tokens"),
        "reasoning_tokens": sum_reasoning_tokens(response_metadata),
        "total_tokens": sum_usage(response_metadata, "total_tokens"),
        "provider_models": distinct_metadata_values(response_metadata, "model"),
        "finish_reasons": distinct_metadata_values(response_metadata, "finish_reason"),
        "provider_response_ids": distinct_metadata_values(response_metadata, "response_id"),
        "is_task_limit": int(failure_type == "task_limit"),
        "is_context_limit": int(failure_type == "context_limit"),
        "is_format_error": int(failure_type == "format_error"),
        "is_invalid_action": int(failure_type == "invalid_action"),
        "final_agent_message": final_agent_message(history)[:500],
    }


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Skipping invalid JSON: {path}:{line_no}: {e}")
    return rows


def write_csv(rows: List[Dict[str, Any]], output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        print("No rows to write.")
        return

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {}

    def mean(col):
        vals = [float(r[col]) for r in rows if r.get(col) not in ["", None]]
        return sum(vals) / len(vals) if vals else 0.0

    repair_attempted_episodes = sum(
        int(row.get("repair_attempted_indicator") or 0) for row in rows
    )
    repaired_episodes = sum(
        int(row.get("repair_succeeded_indicator") or 0) for row in rows
    )

    return {
        "episodes": n,
        "completed_rate": mean("completed_indicator"),
        "avg_steps": mean("approx_steps"),
        "avg_history_length": mean("history_length"),
        "avg_sql_operations": mean("sql_operations"),
        "avg_input_tokens": mean("input_tokens"),
        "avg_cached_input_tokens": mean("cached_input_tokens"),
        "avg_output_tokens": mean("output_tokens"),
        "avg_reasoning_tokens": mean("reasoning_tokens"),
        "avg_total_tokens": mean("total_tokens"),
        "avg_repair_attempts": mean("repair_attempts"),
        "repair_attempt_rate": mean("repair_attempted_indicator"),
        "repair_success_rate": (
            repaired_episodes / repair_attempted_episodes
            if repair_attempted_episodes
            else 0.0
        ),
        "sql_error_rate": mean("has_sql_error"),
        "task_limit_rate": mean("is_task_limit"),
        "format_error_rate": mean("is_format_error"),
        "invalid_action_rate": mean("is_invalid_action"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to runs.jsonl")
    parser.add_argument("--output", default="results/episode_metrics.csv")
    parser.add_argument("--summary", default="results/summary_metrics.csv")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    summary_path = Path(args.summary)

    raw_rows = read_jsonl(input_path)
    rows = [extract_episode(row, input_path) for row in raw_rows]
    write_csv(rows, output_path)

    summary = summarize(rows)
    write_csv([summary], summary_path)

    print("Extraction complete.")
    print(f"Input: {input_path}")
    print(f"Episodes: {len(rows)}")
    print(f"Episode metrics: {output_path}")
    print(f"Summary metrics: {summary_path}")
    print(summary)


if __name__ == "__main__":
    main()
