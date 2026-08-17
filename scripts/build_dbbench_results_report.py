import argparse
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/agentbench-matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/agentbench-cache")

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


CONDITION_ORDER = ["P0C0", "P0C1", "P1C0", "P1C1"]
CONDITION_COLORS = {
    "P0C0": "#4C78A8",
    "P0C1": "#72B7B2",
    "P1C0": "#F58518",
    "P1C1": "#E45756",
}
TERM_LABELS = {"p": "P1 vs P0", "c": "C1 vs C0", "p:c": "P × C"}


def ordered_conditions(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["condition"] = pd.Categorical(
        result["condition"], categories=CONDITION_ORDER, ordered=True
    )
    return result.sort_values("condition")


def select_effects(effects: pd.DataFrame, outcome: str) -> pd.DataFrame:
    selected = effects[effects["outcome"] == outcome].copy()
    selected["term_label"] = selected["term"].map(TERM_LABELS).fillna(
        selected["term"]
    )
    order = {term: position for position, term in enumerate(["p", "c", "p:c"])}
    selected["term_order"] = selected["term"].map(order)
    return selected.sort_values("term_order")


def save_figure(fig, base_path: Path) -> None:
    base_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(base_path.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(base_path.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_success(descriptives: pd.DataFrame, output_dir: Path) -> None:
    data = ordered_conditions(
        descriptives[descriptives["outcome"] == "official_success"]
    )
    x = np.arange(len(data))
    means = data["mean"].to_numpy() * 100
    lower = (data["mean"] - data["ci_lower"]).to_numpy() * 100
    upper = (data["ci_upper"] - data["mean"]).to_numpy() * 100
    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    ax.bar(
        x,
        means,
        color=[CONDITION_COLORS[str(value)] for value in data["condition"]],
        width=0.66,
    )
    ax.errorbar(x, means, yerr=[lower, upper], fmt="none", color="black", capsize=4)
    ax.set_xticks(x, [str(value) for value in data["condition"]])
    ax.set_ylabel("Official task success (%)")
    ax.set_xlabel("Factorial condition")
    ax.set_ylim(0, 65)
    ax.grid(axis="y", alpha=0.25)
    for position, value in zip(x, means):
        ax.text(position, value + 1.2, f"{value:.1f}%", ha="center", fontsize=9)
    fig.tight_layout()
    save_figure(fig, output_dir / "dbbench_success_by_condition")


def plot_success_effects(effects: pd.DataFrame, output_dir: Path) -> None:
    data = select_effects(effects, "official_success")
    estimate = data["ratio_estimate"].to_numpy()
    lower = data["ratio_ci_lower"].to_numpy()
    upper = data["ratio_ci_upper"].to_numpy()
    y = np.arange(len(data))[::-1]
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    ax.axvline(1.0, color="#666666", linestyle="--", linewidth=1)
    ax.errorbar(
        estimate,
        y,
        xerr=[estimate - lower, upper - estimate],
        fmt="o",
        color="#4C78A8",
        capsize=4,
    )
    ax.set_yticks(y, data["term_label"])
    ax.set_xlabel("Population-average odds ratio (95% CI)")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    save_figure(fig, output_dir / "dbbench_success_factorial_effects")


def plot_resources(descriptives: pd.DataFrame, output_dir: Path) -> None:
    outcomes = [
        ("approx_steps", "Interaction steps"),
        ("sql_operations", "SQL operations"),
        ("total_tokens", "Total tokens"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(10.2, 3.6))
    for ax, (outcome, label) in zip(axes, outcomes):
        data = ordered_conditions(descriptives[descriptives["outcome"] == outcome])
        x = np.arange(len(data))
        ax.bar(
            x,
            data["mean"],
            color=[CONDITION_COLORS[str(value)] for value in data["condition"]],
            width=0.68,
        )
        ax.set_xticks(x, [str(value) for value in data["condition"]], rotation=35)
        ax.set_title(label)
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("Mean per episode")
    fig.tight_layout()
    save_figure(fig, output_dir / "dbbench_trajectory_resources")


def plot_stability(stability: pd.DataFrame, output_dir: Path) -> None:
    means = (
        stability.groupby("condition", as_index=False)[
            ["final_answer_consistency", "action_sequence_consistency"]
        ]
        .mean()
        .pipe(ordered_conditions)
    )
    x = np.arange(len(means))
    width = 0.36
    fig, ax = plt.subplots(figsize=(6.8, 4.0))
    ax.bar(
        x - width / 2,
        means["final_answer_consistency"],
        width,
        label="Final-answer consistency",
        color="#4C78A8",
    )
    ax.bar(
        x + width / 2,
        means["action_sequence_consistency"],
        width,
        label="Action-sequence consistency",
        color="#F58518",
    )
    ax.set_xticks(x, [str(value) for value in means["condition"]])
    ax.set_ylabel("Mean modal proportion")
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=False, loc="lower left")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    save_figure(fig, output_dir / "dbbench_stability_by_condition")


def publication_tables(
    effects: pd.DataFrame, descriptives: pd.DataFrame, stability: pd.DataFrame
):
    success = ordered_conditions(
        descriptives[descriptives["outcome"] == "official_success"]
    )[["condition", "n", "mean", "ci_lower", "ci_upper"]]
    primary = select_effects(effects, "official_success")[
        [
            "term",
            "term_label",
            "ratio_estimate",
            "ratio_ci_lower",
            "ratio_ci_upper",
            "p_value",
        ]
    ]
    secondary = effects[
        (effects["outcome"] != "official_success")
        & effects["bh_adjusted_p"].notna()
    ].sort_values(["bh_adjusted_p", "outcome", "term"])
    stability_table = (
        stability.groupby("condition", as_index=False)[
            [
                "final_answer_consistency",
                "final_answer_entropy_bits",
                "action_sequence_consistency",
                "action_sequence_entropy_bits",
            ]
        ]
        .mean()
        .pipe(ordered_conditions)
    )
    return success, primary, secondary, stability_table


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis-dir", required=True, type=Path)
    parser.add_argument("--stability", required=True, type=Path)
    parser.add_argument("--figure-dir", required=True, type=Path)
    parser.add_argument("--table-dir", required=True, type=Path)
    args = parser.parse_args()

    effects = pd.read_csv(args.analysis_dir / "factorial_effects.csv")
    descriptives = pd.read_csv(args.analysis_dir / "cell_descriptives.csv")
    stability = pd.read_csv(args.stability)
    plot_success(descriptives, args.figure_dir)
    plot_success_effects(effects, args.figure_dir)
    plot_resources(descriptives, args.figure_dir)
    plot_stability(stability, args.figure_dir)
    args.table_dir.mkdir(parents=True, exist_ok=True)
    names = [
        "success_by_condition",
        "primary_success_effects",
        "secondary_effects",
        "stability_by_condition",
    ]
    for name, table in zip(names, publication_tables(effects, descriptives, stability)):
        table.to_csv(args.table_dir / f"{name}.csv", index=False)
    print(f"Generated 4 figures in PDF and PNG formats: {args.figure_dir}")
    print(f"Generated 4 publication tables: {args.table_dir}")


if __name__ == "__main__":
    main()
