# Reproducing TrajectoryBench results

This guide separates reproducibility of the stored analysis from a new run of the proprietary model API. A new API run is a replication attempt and is not expected to reproduce identical trajectories.

The fixed artifact version is `v1.0.0`, archived under the published Zenodo DOI
[10.5281/zenodo.21971301](https://doi.org/10.5281/zenodo.21971301). The public
repository is <https://github.com/fatemeh-akbarifar/TrajectoryBench-artifact>.

## Build the sanitized research-data archive

The private working directory contains raw trajectories, provider response
identifiers, and generated text that are not required for independent analysis.
Build the public package from the audited local results without changing them:

```bash
PYTHONPATH=. .venv/bin/python scripts/build_research_archive.py \
  --repo-root . \
  --output ../trajectorybench-research-data-v1.0.0
```

The output directory must not already exist. The builder removes free-text,
provider-only, timestamp, and local-path fields; represents normalized final
outcomes by SHA-256 for recurrence verification; copies the reviewed derived
outputs; and writes `MANIFEST.csv` and `SHA256SUMS`. Raw trajectories are not
part of the public archive.

## Release inputs

The audited private inputs have the following row counts and checksums before
sanitization:

| Input | Rows | SHA-256 |
|---|---:|---|
| `results/dbbench_factorial_rescored_episode_metrics.csv` | 6,000 | `a3c2f12b014ae0b3e90bde1a57ec30635035217da13f0047e1d33f013a0843f8` |
| `results/osbench_factorial_episode_metrics.csv` | 2,880 | `26262e4043b57bf48620cf40e4ee20c8adc995ede0ba6dd179270467732edce8` |

The public package records new checksums for its sanitized files. Verify them
with `SHA256SUMS`; do not substitute files with the same name but different
checksums. The package also contains the reviewed cell summaries, stability
summaries, model diagnostics, explanatory analyses, sensitivity-model outputs,
publication tables, and ranking outputs listed in `MANIFEST.csv`.

## Environment

From a clean checkout of the release tag:

```bash
python3.9 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-analysis.txt
```

The random-intercept logistic sensitivity analyses use the pinned container in `analysis/r-glmm/Dockerfile`.

## DBBench stored-data analysis

```bash
PYTHONPATH=. .venv/bin/python scripts/analyze_dbbench_factorial.py \
  --input DATA_ARCHIVE/data/dbbench_factorial_episode_metrics.csv \
  --output-dir reproduced/dbbench_factorial_analysis

PYTHONPATH=. .venv/bin/python -m scripts.build_dbbench_results_report \
  --analysis-dir reproduced/dbbench_factorial_analysis \
  --stability DATA_ARCHIVE/results/dbbench_factorial_stability_metrics.csv \
  --figure-dir reproduced/figures \
  --table-dir reproduced/dbbench_factorial_publication_tables
```

The mutation outcomes in the input dataset are the audited deterministic replay scores. Do not use the original deterministic zero mutation scores as model outcomes. The recovery procedure and its residual replay-equivalence assumption are documented in `thesis_protocol/dbbench_full_results.md`.

## OSBench stored-data analysis

```bash
PYTHONPATH=. .venv/bin/python scripts/analyze_osbench_factorial.py \
  --input DATA_ARCHIVE/data/osbench_factorial_episode_metrics.csv \
  --output-dir reproduced/osbench_factorial_analysis
```

The original raw-trajectory extraction and integrity validation are documented
in `docs/osbench_factorial_analysis.md`, but raw trajectories are not publicly
redistributed.

## Repeated-output recurrence from release hashes

The public episode-level stability files retain only exact-match hashes. They
allow the reported recurrence summaries to be recalculated without exposing
the underlying answers or commands:

```bash
PYTHONPATH=. .venv/bin/python scripts/recalculate_released_stability.py \
  --environment dbbench \
  --input DATA_ARCHIVE/data/dbbench_factorial_episode_stability.csv \
  --output reproduced/dbbench_factorial_stability_metrics.csv

PYTHONPATH=. .venv/bin/python scripts/recalculate_released_stability.py \
  --environment osbench \
  --input DATA_ARCHIVE/data/osbench_factorial_episode_stability.csv \
  --output reproduced/osbench_factorial_stability_metrics.csv
```

## Cross-environment ranking sensitivity

After both environment analyses:

```bash
PYTHONPATH=. .venv/bin/python scripts/analyze_cross_environment_rankings.py \
  --db-cell DATA_ARCHIVE/results/dbbench_factorial_analysis/cell_descriptives.csv \
  --db-stability DATA_ARCHIVE/results/dbbench_factorial_stability_metrics.csv \
  --os-cell DATA_ARCHIVE/results/osbench_factorial_analysis/cell_descriptives.csv \
  --os-stability DATA_ARCHIVE/results/osbench_factorial_stability_metrics.csv \
  --output-dir reproduced/cross_environment_rankings
```

The aggregation formula was completed after outcome collection. These outputs reproduce a descriptive sensitivity analysis, not a prespecified confirmatory test.

## GLMM sensitivity analyses

```bash
docker build -f analysis/r-glmm/Dockerfile analysis/r-glmm -t trajectorybench/r-glmm:4.6.1

docker run --rm -v "$PWD:/work" -w /work trajectorybench/r-glmm:4.6.1 \
  Rscript scripts/fit_dbbench_success_glmm.R \
  DATA_ARCHIVE/data/dbbench_factorial_episode_metrics.csv \
  DATA_ARCHIVE/results/dbbench_factorial_analysis/factorial_effects.csv \
  thesis_protocol/dbbench_success_glmm_sensitivity.json

docker run --rm -v "$PWD:/work" -w /work trajectorybench/r-glmm:4.6.1 \
  Rscript scripts/fit_osbench_success_glmm.R \
  DATA_ARCHIVE/data/osbench_factorial_episode_metrics.csv \
  DATA_ARCHIVE/results/osbench_factorial_analysis/factorial_effects.csv \
  thesis_protocol/osbench_success_glmm_sensitivity.json
```

The task-clustered logistic GEE remains primary. The GLMMs are task-conditional sensitivity analyses with different estimands.

## Artifact-to-thesis map

| Thesis result | Authoritative source |
|---|---|
| DBBench cell success and factorial effects | `thesis_protocol/dbbench_full_results.md`; sanitized DBBench episode dataset and archived `results/dbbench_factorial_analysis/` |
| DBBench reviewed figures | `thesis_protocol/figures/dbbench_*` |
| OSBench cell success, factorial effects, recurrence, and prediction | `thesis_protocol/osbench_full_results.md`; sanitized OSBench episode/stability data and archived `results/osbench_factorial_analysis/` |
| GEE/GLMM comparison | `thesis_protocol/*_success_glmm_sensitivity.json` and environment result reports |
| Cross-environment rankings | `thesis_protocol/cross_environment_ranking_results.md` and `results/cross_environment_rankings/` |
| Frozen design and deviations | `thesis_protocol/study_protocol.md` and the two full experiment plans |

## Full experimental rerun

Full reruns require Docker, benchmark services, a compatible proprietary API account, and nontrivial cost. The tracked assignment configurations reference the frozen model snapshot and factor levels. Their base definitions were changed after execution only to replace the ignored credential-bearing import with the tracked, environment-variable-based equivalent; task, model, factor, concurrency, and output definitions were not changed. Supply credentials through the `OPENAI_API_KEY` environment variable; never edit a key into a tracked or local YAML file. Because provider infrastructure and closed-model behavior can change, reruns should be interpreted as replication rather than byte-identical reproduction.

## Known boundaries

- Five executions provide coarse descriptive recurrence summaries.
- DBBench mutation correctness depends on audited deterministic replay.
- OSBench includes documented post-execution checker classification recovery.
- Model outputs may be affected by API drift and benchmark familiarity.
- Raw trajectories are excluded. The release supports derived-data analysis and
  exact-match recurrence verification, but not independent re-extraction of
  trajectory features from the original conversations.
