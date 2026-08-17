#!/usr/bin/env python3
"""Recalculate recurrence summaries from sanitized release hashes."""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path


def modal_proportion(values: list[str]) -> float:
    counts = Counter(values)
    return max(counts.values()) / len(values)


def entropy_bits(values: list[str]) -> float:
    counts = Counter(values)
    total = len(values)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def summarize(input_path: Path, output_path: Path, environment: str) -> None:
    with input_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("input contains no data rows")

    if environment == "dbbench":
        identity_fields = ("condition", "p", "c", "episode_index", "task_type")
        final_prefix = "final_answer"
    else:
        identity_fields = (
            "condition",
            "p",
            "c",
            "task_identity",
            "task_family",
            "evaluator_type",
        )
        final_prefix = "final_outcome"

    required = set(identity_fields) | {
        "repetition",
        "official_success",
        "final_outcome_sha256",
        "action_sequence_sha256",
    }
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"input is missing columns: {sorted(missing)}")

    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[field] for field in identity_fields)].append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(identity_fields) + [
        "repetitions",
        "official_success_rate",
        f"{final_prefix}_distinct_count",
        f"{final_prefix}_consistency",
        f"{final_prefix}_entropy_bits",
        "action_sequence_distinct_count",
        "action_sequence_consistency",
        "action_sequence_entropy_bits",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        if environment == "dbbench":
            ordered_keys = sorted(groups, key=lambda key: (key[0], int(key[3])))
        else:
            ordered_keys = sorted(groups)
        for key in ordered_keys:
            group = groups[key]
            finals = [row["final_outcome_sha256"] for row in group]
            actions = [row["action_sequence_sha256"] for row in group]
            record = dict(zip(identity_fields, key))
            record.update(
                {
                    "repetitions": len(group),
                    "official_success_rate": sum(int(row["official_success"]) for row in group)
                    / len(group),
                    f"{final_prefix}_distinct_count": len(set(finals)),
                    f"{final_prefix}_consistency": modal_proportion(finals),
                    f"{final_prefix}_entropy_bits": entropy_bits(finals),
                    "action_sequence_distinct_count": len(set(actions)),
                    "action_sequence_consistency": modal_proportion(actions),
                    "action_sequence_entropy_bits": entropy_bits(actions),
                }
            )
            writer.writerow(record)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--environment", choices=("dbbench", "osbench"), required=True)
    args = parser.parse_args()
    summarize(args.input, args.output, args.environment)


if __name__ == "__main__":
    main()
