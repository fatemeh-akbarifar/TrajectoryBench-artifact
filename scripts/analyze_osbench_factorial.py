import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import chi2
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

try:
    from scripts.analyze_dbbench_factorial import (
        benjamini_hochberg,
        descriptive_cells,
        dispersion_ratio,
        fit_clustered_gaussian,
        fit_gee,
        single_term_row,
    )
except ModuleNotFoundError:
    from analyze_dbbench_factorial import (
        benjamini_hochberg,
        descriptive_cells,
        dispersion_ratio,
        fit_clustered_gaussian,
        fit_gee,
        single_term_row,
    )


COUNT_OUTCOMES = ["approx_steps", "shell_actions"]
TOKEN_OUTCOMES = ["input_tokens", "output_tokens", "total_tokens"]
BINARY_OUTCOMES = [
    "completed_indicator",
    "is_format_error",
    "is_invalid_action",
    "is_task_limit",
]
TRAJECTORY_PREDICTORS = [
    "approx_steps",
    "shell_actions",
    "completed_indicator",
    "is_format_error",
    "is_invalid_action",
    "is_task_limit",
    "input_tokens",
    "output_tokens",
]


def explanatory_cross_validation(df: pd.DataFrame) -> Dict[str, Any]:
    condition_features = ["p", "c", "pxc", "task_family", "evaluator_type"]
    full_features = condition_features + TRAJECTORY_PREDICTORS
    groups = df["task_identity"]
    target = df["official_success"].astype(int)
    output: Dict[str, Any] = {"folds": []}
    for fold, (train, test) in enumerate(
        GroupKFold(n_splits=5).split(df, target, groups), start=1
    ):
        fold_result: Dict[str, Any] = {
            "fold": fold,
            "train_tasks": len(set(groups.iloc[train])),
            "test_tasks": len(set(groups.iloc[test])),
        }
        for label, features in [
            ("condition_only", condition_features),
            ("trajectory_augmented", full_features),
        ]:
            categorical = ["task_family", "evaluator_type"]
            numeric = [column for column in features if column not in categorical]
            preprocess = ColumnTransformer(
                [
                    (
                        "numeric",
                        Pipeline(
                            [
                                ("impute", SimpleImputer(strategy="median")),
                                ("scale", StandardScaler()),
                            ]
                        ),
                        numeric,
                    ),
                    ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical),
                ]
            )
            model = Pipeline(
                [
                    ("preprocess", preprocess),
                    ("model", LogisticRegression(max_iter=2000, random_state=0)),
                ]
            )
            model.fit(df.iloc[train][features], target.iloc[train])
            probability = model.predict_proba(df.iloc[test][features])[:, 1]
            fold_result[label] = {
                "roc_auc": float(roc_auc_score(target.iloc[test], probability)),
                "log_loss": float(log_loss(target.iloc[test], probability)),
            }
        output["folds"].append(fold_result)
    output["mean"] = {}
    output["sd"] = {}
    for label in ["condition_only", "trajectory_augmented"]:
        output["mean"][label] = {}
        output["sd"][label] = {}
        for metric in ["roc_auc", "log_loss"]:
            values = [fold[label][metric] for fold in output["folds"]]
            output["mean"][label][metric] = float(np.mean(values))
            output["sd"][label][metric] = float(np.std(values, ddof=1))
    output["incremental"] = {
        "roc_auc": output["mean"]["trajectory_augmented"]["roc_auc"]
        - output["mean"]["condition_only"]["roc_auc"],
        "log_loss_reduction": output["mean"]["condition_only"]["log_loss"]
        - output["mean"]["trajectory_augmented"]["log_loss"],
    }
    return output


def likelihood_comparison(df: pd.DataFrame) -> Dict[str, Any]:
    work = df.copy()
    work["task"] = work["task_identity"].astype("category")
    base = sm.GLM.from_formula(
        "official_success ~ p * c + C(task)",
        data=work,
        family=sm.families.Binomial(),
    ).fit()
    full = sm.GLM.from_formula(
        "official_success ~ p * c + approx_steps + shell_actions + "
        "completed_indicator + is_format_error + is_invalid_action + is_task_limit + "
        "np.log1p(input_tokens) + np.log1p(output_tokens) + C(task)",
        data=work,
        family=sm.families.Binomial(),
    ).fit()
    statistic = 2 * (full.llf - base.llf)
    degrees = int(full.df_model - base.df_model)
    return {
        "condition_only_log_likelihood": float(base.llf),
        "trajectory_augmented_log_likelihood": float(full.llf),
        "likelihood_ratio": float(statistic),
        "degrees_of_freedom": degrees,
        "p_value": float(chi2.sf(statistic, degrees)),
    }


def analyze(df: pd.DataFrame):
    required = {
        "repetition",
        "condition",
        "p",
        "c",
        "task_identity",
        "task_family",
        "evaluator_type",
        "official_success",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"input is missing columns: {sorted(missing)}")
    if df["official_success"].isna().any():
        raise ValueError("official_success contains missing values")
    if df.duplicated(["repetition", "condition", "task_identity"]).any():
        raise ValueError("input contains duplicate episode identities")
    df = df.copy()
    # Shared clustered-model helpers use the DBBench-era column name.
    df["episode_index"] = df["task_identity"]
    df["pxc"] = df["p"] * df["c"]
    estimates: List[Dict[str, Any]] = []
    diagnostics: List[Dict[str, Any]] = []

    rows, diagnostic = fit_gee(
        df, "official_success", sm.families.Binomial(), "logistic_gee_task_cluster"
    )
    estimates.extend(rows)
    diagnostics.append(diagnostic)

    for outcome in COUNT_OUTCOMES:
        dispersion = dispersion_ratio(df[outcome])
        if dispersion > 1.5:
            family = sm.families.NegativeBinomial(alpha=1.0)
            label = "negative_binomial_gee_task_cluster"
        else:
            family = sm.families.Poisson()
            label = "poisson_gee_task_cluster"
        rows, diagnostic = fit_gee(df, outcome, family, label)
        diagnostic["dispersion_ratio"] = dispersion
        estimates.extend(rows)
        diagnostics.append(diagnostic)

    for outcome in TOKEN_OUTCOMES:
        rows, diagnostic = fit_clustered_gaussian(df, outcome)
        estimates.extend(rows)
        diagnostics.append(diagnostic)

    for outcome in BINARY_OUTCOMES:
        events = int(df[outcome].sum())
        nonevents = len(df) - events
        if min(events, nonevents) < 20:
            diagnostics.append(
                {
                    "outcome": outcome,
                    "model": "descriptive_sparse_events",
                    "events": events,
                    "nonevents": nonevents,
                    "converged": None,
                }
            )
            continue
        rows, diagnostic = fit_gee(
            df, outcome, sm.families.Binomial(), "logistic_gee_task_cluster"
        )
        diagnostic.update({"events": events, "nonevents": nonevents})
        estimates.extend(rows)
        diagnostics.append(diagnostic)

    repair = df[df["c"] == 1].copy()
    events = int(repair["repair_attempted_indicator"].sum())
    nonevents = len(repair) - events
    if min(events, nonevents) < 20:
        diagnostics.append(
            {
                "outcome": "repair_attempted_indicator",
                "model": "descriptive_sparse_events_c1_only",
                "events": events,
                "nonevents": nonevents,
                "converged": None,
                "structural_note": "C0 has no repair path; C1 repair attempts are sparse.",
            }
        )
    else:
        model = sm.GEE.from_formula(
            "repair_attempted_indicator ~ p",
            groups="task_identity",
            cov_struct=sm.cov_struct.Exchangeable(),
            family=sm.families.Binomial(),
            data=repair,
        ).fit()
        estimates.append(
            single_term_row(
                model,
                "repair_attempted_indicator",
                "logistic_gee_c1_only_task_cluster",
                "p",
                "p_within_c1",
            )
        )
        diagnostics.append(
            {
                "outcome": "repair_attempted_indicator",
                "model": "logistic_gee_c1_only_task_cluster",
                "events": events,
                "nonevents": nonevents,
                "observations": int(model.nobs),
                "converged": bool(model.converged),
            }
        )
    attempted = repair[repair["repair_attempted_indicator"] == 1]
    diagnostics.append(
        {
            "outcome": "repair_succeeded_indicator",
            "model": "descriptive_conditional_on_attempt",
            "attempted_repairs": int(len(attempted)),
            "successful_repairs": int(attempted["repair_succeeded_indicator"].sum()),
            "success_rate": float(attempted["repair_succeeded_indicator"].mean())
            if len(attempted)
            else math.nan,
            "converged": None,
        }
    )

    estimates_df = pd.DataFrame(estimates)
    secondary = estimates_df["outcome"] != "official_success"
    estimates_df["bh_adjusted_p"] = np.nan
    estimates_df.loc[secondary, "bh_adjusted_p"] = benjamini_hochberg(
        estimates_df.loc[secondary, "p_value"]
    )
    numeric = ["estimate", "ci_lower", "ci_upper", "p_value"]
    if not np.isfinite(estimates_df[numeric].to_numpy(dtype=float)).all():
        raise ValueError("inferential results contain non-finite values")
    outcomes = (
        ["official_success"]
        + COUNT_OUTCOMES
        + TOKEN_OUTCOMES
        + BINARY_OUTCOMES
        + ["repair_attempted_indicator", "repair_succeeded_indicator"]
    )
    return (
        estimates_df,
        descriptive_cells(df, outcomes),
        diagnostics,
        explanatory_cross_validation(df),
        likelihood_comparison(df),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    df = pd.read_csv(args.input)
    outputs = analyze(df)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs[0].to_csv(args.output_dir / "factorial_effects.csv", index=False)
    outputs[1].to_csv(args.output_dir / "cell_descriptives.csv", index=False)
    for name, value in [
        ("model_diagnostics.json", outputs[2]),
        ("explanatory_cross_validation.json", outputs[3]),
        ("explanatory_likelihood_comparison.json", outputs[4]),
    ]:
        (args.output_dir / name).write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(f"Analyzed {len(df)} OSBench episodes.")
    print(f"Outputs: {args.output_dir}")


if __name__ == "__main__":
    main()
