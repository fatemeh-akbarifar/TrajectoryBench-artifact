import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List

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


COUNT_OUTCOMES = ["approx_steps", "sql_operations"]
TOKEN_OUTCOMES = ["input_tokens", "output_tokens", "total_tokens"]
BINARY_OUTCOMES = [
    "has_sql_error",
    "is_format_error",
    "is_invalid_action",
    "is_task_limit",
]
TRAJECTORY_PREDICTORS = [
    "approx_steps",
    "sql_operations",
    "has_sql_error",
    "is_format_error",
    "is_invalid_action",
    "is_task_limit",
    "input_tokens",
    "output_tokens",
]


def benjamini_hochberg(p_values: Iterable[float]) -> List[float]:
    values = np.asarray(list(p_values), dtype=float)
    adjusted = np.full(len(values), np.nan)
    finite = np.isfinite(values)
    indices = np.where(finite)[0]
    if not len(indices):
        return adjusted.tolist()
    order = indices[np.argsort(values[indices])]
    ranked = values[order] * len(order) / np.arange(1, len(order) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    adjusted[order] = np.minimum(ranked, 1.0)
    return adjusted.tolist()


def dispersion_ratio(values: pd.Series) -> float:
    mean = float(values.mean())
    return float(values.var(ddof=1) / mean) if mean > 0 else math.nan


def model_rows(result, outcome: str, model: str, scale: str) -> List[Dict[str, Any]]:
    intervals = result.conf_int()
    rows = []
    for term in ["p", "c", "p:c"]:
        estimate = float(result.params[term])
        lower, upper = map(float, intervals.loc[term])
        rows.append(
            {
                "outcome": outcome,
                "model": model,
                "term": term,
                "scale": scale,
                "estimate": estimate,
                "ci_lower": lower,
                "ci_upper": upper,
                "ratio_estimate": math.exp(estimate),
                "ratio_ci_lower": math.exp(lower),
                "ratio_ci_upper": math.exp(upper),
                "p_value": float(result.pvalues[term]),
            }
        )
    return rows


def single_term_row(result, outcome: str, model: str, term: str, reported_term: str):
    lower, upper = map(float, result.conf_int().loc[term])
    estimate = float(result.params[term])
    return {
        "outcome": outcome,
        "model": model,
        "term": reported_term,
        "scale": "link",
        "estimate": estimate,
        "ci_lower": lower,
        "ci_upper": upper,
        "ratio_estimate": math.exp(estimate),
        "ratio_ci_lower": math.exp(lower),
        "ratio_ci_upper": math.exp(upper),
        "p_value": float(result.pvalues[term]),
    }


def fit_gee(df: pd.DataFrame, outcome: str, family, model_label: str):
    result = sm.GEE.from_formula(
        f"{outcome} ~ p * c",
        groups="episode_index",
        cov_struct=sm.cov_struct.Exchangeable(),
        family=family,
        data=df,
    ).fit()
    return model_rows(result, outcome, model_label, "link"), {
        "outcome": outcome,
        "model": model_label,
        "converged": bool(result.converged),
        "observations": int(result.nobs),
        "working_correlation": float(result.cov_struct.dep_params),
    }


def fit_clustered_gaussian(df: pd.DataFrame, outcome: str):
    transformed = f"log1p_{outcome}"
    work = df.copy()
    work[transformed] = np.log1p(work[outcome])
    result = sm.OLS.from_formula(f"{transformed} ~ p * c", data=work).fit(
        cov_type="cluster", cov_kwds={"groups": work["episode_index"]}
    )
    rows = model_rows(result, outcome, "clustered_gaussian_log1p", "log1p")
    return rows, {
        "outcome": outcome,
        "model": "clustered_gaussian_log1p",
        "converged": True,
        "observations": int(result.nobs),
        "skewness_raw": float(work[outcome].skew()),
        "skewness_log1p": float(work[transformed].skew()),
        "r_squared": float(result.rsquared),
    }


def descriptive_cells(df: pd.DataFrame, outcomes: List[str]) -> pd.DataFrame:
    rows = []
    for condition, group in df.groupby("condition", sort=True):
        for outcome in outcomes:
            values = group[outcome].dropna().astype(float)
            mean = float(values.mean())
            se = float(values.std(ddof=1) / math.sqrt(len(values)))
            rows.append(
                {
                    "condition": condition,
                    "outcome": outcome,
                    "n": len(values),
                    "mean": mean,
                    "sd": float(values.std(ddof=1)),
                    "ci_lower": mean - 1.96 * se,
                    "ci_upper": mean + 1.96 * se,
                }
            )
    return pd.DataFrame(rows)


def explanatory_cross_validation(df: pd.DataFrame) -> Dict[str, Any]:
    condition_features = ["p", "c", "pxc", "task_type"]
    full_features = condition_features + TRAJECTORY_PREDICTORS
    groups = df["episode_index"]
    target = df["official_success"].astype(int)
    folds = GroupKFold(n_splits=5)
    output = {"folds": []}

    for fold, (train, test) in enumerate(folds.split(df, target, groups), start=1):
        fold_result = {"fold": fold, "train_tasks": len(set(groups.iloc[train])), "test_tasks": len(set(groups.iloc[test]))}
        for label, features in [("condition_only", condition_features), ("trajectory_augmented", full_features)]:
            categorical = ["task_type"]
            numeric = [column for column in features if column not in categorical]
            preprocessor = ColumnTransformer(
                [
                    ("numeric", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
                    ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical),
                ]
            )
            model = Pipeline(
                [("preprocess", preprocessor), ("model", LogisticRegression(max_iter=2000, random_state=0))]
            )
            model.fit(df.iloc[train][features], target.iloc[train])
            probability = model.predict_proba(df.iloc[test][features])[:, 1]
            fold_result[label] = {
                "roc_auc": float(roc_auc_score(target.iloc[test], probability)),
                "log_loss": float(log_loss(target.iloc[test], probability)),
            }
        output["folds"].append(fold_result)

    for label in ["condition_only", "trajectory_augmented"]:
        for metric in ["roc_auc", "log_loss"]:
            values = [fold[label][metric] for fold in output["folds"]]
            output.setdefault("mean", {}).setdefault(label, {})[metric] = float(np.mean(values))
            output.setdefault("sd", {}).setdefault(label, {})[metric] = float(np.std(values, ddof=1))
    output["incremental"] = {
        "roc_auc": output["mean"]["trajectory_augmented"]["roc_auc"] - output["mean"]["condition_only"]["roc_auc"],
        "log_loss_reduction": output["mean"]["condition_only"]["log_loss"] - output["mean"]["trajectory_augmented"]["log_loss"],
    }
    return output


def likelihood_comparison(df: pd.DataFrame) -> Dict[str, Any]:
    work = df.copy()
    work["task"] = work["episode_index"].astype("category")
    base = sm.GLM.from_formula("official_success ~ p * c + C(task)", data=work, family=sm.families.Binomial()).fit()
    full = sm.GLM.from_formula(
        "official_success ~ p * c + approx_steps + sql_operations + has_sql_error + is_format_error + is_invalid_action + is_task_limit + np.log1p(input_tokens) + np.log1p(output_tokens) + C(task)",
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
    required = {"official_success", "p", "c", "condition", "episode_index", "task_type"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"input is missing columns: {sorted(missing)}")
    if df["official_success"].isna().any():
        raise ValueError("official_success contains missing values")
    if df.duplicated(["repetition", "condition", "episode_index"]).any():
        raise ValueError("input contains duplicate episode identities")
    df = df.copy()
    df["pxc"] = df["p"] * df["c"]

    estimates = []
    diagnostics = []
    rows, diagnostic = fit_gee(df, "official_success", sm.families.Binomial(), "logistic_gee_task_cluster")
    estimates.extend(rows); diagnostics.append(diagnostic)

    for outcome in COUNT_OUTCOMES:
        dispersion = dispersion_ratio(df[outcome])
        if dispersion > 1.5:
            family, label = sm.families.NegativeBinomial(alpha=1.0), "negative_binomial_gee_task_cluster"
        else:
            family, label = sm.families.Poisson(), "poisson_gee_task_cluster"
        rows, diagnostic = fit_gee(df, outcome, family, label)
        diagnostic["dispersion_ratio"] = dispersion
        estimates.extend(rows); diagnostics.append(diagnostic)

    for outcome in TOKEN_OUTCOMES:
        rows, diagnostic = fit_clustered_gaussian(df, outcome)
        estimates.extend(rows); diagnostics.append(diagnostic)

    for outcome in BINARY_OUTCOMES:
        events = int(df[outcome].sum())
        nonevents = len(df) - events
        if min(events, nonevents) < 20:
            diagnostics.append({"outcome": outcome, "model": "descriptive_sparse_events", "events": events, "nonevents": nonevents, "converged": None})
            continue
        rows, diagnostic = fit_gee(df, outcome, sm.families.Binomial(), "logistic_gee_task_cluster")
        diagnostic.update({"events": events, "nonevents": nonevents})
        estimates.extend(rows); diagnostics.append(diagnostic)

    repair = df[df["c"] == 1].copy()
    repair_events = int(repair["repair_attempted_indicator"].sum())
    repair_nonevents = len(repair) - repair_events
    repair_model = sm.GEE.from_formula(
        "repair_attempted_indicator ~ p",
        groups="episode_index",
        cov_struct=sm.cov_struct.Exchangeable(),
        family=sm.families.Binomial(),
        data=repair,
    ).fit()
    estimates.append(
        single_term_row(
            repair_model,
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
            "converged": bool(repair_model.converged),
            "observations": int(repair_model.nobs),
            "events": repair_events,
            "nonevents": repair_nonevents,
            "working_correlation": float(repair_model.cov_struct.dep_params),
            "structural_note": "C0 has no repair path; only P is compared within C1.",
        }
    )
    attempted = repair[repair["repair_attempted_indicator"] == 1]
    diagnostics.append(
        {
            "outcome": "repair_succeeded_indicator",
            "model": "descriptive_conditional_on_attempt",
            "attempted_repairs": int(len(attempted)),
            "successful_repairs": int(attempted["repair_succeeded_indicator"].sum()),
            "success_rate": float(attempted["repair_succeeded_indicator"].mean()),
            "converged": None,
        }
    )

    estimates_df = pd.DataFrame(estimates)
    secondary = estimates_df["outcome"] != "official_success"
    estimates_df["bh_adjusted_p"] = np.nan
    estimates_df.loc[secondary, "bh_adjusted_p"] = benjamini_hochberg(estimates_df.loc[secondary, "p_value"])
    numeric = ["estimate", "ci_lower", "ci_upper", "p_value"]
    if not np.isfinite(estimates_df[numeric].to_numpy(dtype=float)).all():
        raise ValueError("inferential results contain non-finite values")
    outcomes = ["official_success"] + COUNT_OUTCOMES + TOKEN_OUTCOMES + BINARY_OUTCOMES + ["repair_attempted_indicator", "repair_succeeded_indicator"]
    return (
        estimates_df,
        descriptive_cells(df, outcomes),
        diagnostics,
        explanatory_cross_validation(df),
        likelihood_comparison(df),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    estimates, descriptions, diagnostics, cross_validation, comparison = analyze(pd.read_csv(args.input))
    estimates.to_csv(output / "factorial_effects.csv", index=False)
    descriptions.to_csv(output / "cell_descriptives.csv", index=False)
    (output / "model_diagnostics.json").write_text(json.dumps(diagnostics, indent=2, sort_keys=True) + "\n")
    (output / "explanatory_cross_validation.json").write_text(json.dumps(cross_validation, indent=2, sort_keys=True) + "\n")
    (output / "explanatory_likelihood_comparison.json").write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n")
    print(f"Analyzed {len(pd.read_csv(args.input))} episodes.")
    print(f"Outputs: {output}")


if __name__ == "__main__":
    main()
