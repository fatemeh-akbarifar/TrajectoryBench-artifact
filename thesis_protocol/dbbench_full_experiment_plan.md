# DBBench Full Factorial Experiment Plan

## Objective

This experiment evaluates efficiency, execution validity, repeated-output
variability, and ranking sensitivity alongside DBBench task-level correctness.
A frozen 2 x 2 design is used, defined by control policy (P0/P1) and output
constraint (C0/C1).

## Experimental Design

The standard DBBench dataset contains 300 tasks. Each task is evaluated under
P0C0, P0C1, P1C0, and P1C1, with five independent repetitions per condition.
This design contains 6,000 episodes. The stable identifiers `r1` through `r5`
are used for the repetition files; calendar-based identifiers are excluded
from the tracked study record.

The agent configuration is fixed as follows:

- Provider model: `gpt-5-2025-08-07`
- Temperature: `1`
- Reasoning effort: `minimal`
- Maximum completion tokens per response: `1024`
- Agent concurrency: `1`
- P0 maximum rounds: `15`
- P1 maximum rounds: `10`
- C0 repair allowance: `0`
- C1 repair allowance: `1` per episode

The same 300 task indices are used in every condition and repetition. The
task, condition, and repetition identifiers jointly identify an episode.

## Research Questions and Estimands

The experiment contributes DBBench evidence toward the four study research
questions:

1. **RQ1:** How do efficiency metrics (e.g., interaction length and invalid
   action rate) vary across LLM agent configurations in interactive
   environments?
2. **RQ2:** How are efficiency, execution-validity, and
   repeated-output-variability measures associated with the cost-aware control policy, output
   constraint, and their interaction?
3. **RQ3:** How does incorporating efficiency and repeated-output-variability
   measures alter agent configuration rankings compared with success-only
   evaluation?
4. **RQ4:** What relationships exist between efficiency, execution validity,
   and descriptive repeated-output variability in multi-step decision
   trajectories?

Within DBBench, these questions are operationalized through official success,
interaction length, SQL operations, token use, error and repair measures,
five-repeat output and action-sequence summaries, explanatory success models,
and configuration-ranking comparisons. This is an empirical analysis of
efficiency and repeated-output variability under controlled interventions; a
trade-off is not assumed in advance.

The primary factorial estimands are the average P1 versus P0 contrast, the
average C1 versus C0 contrast, and the P x C interaction. Estimates will be
reported with 95% confidence intervals. Effect sizes and uncertainty will be
reported independently of statistical significance.

## Outcomes

The official AgentBench task-specific correctness score is used as the primary
task outcome. Framework completion is reported separately and is not treated
as task success.

The primary trajectory outcomes are interaction steps, executable SQL
operations, input tokens, output tokens, total tokens, SQL-error occurrence,
format-error occurrence, invalid-action occurrence, task-limit occurrence, and
repair-attempt occurrence. Repair success is evaluated conditionally among
episodes that contain a repair attempt.

Across the five repetitions, sample consistency is defined as the proportion
of normalized final answers equal to the modal answer for a given task and
condition. Entropy will be computed from the empirical distribution of
normalized final answers and, separately, from normalized action sequences.
For query tasks, final-answer normalization safely parses list-like answers,
treats their members as an unordered set, and treats numerically equivalent
single values as equal. Text comparison remains case-sensitive. Surrounding
whitespace is removed from mutation-task results and other unparsed answers.
An episode without a final result is represented by its recorded failure type.

An action sequence contains the executable SQL operations in their observed
order. Whitespace outside quoted SQL strings and identifiers is collapsed, and
an optional terminal semicolon is removed. Case, quoted content, identifiers,
and comments are otherwise preserved to avoid merging actions whose semantic
equivalence cannot be established safely. C1 actions rejected by the strict
format checker are excluded because they were not executed. Shannon entropy is
reported in bits. With five repetitions, modal consistency and entropy are
treated as descriptive repeated-output-variability measures. They are not
estimates of reliability, hallucination probability, semantic uncertainty, or
validated general behavioral stability.

## Statistical Analysis

Official task success will be analyzed using logistic generalized estimating
equations with fixed effects for P, C, and P x C, exchangeable within-task
correlation, and robust task-clustered uncertainty. This population-average
model remains the primary analysis. The originally planned frequentist
random-intercept logistic model will also be fitted as a sensitivity analysis
in a supported R environment, using the same fixed effects, inclusion rules,
and corrected 6,000-episode dataset. It conditions on a task random intercept
and therefore estimates task-specific rather than marginal associations. The
two estimands are not treated as interchangeable, and the primary model will
not be selected or replaced according to statistical significance. This
distinction follows the conditional and marginal model formulations described
by Muff, Held, and Keller (2016; https://doi.org/10.1111/2041-210X.12623).
Count outcomes will use either a Poisson or negative binomial
generalized estimating equation model, selected after
dispersion has been assessed. Token outcomes will be analyzed on a logarithmic
scale if their residual distribution is strongly right-skewed. Task-clustered
logistic generalized estimating equations will be used for binary error
outcomes when the number of observed events is sufficient; otherwise, the
outcome will be reported descriptively and its sparse-event limitation noted.

Because repair attempts are structurally unavailable under C0, their
occurrence is not analyzed with the full four-cell P x C model. The P1 versus
P0 contrast is estimated within C1 using task-clustered logistic generalized
estimating equations. Repair success is reported descriptively and
conditionally among episodes in which a repair was attempted.

The explanatory analysis of task success will compare a condition-only model
with a model that also includes the prespecified trajectory measures.
Incremental explanatory value will be summarized using likelihood-based model
comparison and task-grouped cross-validation. Because trajectory measures can
be consequences of both difficulty and failure, these associations will not
be interpreted as causal effects.

The P, C, and P x C tests for official task success constitute the primary
confirmatory family. The Benjamini--Hochberg procedure, with a false-discovery
rate of 0.05, will be applied to secondary trajectory and error outcomes.
Model assumptions, convergence diagnostics, and sparse-event limitations will
be reported.

## Episode Inclusion and Missing Data

All scheduled episodes will remain in the execution accounting. Task failures,
format failures, invalid actions, context limits, and task limits will not be
removed from the primary dataset. Provider or infrastructure failures that
prevent an episode from starting will be reported separately and rerun using
the same task, condition, and repetition identifier.

Missing token metadata will not be imputed. Analyses involving token measures
will report the number and proportion of episodes with available metadata.
Sensitivity analyses will distinguish agent-originated failures from provider
or infrastructure failures.

During post-experiment validation, the database image was found not to provide
the `MD5()` function used by the original DBBench mutation evaluator. As a
result, the recorded INSERT and UPDATE aggregate scores were deterministically
zero and were not treated as agent outcomes. Mutation episodes are rescored by
replaying the SQL actions accepted during each saved trajectory against the
same frozen initial table and calculating the historical nested-MD5 table
fingerprint in Python. No additional model calls are made, rejected actions are
not replayed, and actions observed after the configured round limit are not
executed. The replayed score, replay action count, and scoring source are
retained in the analysis dataset. Query-task scores remain those produced by
the original evaluator.

## Execution and Stopping Rules

The five repetitions will be executed sequentially. After each repetition,
episode counts, task-index coverage, model identity, configuration labels,
missing metadata, failure types, and observed cost will be verified. Technical
integrity problems will be investigated before the next repetition if the
model snapshot differs from the frozen identifier, an output directory
contains conflicting episode identifiers, or required metadata are
systematically absent.

Stopping decisions will not depend on observed task accuracy or estimated
factor effects. If a repetition is interrupted for a technical reason, it will
be resumed in its existing stable output directory to avoid duplicating
completed episode identifiers.

## Cost and Runtime Projection

The factorial smoke contained 20 episodes, 30,106 input tokens, and 7,366
output tokens. Under rates of USD 1.25 per million uncached input tokens, USD
0.125 per million cached input tokens, and USD 10 per million output tokens,
the observed cost was estimated as USD 0.1113, or USD 0.00556 per episode.

Direct extrapolation gives a point estimate of USD 6.68 for one 1,200-episode
repetition and USD 33.39 for all 6,000 episodes. This extrapolation is not a
cost bound because the five smoke tasks may not represent the trajectory
length distribution of the complete dataset. The applicable rates will be
verified before execution, and the projection will be recalculated after the
first repetition. For cost planning, I set the DBBench budget at USD 90. This
amount is not an automatic stopping rule; cumulative cost will be monitored and
reported without automatically pausing or terminating a running experiment.

At the sequential smoke throughput of approximately 12.7 seconds per episode,
6,000 episodes would require approximately 21.1 hours. This runtime is a
planning estimate rather than a guaranteed duration.

## Reporting Boundary

The full-experiment outputs will be interpreted only after the five planned
repetitions and prespecified validation checks have been completed. Interim
accuracy and factor-effect estimates will not be used to modify the design.
Any deviation from this plan and its rationale will be documented before the
affected analysis is conducted.
