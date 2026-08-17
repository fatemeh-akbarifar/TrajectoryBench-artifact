# Study Protocol

## Thesis Title

Experimental Multi-Metric Evaluation of Interactive LLM Agents: Efficiency, Repeated-Trajectory Variability, and Ranking Sensitivity

## Research Method

A controlled factorial design is used to evaluate interactive language model
agents on AgentBench tasks. Task-level correctness is analyzed separately from
trajectory-level efficiency, execution-validity, and
repeated-output-variability measures. The study contributes an empirical analysis of
efficiency and repeated-output variability under controlled interventions; it
does not presuppose that these outcomes form a trade-off.

## Research Questions

1. **RQ1:** What efficiency and execution-validity patterns are observed across
   the four agent configurations in DBBench and OSBench?
2. **RQ2:** How do the interaction-round budget and output constraint,
   separately and together, relate to task success, efficiency, and execution
   validity?
3. **RQ3:** How does incorporating efficiency and repeated-output-variability
   measures alter agent configuration rankings compared with success-only
   evaluation?
4. **RQ4:** What patterns recur across repeated final answers and action
   sequences, and how much predictive information do trajectory features add
   beyond configuration alone?

The frozen environment plans retain the broader question wording used when the
experiments were specified. The questions above provide the thesis-level
operational wording: RQ2 maps to the planned factorial outcome comparisons,
while RQ4 maps to the planned repeated-output summaries and task-grouped
predictive comparison. This traceability distinction changes neither the
factors and outcomes nor the analyses recorded in the frozen plans.

## Selected Environments

Before outcome collection, the study selected DBBench and OSBench as
contrasting database and command-line AgentBench environments with executable
evaluation, complete task coverage, retained trajectories, and compatible
factorial interventions. The selection was purposive rather than
representative. Mind2Web was not included in the completed design.

## Model Choice and Freeze

The study compared configurations of one model rather than model families.
GPT-5 was available to the project at design freeze and was retained after the
bounded DBBench compatibility and four-cell smoke evaluations confirmed the
required interaction, parser, and provider-metadata paths. The returned model
snapshot `gpt-5-2025-08-07` was then fixed for DBBench and OSBench. This was a
feasibility and control decision, not a claim that the model was superior or
representative of other interactive agents.

## Unit of Analysis

The unit of analysis is one task episode executed under one agent
configuration.

## Experimental Factors

| Factor | Levels |
|---|---|
| Control Policy (P) | P0: baseline, P1: reduced round budget |
| Output Constraint (C) | C0: baseline output handling, C1: strict format checker with one repair attempt |

## Configuration Matrix

| Config ID | Control Policy | Output Constraint |
|---|---|---|
| P0C0 | Baseline | Baseline |
| P0C1 | Baseline | Strict checker |
| P1C0 | Reduced round budget | Baseline |
| P1C1 | Reduced round budget | Strict checker |

## Frozen DBBench Implementation

| Config ID | Maximum rounds | Output handling | Repair allowance |
|---|---:|---|---:|
| P0C0 | 15 | Legacy DBBench parser | 0 |
| P0C1 | 15 | Strict explicit-action parser | 1 per episode |
| P1C0 | 10 | Legacy DBBench parser | 0 |
| P1C1 | 10 | Strict explicit-action parser | 1 per episode |

C1 accepts one SQL statement in the explicit `Action: Operation` format or a
final response in the explicit `Action: Answer` format. The repair allowance
applies to the entire episode. After one rejected response and one repair
prompt, a second invalid response terminates the episode. Repair attempts,
successful repairs, and rejection reasons are recorded in the episode data.

## Primary Metrics

| Metric | Operational Definition |
|---|---|
| Task success | AgentBench official task-specific correctness score |
| Framework completion | Episode terminates with a submitted final answer |
| Steps | Number of agent-environment interaction turns |
| Tool calls | Number of executable actions sent to environment |
| Token usage | Input + output tokens if available |
| Invalid format | Output does not match expected action format |
| Invalid action | Output format is valid but action cannot be executed |
| Finish reason | complete / invalid format / invalid action / context limit / task limit |
| Entropy | Descriptive variability in the five repeated outputs or action sequences for the same task/configuration |
| Modal consistency | Descriptive agreement with the modal output or action sequence across five repetitions for the same task/configuration |

Entropy and modal consistency are descriptive five-repeat variability
measures. They are not interpreted as reliability, hallucination probability,
semantic uncertainty, or validated general behavioral stability.

## Preflight History

DBBench was used as the first pilot environment, with three to five tasks under
P0C0, P0C1, P1C0, and P1C1. The pilot used two repeated samples per task and
configuration. These pilot and smoke episodes were retained as preflight
evidence and were not included in the full factorial analysis.

## Frozen Full Experiment Design and Completion

For an environment containing \(T\) tasks, the four factorial conditions
produce \(4T\) primary episodes. With \(K\) repeated samples per task and
condition, the design produces \(4TK\) episodes.

The completed design used five repetitions. The 300-task DBBench standard
dataset produced 6,000 analyzed episodes, and the 144-task OSBench standard
dataset produced 2,880, for 8,880 analyzed episodes across the two
environments. Every task--condition group contains five completed observations.

The DBBench hypotheses, estimands, outcome definitions, statistical models,
episode-inclusion rules, and operational stopping conditions are specified in
`thesis_protocol/dbbench_full_experiment_plan.md`.
The environment-specific OSBench design and recovery rules are specified in
`thesis_protocol/osbench_full_experiment_plan.md`. Audited results and
limitations are recorded in `thesis_protocol/dbbench_full_results.md` and
`thesis_protocol/osbench_full_results.md`. The descriptive post-collection
ranking protocol completion and its results are recorded in
`thesis_protocol/cross_environment_ranking_analysis_plan.md` and
`thesis_protocol/cross_environment_ranking_results.md`.

## Implementation and Validation Status

| Component | Status | Evidence |
|---|---|---|
| GPT-5 DBBench compatibility | Validated | Single-episode debug evaluation |
| P0/P1 execution | Validated | Bounded P0/P1 smoke evaluation |
| Provider metadata persistence | Validated | Model and token fields in saved trajectories |
| Cost estimation | Validated | Tested token-based estimator |
| C0/C1 behavior | Validated | Parser and repair-path unit tests |
| Four-cell factorial execution | Validated | Twenty-episode bounded smoke evaluation |
| Full DBBench experiment | Completed and audited | 6,000 analyzed episodes; `thesis_protocol/dbbench_full_results.md` |
| OSBench preflight and transport | Validated | Frozen task audit, debug, smoke, and transport regression tests |
| Full OSBench experiment | Completed and audited | 2,880 analyzed episodes; `thesis_protocol/osbench_full_results.md` |
| Cross-environment ranking | Completed, descriptive | `thesis_protocol/cross_environment_ranking_results.md` |

The DBBench result record is tracked from commit
`0b9c9fe1fab2d5a94340bded1957456572005a89`; the cross-environment ranking
record from `bcdd5394c396541cccacba80502592c42b4446b7`; and the audited OSBench
result record from `fd9fe8099509133b99aa80b91704b34692966314`.
