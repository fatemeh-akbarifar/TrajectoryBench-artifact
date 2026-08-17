#!/usr/bin/env python3
"""Compare success-only and multi-metric configuration rankings for RQ3."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable


CONDITIONS = ("P0C0", "P0C1", "P1C0", "P1C1")

METRICS = {
    "success": ("official_success", "higher"),
    "steps": ("approx_steps", "lower"),
    "actions": ({"dbbench": "sql_operations", "osbench": "shell_actions"}, "lower"),
    "tokens": ("total_tokens", "lower"),
    "format_errors": ("is_format_error", "lower"),
    "invalid_actions": ("is_invalid_action", "lower"),
    "task_limits": ("is_task_limit", "lower"),
    "final_consistency": (
        {"dbbench": "final_answer_consistency", "osbench": "final_outcome_consistency"},
        "higher",
    ),
    "action_consistency": ("action_sequence_consistency", "higher"),
}

DOMAINS = {
    "success": ("success",),
    "efficiency": ("steps", "actions", "tokens"),
    "execution_validity": ("format_errors", "invalid_actions", "task_limits"),
    "variability": ("final_consistency", "action_consistency"),
}

SCHEMES = {
    "success_only": {"domains": ("success",), "balance": "domains"},
    "core_domain_balanced": {
        "domains": ("success", "efficiency", "variability"),
        "balance": "domains",
    },
    "core_metric_balanced": {
        "domains": ("success", "efficiency", "variability"),
        "balance": "metrics",
    },
    "broad_domain_balanced": {
        "domains": ("success", "efficiency", "execution_validity", "variability"),
        "balance": "domains",
    },
}


def average_ranks(values: dict[str, float], preferred: str = "higher") -> dict[str, float]:
    """Return average ranks, where rank 1 is always preferable."""
    reverse = preferred == "higher"
    ordered = sorted(values.items(), key=lambda item: item[1], reverse=reverse)
    result: dict[str, float] = {}
    position = 1
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        tied_positions = range(position, position + end - index)
        rank = sum(tied_positions) / (end - index)
        for condition, _ in ordered[index:end]:
            result[condition] = rank
        position += end - index
        index = end
    return result


def rank_utilities(values: dict[str, float], preferred: str) -> dict[str, float]:
    ranks = average_ranks(values, preferred)
    denominator = max(len(ranks) - 1, 1)
    return {condition: (len(ranks) - rank) / denominator for condition, rank in ranks.items()}


def _read_cell_means(path: Path) -> dict[str, dict[str, float]]:
    means: dict[str, dict[str, float]] = defaultdict(dict)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            means[row["outcome"]][row["condition"]] = float(row["mean"])
    return means


def _read_stability_means(path: Path) -> dict[str, dict[str, float]]:
    collected: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            for outcome in (
                "final_answer_consistency",
                "final_outcome_consistency",
                "action_sequence_consistency",
            ):
                if outcome in row:
                    collected[outcome][row["condition"]].append(float(row[outcome]))
    return {
        outcome: {
            condition: sum(values) / len(values)
            for condition, values in by_condition.items()
        }
        for outcome, by_condition in collected.items()
    }


def load_environment_metrics(
    environment: str, cell_path: Path, stability_path: Path
) -> dict[str, dict[str, float]]:
    sources = _read_cell_means(cell_path)
    sources.update(_read_stability_means(stability_path))
    result: dict[str, dict[str, float]] = {}
    for metric, (source, _) in METRICS.items():
        outcome = source[environment] if isinstance(source, dict) else source
        if outcome not in sources or set(sources[outcome]) != set(CONDITIONS):
            raise ValueError(f"Missing complete {environment} metric: {outcome}")
        result[metric] = sources[outcome]
    return result


def aggregate_scheme(
    metric_utilities: dict[str, dict[str, float]], scheme: dict[str, object]
) -> dict[str, float]:
    domains = scheme["domains"]
    if scheme["balance"] == "metrics":
        selected = [metric for domain in domains for metric in DOMAINS[domain]]
        return {
            condition: sum(metric_utilities[m][condition] for m in selected) / len(selected)
            for condition in CONDITIONS
        }
    domain_scores = {
        domain: {
            condition: sum(metric_utilities[m][condition] for m in DOMAINS[domain])
            / len(DOMAINS[domain])
            for condition in CONDITIONS
        }
        for domain in domains
    }
    return {
        condition: sum(domain_scores[d][condition] for d in domains) / len(domains)
        for condition in CONDITIONS
    }


def spearman_from_ranks(first: dict[str, float], second: dict[str, float]) -> float:
    """Pearson correlation of average ranks, including tied ranks."""
    x = [first[c] for c in CONDITIONS]
    y = [second[c] for c in CONDITIONS]
    x_mean, y_mean = sum(x) / len(x), sum(y) / len(y)
    numerator = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y))
    x_ss = sum((a - x_mean) ** 2 for a in x)
    y_ss = sum((b - y_mean) ** 2 for b in y)
    return numerator / (x_ss * y_ss) ** 0.5 if x_ss and y_ss else 1.0


def analyze(environments: dict[str, dict[str, dict[str, float]]]) -> tuple[list[dict], dict]:
    environment_scores: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    rows: list[dict] = []
    for environment, metrics in environments.items():
        utilities = {
            metric: rank_utilities(values, METRICS[metric][1])
            for metric, values in metrics.items()
        }
        for scheme_name, scheme in SCHEMES.items():
            scores = aggregate_scheme(utilities, scheme)
            ranks = average_ranks(scores, "higher")
            environment_scores[environment][scheme_name] = scores
            for condition in CONDITIONS:
                rows.append(
                    {
                        "scope": environment,
                        "scheme": scheme_name,
                        "condition": condition,
                        "utility": scores[condition],
                        "rank": ranks[condition],
                    }
                )

    pooled_ranks: dict[str, dict[str, float]] = {}
    pooled_scores: dict[str, dict[str, float]] = {}
    for scheme_name in SCHEMES:
        scores = {
            condition: sum(
                environment_scores[environment][scheme_name][condition]
                for environment in environments
            )
            / len(environments)
            for condition in CONDITIONS
        }
        ranks = average_ranks(scores, "higher")
        pooled_scores[scheme_name] = scores
        pooled_ranks[scheme_name] = ranks
        for condition in CONDITIONS:
            rows.append(
                {
                    "scope": "cross_environment",
                    "scheme": scheme_name,
                    "condition": condition,
                    "utility": scores[condition],
                    "rank": ranks[condition],
                }
            )

    baseline = pooled_ranks["success_only"]
    for row in rows:
        if row["scope"] == "cross_environment":
            row["rank_change_from_success_only"] = baseline[row["condition"]] - row["rank"]
        else:
            row["rank_change_from_success_only"] = ""
    summary = {
        "analysis_role": "descriptive RQ3 sensitivity analysis; ranking formula completed after outcome collection",
        "environment_weighting": "equal",
        "schemes": SCHEMES,
        "cross_environment": {
            scheme: {
                "ordering": sorted(CONDITIONS, key=lambda c: (pooled_ranks[scheme][c], c)),
                "ranks": pooled_ranks[scheme],
                "utilities": pooled_scores[scheme],
                "spearman_vs_success_only": spearman_from_ranks(baseline, pooled_ranks[scheme]),
            }
            for scheme in SCHEMES
        },
    }
    return rows, summary


def write_outputs(rows: Iterable[dict], summary: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "rankings.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "scope",
                "scheme",
                "condition",
                "utility",
                "rank",
                "rank_change_from_success_only",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-cell", type=Path, required=True)
    parser.add_argument("--db-stability", type=Path, required=True)
    parser.add_argument("--os-cell", type=Path, required=True)
    parser.add_argument("--os-stability", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    environments = {
        "dbbench": load_environment_metrics("dbbench", args.db_cell, args.db_stability),
        "osbench": load_environment_metrics("osbench", args.os_cell, args.os_stability),
    }
    rows, summary = analyze(environments)
    write_outputs(rows, summary, args.output_dir)


if __name__ == "__main__":
    main()
