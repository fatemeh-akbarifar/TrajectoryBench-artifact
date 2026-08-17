# Cross-Environment Ranking Sensitivity

The RQ3 analysis compares success-only configuration rankings with the fixed
sensitivity grid documented in
`thesis_protocol/cross_environment_ranking_analysis_plan.md`. The ranking
formula was completed after outcome collection, so the results are descriptive
and are not presented as a preregistered confirmatory analysis.

Run the analysis from the repository root:

```bash
.venv/bin/python scripts/analyze_cross_environment_rankings.py \
  --db-cell results/dbbench_factorial_analysis/cell_descriptives.csv \
  --db-stability results/dbbench_factorial_stability_metrics.csv \
  --os-cell results/osbench_factorial_analysis/cell_descriptives.csv \
  --os-stability results/osbench_factorial_stability_metrics.csv \
  --output-dir results/cross_environment_rankings
```

The command writes `rankings.csv` and `summary.json`. The repository ignores
the `results/` directory; generated analysis output is validation evidence and
must not be included in a source commit.

Run the focused regression tests with:

```bash
.venv/bin/python -m unittest tests.scripts.test_cross_environment_rankings
```

Interpret rank changes across the entire sensitivity grid. A configuration is
not declared universally best from one chosen scheme, and descriptive
five-repeat consistency is not interpreted as reliability.
