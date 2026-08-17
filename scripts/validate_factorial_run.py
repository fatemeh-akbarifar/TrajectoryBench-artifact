import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

import yaml

try:
    from scripts.estimate_experiment_cost import estimate_cost
    from scripts.extract_episode_metrics import extract_episode
except ModuleNotFoundError:
    from estimate_experiment_cost import estimate_cost
    from extract_episode_metrics import extract_episode


CELL_SPECS = {
    "dbbench-std-p0c0": {"rounds": 15, "constraint": "c0", "repairs": 0},
    "dbbench-std-p0c1": {"rounds": 15, "constraint": "c1", "repairs": 1},
    "dbbench-std-p1c0": {"rounds": 10, "constraint": "c0", "repairs": 0},
    "dbbench-std-p1c1": {"rounds": 10, "constraint": "c1", "repairs": 1},
}
SMOKE_CELL_SPECS = {
    name.replace("dbbench-std-", "dbbench-smoke-"): spec
    for name, spec in CELL_SPECS.items()
}
OSBENCH_CELL_SPECS = {
    "os-std-p0c0": {"rounds": 8, "constraint": "c0", "repairs": 0},
    "os-std-p0c1": {"rounds": 8, "constraint": "c1", "repairs": 1},
    "os-std-p1c0": {"rounds": 5, "constraint": "c0", "repairs": 0},
    "os-std-p1c1": {"rounds": 5, "constraint": "c1", "repairs": 1},
}
OSBENCH_SMOKE_CELL_SPECS = {
    name.replace("os-std-", "os-smoke-"): spec
    for name, spec in OSBENCH_CELL_SPECS.items()
}


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
    return rows


def validate_config(
    config: Dict[str, Any],
    expected_configured_model: str,
    cell_specs: Dict[str, Dict[str, Any]],
) -> List[str]:
    errors = []
    agent = config.get("definition", {}).get("agent", {}).get("gpt-5", {})
    parameters = agent.get("parameters", {})
    model = parameters.get("body", {}).get("model")
    if model != expected_configured_model:
        errors.append(
            f"configured model is {model!r}, expected {expected_configured_model!r}"
        )

    authorization = parameters.get("headers", {}).get("Authorization")
    if authorization not in (None, "<redacted>"):
        errors.append("saved config contains an unredacted Authorization header")

    configured_tasks = config.get("definition", {}).get("task", {})
    for cell, spec in cell_specs.items():
        task_parameters = configured_tasks.get(cell, {}).get("parameters", {})
        rounds = task_parameters.get("max_round")
        if cell.startswith("os-"):
            rounds = task_parameters.get("round_limit")
        observed = (
            rounds,
            task_parameters.get("output_constraint"),
            task_parameters.get("max_repair_attempts"),
        )
        expected = (spec["rounds"], spec["constraint"], spec["repairs"])
        if observed != expected:
            errors.append(f"{cell} config is {observed!r}, expected {expected!r}")
    return errors


def validate_run(
    run_dir: Path,
    expected_per_cell: int,
    expected_model: str,
    input_rate: Decimal,
    cached_input_rate: Decimal,
    output_rate: Decimal,
    cell_specs: Dict[str, Dict[str, Any]] = CELL_SPECS,
    expected_configured_model: str = None,
    projected_episodes: int = None,
) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    config_path = run_dir / "config.yaml"
    if not config_path.exists():
        errors.append(f"missing {config_path}")
        config = {}
    else:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        errors.extend(
            validate_config(
                config,
                expected_configured_model or expected_model,
                cell_specs,
            )
        )

    cells: Dict[str, Any] = {}
    index_sets = {}
    cost_rows = []
    for cell, spec in cell_specs.items():
        cell_dir = run_dir / "gpt-5" / cell
        runs_path = cell_dir / "runs.jsonl"
        overall_path = cell_dir / "overall.json"
        error_path = cell_dir / "error.jsonl"
        try:
            rows = load_jsonl(runs_path)
            task_errors = load_jsonl(error_path)
        except ValueError as exc:
            errors.append(str(exc))
            rows = []
            task_errors = []

        indices = [row.get("index") for row in rows]
        unique_indices = set(indices)
        index_sets[cell] = unique_indices
        if len(rows) != expected_per_cell:
            errors.append(
                f"{cell} has {len(rows)} completed records, expected {expected_per_cell}"
            )
        if len(unique_indices) != len(indices):
            errors.append(f"{cell} contains duplicate episode indices")
        unresolved_task_errors = [
            row for row in task_errors if row.get("index") not in unique_indices
        ]
        resolved_task_errors = len(task_errors) - len(unresolved_task_errors)
        if unresolved_task_errors:
            errors.append(
                f"{cell} contains {len(unresolved_task_errors)} unresolved "
                "task-client errors"
            )
        if resolved_task_errors:
            warnings.append(
                f"{cell} contains {resolved_task_errors} historical task-client "
                "errors followed by successful reruns"
            )

        official_accuracy = None
        if not overall_path.exists():
            errors.append(f"missing {overall_path}")
        else:
            overall = json.loads(overall_path.read_text(encoding="utf-8"))
            if overall.get("total") != expected_per_cell:
                errors.append(
                    f"{cell} overall total is {overall.get('total')!r}, "
                    f"expected {expected_per_cell}"
                )
            custom = overall.get("custom", {})
            official_accuracy = custom.get("SELECT_accuracy")
            if cell.startswith("os-"):
                official_accuracy = custom.get("overall", {}).get("acc")

        metrics = [extract_episode(row, runs_path) for row in rows]
        if cell.startswith("os-") and metrics:
            episode_accuracy = sum(
                int(bool(row.get("output", {}).get("result", {}).get("result")))
                for row in rows
            ) / len(rows)
            if official_accuracy is None or abs(episode_accuracy - official_accuracy) > 1e-12:
                errors.append(
                    f"{cell} episode scores average to {episode_accuracy}, but "
                    f"overall.json reports accuracy {official_accuracy}"
                )
        wrong_constraints = [
            metric["episode_index"]
            for metric in metrics
            if metric["output_constraint"] != spec["constraint"]
        ]
        if wrong_constraints:
            errors.append(
                f"{cell} has incorrect constraint labels at {wrong_constraints[:10]}"
            )

        observed_models = sorted(
            {
                model
                for metric in metrics
                for model in metric["provider_models"].split("|")
                if model
            }
        )
        unexpected_models = [model for model in observed_models if model != expected_model]
        if unexpected_models:
            errors.append(f"{cell} contains unexpected models: {unexpected_models}")

        missing_metadata = sum(
            1
            for metric in metrics
            if not metric["provider_models"] or metric["total_tokens"] <= 0
        )
        if missing_metadata:
            warnings.append(
                f"{cell} has {missing_metadata} episodes without complete provider metadata"
            )

        for metric in metrics:
            cost_rows.append(
                {
                    "input_tokens": metric["input_tokens"],
                    "cached_input_tokens": metric["cached_input_tokens"],
                    "output_tokens": metric["output_tokens"],
                }
            )
        cells[cell] = {
            "records": len(rows),
            "unique_indices": len(unique_indices),
            "framework_completed": sum(
                metric["completed_indicator"] for metric in metrics
            ),
            "official_accuracy": official_accuracy,
            "repair_attempts": sum(metric["repair_attempts"] for metric in metrics),
            "repair_successes": sum(metric["repair_successes"] for metric in metrics),
            "missing_provider_metadata": missing_metadata,
            "provider_models": observed_models,
        }

    reference_cell = next(iter(cell_specs))
    reference_indices = index_sets.get(reference_cell, set())
    for cell, indices in index_sets.items():
        if indices != reference_indices:
            errors.append(f"{cell} does not contain the same indices as {reference_cell}")

    cost = None
    if cost_rows:
        cost = estimate_cost(
            cost_rows,
            input_rate_per_million=input_rate,
            cached_input_rate_per_million=cached_input_rate,
            output_rate_per_million=output_rate,
            projected_episodes=projected_episodes or len(cost_rows),
        )

    return {
        "valid": not errors,
        "run_dir": str(run_dir),
        "expected_model": expected_model,
        "expected_per_cell": expected_per_cell,
        "expected_total": expected_per_cell * len(cell_specs),
        "errors": errors,
        "warnings": warnings,
        "cells": cells,
        "cost": cost,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--expected-per-cell", type=int, default=300)
    parser.add_argument(
        "--suite",
        choices=("dbbench-full", "dbbench-smoke", "osbench-full", "osbench-smoke", "full", "smoke"),
        default="dbbench-full",
    )
    parser.add_argument("--expected-model", default="gpt-5-2025-08-07")
    parser.add_argument("--expected-configured-model")
    parser.add_argument("--input-rate", default="1.25")
    parser.add_argument("--cached-input-rate", default="0.125")
    parser.add_argument("--output-rate", default="10")
    parser.add_argument("--projected-episodes", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.expected_per_cell <= 0:
        parser.error("--expected-per-cell must be positive")
    if args.projected_episodes is not None and args.projected_episodes <= 0:
        parser.error("--projected-episodes must be positive")

    suites = {
        "dbbench-full": CELL_SPECS,
        "dbbench-smoke": SMOKE_CELL_SPECS,
        "osbench-full": OSBENCH_CELL_SPECS,
        "osbench-smoke": OSBENCH_SMOKE_CELL_SPECS,
        "full": CELL_SPECS,
        "smoke": SMOKE_CELL_SPECS,
    }
    report = validate_run(
        run_dir=args.run_dir,
        expected_per_cell=args.expected_per_cell,
        expected_model=args.expected_model,
        input_rate=Decimal(args.input_rate),
        cached_input_rate=Decimal(args.cached_input_rate),
        output_rate=Decimal(args.output_rate),
        cell_specs=suites[args.suite],
        expected_configured_model=args.expected_configured_model,
        projected_episodes=args.projected_episodes,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    raise SystemExit(0 if report["valid"] else 1)


if __name__ == "__main__":
    main()
