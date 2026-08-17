# OSBench Full Factorial Results

## Analysis status and provenance

This report records the audited five-repetition OSBench factorial analysis used
for thesis RQ1 and RQ2. The analysis dataset is
`results/osbench_factorial_episode_metrics.csv` (2,880 rows excluding the
header; SHA-256
`26262e4043b57bf48620cf40e4ee20c8adc995ede0ba6dd179270467732edce8`).
Generated outputs under `results/` remain ignored; this tracked report is the
stable writing provenance for their reviewed values.

The full runs used `gpt-5-2025-08-07`. They comprise 144 frozen tasks, four
factorial conditions, and five repetitions: 2,880 unique
task--condition--repetition identities, 720 observations per condition, and
five observations in every task--condition group. Every repetition contains
144 unique identities per cell with identical task coverage. Provider model
and token metadata are present for all completed episodes.

The static integrity audit passed with 144 tasks (135 checker evaluated and
nine direct-match evaluated), three container definitions, no errors, and no
warnings. Its frozen definition digest is
`3eee590068c8d8b180338597d76cf01c3f2d335d89529b6b2fa850a884bfc466`.
The frozen full-factorial validator returned `valid=true` for repetitions R1
through R5, with zero unresolved errors.

## Factor definitions

P0 retains the released eight-round interaction limit. P1 uses five rounds,
fixed before OSBench model results by applying the DBBench cost-aware policy's
approximate two-thirds budget rule and rounding to the nearest integer. C0 uses
the released permissive last-recognized-action parser and has no repair path.
C1 requires exactly one explicit `Act: bash`, `Act: finish`, or
`Act: answer(...)` envelope and permits one format-repair attempt per episode.
The strict parser validates the envelope, not the content of an enclosed shell
command.

## Integrity events and analysis inclusion

All scheduled completed identities remain in the analysis, including
incorrect responses, format failures, invalid actions, and task-limit
outcomes. Nineteen historical task-client error records are preserved: 11 in
R1, six in R2, and two in R4. Each is followed by a completed rerun under the
same identity and is not counted as another episode.

Four R1 trajectories for `std-002-environment-00004`, one per factorial cell,
were initially classified as evaluator infrastructure errors when their
checker exited 127. The checker correctly sourced a fresh shell in which the
agent's PATH change was unavailable; these were therefore incorrect agent
outcomes. The original saved histories were deterministically recovered with
`evaluator_recovery=checker_command_unavailable`, `evaluator_status=incorrect`,
and `checker_exit_code=127`. No new model calls were made, and the historical
error records were not rewritten. Other terminating provider or infrastructure
failures were rerun under their original identities and do not enter the
completed dataset as task outcomes.

## Descriptive condition summaries

Intervals in this table are descriptive normal-approximation intervals over
episodes. They do not account for five repeated observations of each task and
must not be substituted for the model-based inferential intervals below.

| Condition | Episodes | Official success (95% descriptive CI) | Framework completion | Mean steps | Mean shell actions | Mean total tokens |
|---|---:|---:|---:|---:|---:|---:|
| P0C0 | 720 | 41.25% (37.65--44.85%) | 96.53% | 5.297 | 3.300 | 2,136.1 |
| P0C1 | 720 | 41.53% (37.93--45.13%) | 99.58% | 5.347 | 3.351 | 2,184.8 |
| P1C0 | 720 | 41.25% (37.65--44.85%) | 93.06% | 5.243 | 3.258 | 2,011.4 |
| P1C1 | 720 | 41.39% (37.79--44.99%) | 98.06% | 5.267 | 3.286 | 2,056.6 |

Framework completion records whether the episode submitted a final response;
it is not official task correctness, parser acceptance, or checker success.

## RQ2: official task success

The primary population-average model is a logistic generalized estimating
equation
`official_success ~ P * C`, clustered by frozen task identity with an
exchangeable working correlation and robust task-clustered uncertainty. The
working correlation was 0.709 and the model converged on all 2,880 episodes.

| Contrast | Odds ratio | 95% inferential CI | Raw p-value |
|---|---:|---:|---:|
| P1 versus P0 | 1.000 | 0.909--1.100 | 1.000 |
| C1 versus C0 | 1.012 | 0.909--1.125 | .833 |
| P x C | 0.994 | 0.864--1.144 | .936 |

The three success contrasts form the primary confirmatory family and are not
included in the secondary Benjamini--Hochberg adjustment. Their intervals
remain compatible with effects in either direction; the analysis does not
establish equivalence.

The prespecified task-conditional sensitivity model is
`official_success ~ P * C + (1 | task_identity)`, fitted with
`lme4::glmer`, a binomial-logit link, adaptive Gauss--Hermite quadrature
(`nAGQ=10`), and the `bobyqa` optimizer. It converged without warnings,
optimizer failure, or singularity. The P, C, and interaction odds ratios were
1.000 (95% CI 0.676--1.480, p=1.000), 1.041 (0.703--1.541, p=.841), and
0.980 (0.563--1.707, p=.944), respectively. All directions agreed with the
primary GEE under the recorded near-zero tolerance, and neither formulation
identified a clear official-success contrast. The marginal and conditional
odds ratios estimate different quantities and are not numerically
interchangeable.

## RQ1: efficiency and execution validity

Interaction steps and shell actions use Poisson GEE with the same P, C, and
P x C fixed effects, task clustering, and exchangeable working correlation.
Their observed dispersion ratios were 0.134 and 0.236, respectively, below the
prespecified 1.5 threshold for selecting negative-binomial GEE. Input, output,
and total tokens use task-clustered Gaussian models on `log1p` because their
raw distributions were strongly right-skewed. Ratio estimates below are
exponentiated link-scale contrasts.

| Outcome | Contrast | Ratio | 95% inferential CI | Raw p | BH-adjusted p |
|---|---|---:|---:|---:|---:|
| Steps | P | 0.990 | 0.978--1.001 | .086 | .286 |
| Steps | C | 1.009 | 0.999--1.020 | .079 | .286 |
| Steps | P x C | 0.995 | 0.982--1.009 | .477 | .667 |
| Shell actions | P | 0.987 | 0.968--1.007 | .197 | .345 |
| Shell actions | C | 1.016 | 0.999--1.033 | .074 | .286 |
| Shell actions | P x C | 0.993 | 0.972--1.015 | .534 | .701 |
| Total tokens | P | 0.976 | 0.947--1.006 | .123 | .309 |
| Total tokens | C | 1.019 | 0.993--1.045 | .156 | .309 |
| Total tokens | P x C | 0.997 | 0.961--1.034 | .864 | 1.000 |

No step, shell-action, or token contrast met the prespecified secondary
false-discovery-rate threshold of .05. Input- and output-token contrasts lead
to the same conclusion; their exact estimates remain in
`results/osbench_factorial_analysis/factorial_effects.csv`.

Framework completion is a separate execution outcome. Its task-clustered
logistic GEE estimated an odds ratio of 0.482 for P (95% CI 0.294--0.790,
raw p=.0038, BH-adjusted p=.0396), 8.597 for C (2.401--30.778,
raw p=.00095, BH-adjusted p=.0199), and 0.438 for P x C
(0.143--1.336, raw p=.147, BH-adjusted p=.309). Thus, P1 was associated with
lower framework completion and C1 with higher framework completion after
multiplicity adjustment. These associations do not imply corresponding
changes in official task success and are not interpreted causally.

Task-limit occurrence had 29 events. Its P contrast was 5.570 (95% CI
1.185--26.173, raw p=.0296) but did not remain below the secondary threshold
after adjustment (p=.207). The C and interaction adjusted p-values were 1.000
and .937. Format errors (16 events) and invalid actions (one event) were too
sparse for the planned task-clustered binary model and remain descriptive.

Repair is structurally unavailable under C0. Three C1 episodes attempted a
repair and two replacement actions passed the parser, a conditional format
recovery rate of 66.7%. The count is too sparse for the planned C1-only P
contrast. Format recovery establishes parser acceptance, not official task
correctness.

## Repeated-output variability and explanatory analysis

The five-repeat summaries are descriptive. Mean final-outcome modal
consistency ranged from 0.249 to 0.257 and mean final-outcome entropy from
2.192 to 2.216 bits across conditions. Mean exact action-sequence consistency
ranged from 0.300 to 0.315 and mean action-sequence entropy from 2.004 to 2.047
bits. These values describe normalized outcomes and exact action sequences in
this experiment; they are not estimates of reliability, hallucination
probability, semantic uncertainty, or general behavioral stability.

A task-fixed explanatory likelihood comparison favored adding the
prespecified trajectory variables to the condition-only success model
(likelihood-ratio statistic 85.89, 8 degrees of freedom, p=3.17e-15). In five
task-grouped folds, the trajectory-augmented model increased mean ROC AUC from
0.645 to 0.691 and reduced mean log loss from 0.641 to 0.619; log loss improved
in every fold. These are non-causal explanatory and predictive associations.

## Interpretation across RQ1 and RQ2

OSBench provides no clear population-average association between P, C, or
their interaction and official task success. It also provides no secondary
adjusted evidence of changes in step count, shell-action count, token use, or
task-limit occurrence. Framework completion differs from this pattern: P1 is
associated with lower completion and C1 with higher completion. Completion and
official success must therefore remain separate in reporting. The results are
environment-specific and are not pooled with DBBench factorial effects.

## Analysis amendments and limitations

The primary success analysis uses population-average task-clustered GEE after
the planned Python frequentist random-intercept implementation was found
unsupported. This amendment was recorded before factorial effects were
inspected. The originally planned random-intercept model was subsequently
recovered as the task-conditional sensitivity analysis described above. The
two estimands remain distinct.

The checker-exit-126/127 classification was narrowed after R1 because those
codes can reflect an agent-created unavailable command rather than checker
infrastructure failure. Recovery was deterministic and retained provenance,
but it is still a post-execution evaluator-classification correction. Historical
technical failures and same-identity reruns also mean the completed dataset
does not represent the frequency or cost of infrastructure interruptions.

Only four factorial configurations of one frozen model snapshot and 144
OSBench tasks are evaluated. Sparse errors and repairs limit precision, and
five repetitions provide only coarse descriptive variability summaries.
Differences from DBBench may reflect tasks, interfaces, evaluators, or
environment implementation and are not tests of equality between environment
effect sizes.

## Reviewed artifacts and reproducibility checkpoint

The reviewed generated sources are:

- `results/osbench_factorial_episode_metrics.csv`
- `results/osbench_factorial_cell_summaries.csv`
- `results/osbench_factorial_stability_metrics.csv`
- `results/osbench_factorial_analysis/cell_descriptives.csv`
- `results/osbench_factorial_analysis/factorial_effects.csv`
- `results/osbench_factorial_analysis/model_diagnostics.json`
- `results/osbench_factorial_analysis/explanatory_cross_validation.json`
- `results/osbench_factorial_analysis/explanatory_likelihood_comparison.json`
- `thesis_protocol/osbench_success_glmm_sensitivity.json`

No OSBench publication figure or LaTeX table has yet been generated or
reviewed. Thesis prose must therefore cite this tracked report and must not
claim that an OSBench figure has passed visual review. The compact Markdown
tables above are the reviewed tabular result record for the writing handoff.

The report checkpoint passed 73 relevant regression tests: 48 analysis and
validation script tests plus 25 OS action-parser and evaluator tests. The
static integrity audit and all five frozen repetition validators also passed
at this checkpoint.

The source snapshot reviewed for this report is
`bcdd5394c396541cccacba80502592c42b4446b7` on
`experiment/osbench-factorial`. The reproducible OSBench factorial analysis was
introduced by `827cc1eaf144b9f0e002692813f62354a6404c89`; the GLMM sensitivity
record by `7a6d9de33a5688ccf19b6877e4187fc24a3e608f`; and the cross-environment
ranking package by `bcdd5394c396541cccacba80502592c42b4446b7`. The commit that
adds this report must be recorded at the Git checkpoint; generated `results/`
files must not be staged.
