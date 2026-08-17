import argparse
import csv
import json
from pathlib import Path


def safe_get(d, path, default=None):
    current = d
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def count_agent_messages(history):
    if not isinstance(history, list):
        return 0
    return sum(1 for item in history if item.get("role") == "agent")


def count_user_messages(history):
    if not isinstance(history, list):
        return 0
    return sum(1 for item in history if item.get("role") == "user")


def extract_final_agent_message(history):
    if not isinstance(history, list):
        return ""
    for item in reversed(history):
        if item.get("role") == "agent":
            return item.get("content", "")
    return ""


def classify_completed(row):
    """
    Conservative pipeline-validity indicator.
    This is NOT yet the final benchmark success metric.
    """
    top_error = row.get("error")
    status = safe_get(row, ["output", "status"], "")
    return top_error is None and status == "completed"


def extract_row(row, source_file):
    history = safe_get(row, ["output", "history"], [])
    result = safe_get(row, ["output", "result"], {})

    agent_messages = count_agent_messages(history)
    user_messages = count_user_messages(history)
    final_agent_message = extract_final_agent_message(history)

    return {
        "source_file": str(source_file),
        "episode_index": row.get("index"),
        "top_error": row.get("error"),
        "status": safe_get(row, ["output", "status"], ""),
        "completed_indicator": classify_completed(row),
        "result_type": result.get("type") if isinstance(result, dict) else "",
        "result_answer": result.get("answer") if isinstance(result, dict) else "",
        "result_error": result.get("error") if isinstance(result, dict) else "",
        "history_length": len(history) if isinstance(history, list) else 0,
        "agent_messages": agent_messages,
        "user_messages": user_messages,
        "approx_steps": agent_messages,
        "final_agent_message": final_agent_message.replace("\n", " ")[:500],
        "timestamp": safe_get(row, ["time", "str"], ""),
    }


def read_jsonl(path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Skipping invalid JSON in {path}, line {line_number}: {e}")
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to AgentBench runs.jsonl")
    parser.add_argument("--output", default="results/metrics.csv", help="Output CSV path")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = read_jsonl(input_path)
    extracted = [extract_row(row, input_path) for row in rows]

    if not extracted:
        print("No rows extracted.")
        return

    fieldnames = list(extracted[0].keys())

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(extracted)

    completed = sum(1 for r in extracted if r["completed_indicator"])
    total = len(extracted)

    print("Extraction complete.")
    print(f"Input: {input_path}")
    print(f"Output: {output_path}")
    print(f"Episodes: {total}")
    print(f"Completed indicator: {completed}/{total} ({completed / total:.2%})")


if __name__ == "__main__":
    main()