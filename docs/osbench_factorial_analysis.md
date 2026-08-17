# OSBench factorial analysis

The OSBench analysis consumes the five frozen, independently validated full-run
directories. It does not modify those directories. Episode success is read from
the saved boolean evaluator result and cross-checked against each cell's
`overall.json` accuracy.

## Pipeline

1. `extract_osbench_factorial_metrics.py` validates the repeated task identities,
evaluator types, cell balance, and saved aggregate accuracy before producing
   episode-level metrics. If a task-limit or validation record ended before its
   evaluator ran, the extractor uses the evaluator type observed for that same
   frozen task identity in another cell or repetition and rejects inconsistent
   identity-level mappings.
2. `calculate_osbench_stability_metrics.py` parses OSBench actions under the
   output constraint used by each episode and reports empirical consistency and
   entropy across the five repetitions. These are descriptive repeatability
   measures, not probabilities of hallucination.
3. `analyze_osbench_factorial.py` estimates population-average P, C, and P x C
   effects with task-clustered GEE. Count-family selection uses observed
   dispersion, token outcomes use clustered log1p Gaussian models, and sparse
   binary or repair outcomes remain descriptive. Secondary inferential outcomes
   use Benjamini-Hochberg adjustment.
4. `fit_osbench_success_glmm.R` fits the prespecified task-random-intercept
   logistic sensitivity model in the same pinned R container used for DBBench.
   This checks whether effect direction and substantive interpretation persist
   under a task-conditional formulation; it does not replace the primary GEE.
   Direction comparisons treat estimates with absolute magnitude below
   `1e-6` in both models as jointly negligible so floating-point signs near zero
   are not reported as substantive disagreement.

The primary inferential outcome is official OSBench evaluator success. Repair
attempts are evaluated only within C1 because C0 has no repair path. Repair
success is reported conditional on an attempted repair.

## Reproduction

From the repository root, run:

```bash
.venv/bin/python scripts/extract_osbench_factorial_metrics.py \
  --run-dir outputs/gpt5_osbench_factorial_full_r1 \
  --run-dir outputs/gpt5_osbench_factorial_full_r2 \
  --run-dir outputs/gpt5_osbench_factorial_full_r3 \
  --run-dir outputs/gpt5_osbench_factorial_full_r4 \
  --run-dir outputs/gpt5_osbench_factorial_full_r5 \
  --expected-per-cell 144 \
  --output results/osbench_factorial_episode_metrics.csv \
  --summary results/osbench_factorial_cell_summaries.csv

PYTHONPATH=. .venv/bin/python scripts/calculate_osbench_stability_metrics.py \
  --input results/osbench_factorial_episode_metrics.csv \
  --expected-repetitions 5 \
  --episode-output results/osbench_factorial_episode_stability.csv \
  --group-output results/osbench_factorial_stability_metrics.csv

PYTHONPATH=. .venv/bin/python scripts/analyze_osbench_factorial.py \
  --input results/osbench_factorial_episode_metrics.csv \
  --output-dir results/osbench_factorial_analysis

docker build -t agentbench-r-glmm analysis/r-glmm
docker run --rm \
  -v "$PWD:/work" \
  -w /work \
  agentbench-r-glmm \
  Rscript scripts/fit_osbench_success_glmm.R \
  results/osbench_factorial_episode_metrics.csv \
  results/osbench_factorial_analysis/factorial_effects.csv \
  thesis_protocol/osbench_success_glmm_sensitivity.json
```

Generated artifacts belong under `results/`, which is ignored by Git. Before
reporting the results, confirm 2,880 episode rows, 576 task-condition stability
groups, five repetitions per group, finite inferential estimates, and converged
fitted models.
