import argparse
import csv
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List


MILLION = Decimal("1000000")
REQUIRED_COLUMNS = {"input_tokens", "cached_input_tokens", "output_tokens"}


def read_episode_rows(paths: Iterable[Path]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    f"{path} is missing required columns: {', '.join(sorted(missing))}"
                )
            rows.extend(reader)
    if not rows:
        raise ValueError("No episode rows found")
    return rows


def nonnegative_decimal(value: Any, label: str) -> Decimal:
    result = Decimal(str(value))
    if result < 0:
        raise ValueError(f"{label} must be non-negative")
    return result


def estimate_cost(
    rows: List[Dict[str, Any]],
    input_rate_per_million: Any,
    cached_input_rate_per_million: Any,
    output_rate_per_million: Any,
    projected_episodes: int = 0,
) -> Dict[str, Any]:
    input_rate = nonnegative_decimal(input_rate_per_million, "input rate")
    cached_rate = nonnegative_decimal(
        cached_input_rate_per_million, "cached input rate"
    )
    output_rate = nonnegative_decimal(output_rate_per_million, "output rate")
    if projected_episodes < 0:
        raise ValueError("projected episodes must be non-negative")

    input_tokens = sum(int(row["input_tokens"]) for row in rows)
    cached_input_tokens = sum(int(row["cached_input_tokens"]) for row in rows)
    output_tokens = sum(int(row["output_tokens"]) for row in rows)
    if cached_input_tokens > input_tokens:
        raise ValueError("cached input tokens cannot exceed total input tokens")

    uncached_input_tokens = input_tokens - cached_input_tokens
    input_cost = Decimal(uncached_input_tokens) * input_rate / MILLION
    cached_input_cost = Decimal(cached_input_tokens) * cached_rate / MILLION
    output_cost = Decimal(output_tokens) * output_rate / MILLION
    observed_cost = input_cost + cached_input_cost + output_cost
    mean_episode_cost = observed_cost / Decimal(len(rows))
    projected_cost = mean_episode_cost * Decimal(projected_episodes)

    return {
        "observed_episodes": len(rows),
        "projected_episodes": projected_episodes,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "uncached_input_tokens": uncached_input_tokens,
        "output_tokens": output_tokens,
        "input_rate_per_million_usd": float(input_rate),
        "cached_input_rate_per_million_usd": float(cached_rate),
        "output_rate_per_million_usd": float(output_rate),
        "observed_input_cost_usd": float(input_cost),
        "observed_cached_input_cost_usd": float(cached_input_cost),
        "observed_output_cost_usd": float(output_cost),
        "observed_total_cost_usd": float(observed_cost),
        "mean_episode_cost_usd": float(mean_episode_cost),
        "projected_total_cost_usd": float(projected_cost),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", nargs="+", required=True, type=Path)
    parser.add_argument("--input-rate", required=True)
    parser.add_argument("--cached-input-rate", required=True)
    parser.add_argument("--output-rate", required=True)
    parser.add_argument("--projected-episodes", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    rows = read_episode_rows(args.input)
    estimate = estimate_cost(
        rows,
        input_rate_per_million=args.input_rate,
        cached_input_rate_per_million=args.cached_input_rate,
        output_rate_per_million=args.output_rate,
        projected_episodes=args.projected_episodes,
    )
    rendered = json.dumps(estimate, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
