# OSBench Full Factorial Experiment Plan

## Scope

OSBench is the second primary environment in the study. Its standard dataset
contains 144 tasks evaluated inside isolated Docker containers. The planned
factorial design retains the four P0C0, P0C1, P1C0, and P1C1 conditions and
five repetitions per task and condition, producing 2,880 episodes after the
implementation and smoke-test gates have passed.

The OSBench factors will be frozen only after their environment-specific
semantics have been implemented and validated. The DBBench parser and SQL
repair behavior will not be transferred mechanically to shell interactions.

## Evaluator Integrity Gate

No paid model episode will be used as experimental evidence until the OSBench
execution and evaluation path has passed the following checks:

1. Every standard task definition can be loaded.
2. Every referenced initialization, start, example, and checker script exists.
3. Every locally configured image has a corresponding Dockerfile.
4. Known-correct evaluator inputs pass and known-incorrect inputs fail.
5. Checker exceptions and infrastructure exit codes are recorded as task
   errors rather than incorrect agent outcomes.
6. Representative tasks produce the same evaluator outcome in independently
   created clean containers.
7. The Docker image identifiers, task-definition checksum, AgentBench commit,
   host architecture, and model snapshot are recorded before execution.

The static task definition currently comprises 135 checker-based tasks and
nine direct or regular-expression match tasks. Static validation is necessary
but does not establish that the checkers are semantically correct; executable
positive and negative tests remain required.

The initial static audit identified one inherited schema defect in category 5:
a checker list had also been stored in the task's `create` field, although the
runtime requires `create` to be an object. The duplicate malformed field was
removed without changing the task description or its `evaluation.check`
definition. This correction is retained in version control and is included in
the frozen task-definition checksum.

The audit also identified that the released task data select local images with
the `create.local` field, while the inherited runtime considered only
`create.image`. Image resolution was aligned with the released schema so that
the task requesting the `packages` image is no longer executed in the default
image. The three local Dockerfiles were then pinned to the Ubuntu base-image
digest used for the executable validation rather than the mutable `ubuntu`
tag.

## Frozen Container Baseline

The executable preflight used Ubuntu base-image digest
`sha256:c4a8d5503dfb2a3eb8ab5f807da5bc69a85730fb49b5cfca2330194ebcc41c7b`.
The resulting local OSBench image identities were:

| Image | Local image digest |
|---|---|
| `local-os/default` | `sha256:7abfe6fd55c4df0baabc485cb93a39cd95764b05e5fbdcaf2754d123b37a0626` |
| `local-os/packages` | `sha256:9892cfa915274ceebc2e8cd8ed038a12c9e83cef50d14dd6a5c1cc60bfc80595` |
| `local-os/ubuntu` | `sha256:c052a7e0ba023c201be35502397c85b6a2bbbaefc1922a33282cbbd32bca770d` |

Two checker chains were executed in independently created containers without
language-model calls. A stock-log task using the default image and an npm task
using the packages image both rejected a deliberately incorrect answer and
accepted the answer produced by the task's reference example. These checks
establish executable evidence for the two images selected by the standard task
definitions; broader task-family validation is still required before the paid
factorial smoke evaluation.

## Factor Definitions

P0 retains the released OSBench limit of eight interaction rounds. P1 permits
five rounds. The P1 value was fixed before OSBench model results were observed
by applying the DBBench cost-aware policy's approximate two-thirds budget to
the eight-round OSBench baseline and rounding to the nearest integer. The limit
will not be changed in response to debug, smoke, or full-experiment accuracy.

C0 will retain the benchmark's baseline output handling. C1 will require an
explicit OSBench action format and allow one format-repair attempt per episode.
The C1 parser will validate the action envelope without rejecting valid shell
commands on the basis of command content. Parser rejection reasons, repair
attempts, and successful repairs will be retained in the episode metadata.

The strict envelope accepts exactly one `Act: bash`, `Act: finish`, or
`Act: answer(...)` action. A Bash action requires one fenced `bash` block, but
the command inside that block is not restricted by the parser. An optional
`Think:` line may precede the action. C0 retains the released parser's
permissive last-recognized-action behavior and does not receive repair prompts.

Each accepted Bash block is encoded and evaluated as one line in the existing
interactive shell. This preserves shell state across agent turns while ensuring
that embedded newlines do not produce intermediate prompts that split one
agent action into several partially observed commands. The original command is
retained in the trajectory; the encoding is an execution-transport detail.

The first two-episode debug run exposed the intermediate-prompt transport
problem and is retained only as preflight evidence. It is not used as study
data. The corrected two-episode debug run uses the stable output directory
`outputs/gpt5_osbench_debug_atomic`; the earlier directory is preserved for
audit rather than overwritten.

The first 24-episode factorial smoke attempt completed 21 episodes and exposed
two additional preflight conditions. On one command-creation task, an accepted
action enabled Bash `errexit` before an unavailable command; this terminated
the persistent shell and caused two Docker-stream errors in different
constraint conditions. The action wrapper was therefore guarded so the
transport-control `errexit` and `nounset` options cannot terminate the shell;
the expected early-stop behavior of `errexit` is handled by the wrapper, while
directory and environment changes remain stateful across turns. Docker stream frames are
also read to their declared lengths so a genuinely closed stream is reported
as an explicit transport error rather than a binary-unpack exception. A third
episode ended before producing an action because the provider used the entire
completion allowance for internal reasoning. These three cases are preflight
failures rather than incorrect task outcomes and must be rerun under their
original smoke identifiers after the transport correction is validated.

## Validation Sequence

The implementation will be validated in the following order:

1. Static audit of all standard tasks and dependencies.
2. Unit tests for action parsing and evaluator-status classification.
3. Executable evaluator tests without language-model calls.
4. One GPT-5 debug episode in each output-constraint condition.
5. A balanced factorial smoke evaluation covering multiple OSBench task and
   evaluator families.
6. Episode-metric extraction, run-integrity validation, and observed cost and
   runtime estimation.
7. Freeze of the final P1 budget, model snapshot, container identities,
   analysis plan, and repetition commands.

The debug evaluation uses one original permission/direct-match task under C0
and C1, producing two episodes. The factorial smoke evaluation selects six
tasks directly from the standard source files without copying or modifying
their definitions. The selection covers checker and direct-match evaluation,
the default and packages images, observation tasks, permission and state
modification, command creation, and a generated file-system task. Running the
six tasks under all four conditions produces 24 smoke episodes.

After the three preflight failures described above were rerun under their
original identifiers, the combined smoke dataset contained 24 unique completed
episodes, six in each factorial condition and four observations for every
selected task. Thirteen episodes passed their official evaluator and eleven
were evaluated as incorrect. No completed record had an evaluator error or
missing model/token metadata; all recorded provider responses used
`gpt-5-2025-08-07`. The three retained task-client error records are historical
provenance for the subsequently completed identities and are not counted as
additional episodes.

At the recorded rates of USD 1.25 per million uncached input tokens, USD 0.125
per million cached input tokens, and USD 10 per million output tokens, the 24
completed smoke episodes cost an estimated USD 0.194. Direct scaling of their
mean completed-episode cost projects USD 23.30 for 2,880 completed episodes.
This point estimate excludes the cost of provider calls that fail before a
completed trajectory is saved and is therefore used for planning rather than
as a guaranteed total. The previously selected USD 90 study budget remains a
monitoring threshold and does not trigger an automatic pause.

The first full-repetition attempt was stopped after another transport edge
case appeared during preflight execution. An agent action used the shell
`exit` builtin after detecting missing positional inputs, which terminated the
persistent control shell and produced an explicit closed-stream error. The
transport wrapper was extended so `exit` ends only the current agent action,
retains its requested status for wrapper handling, and leaves the stateful
shell available for the next turn. The partial repetition directory is
preserved and will be resumed after automated and executable regression checks;
completed episode identities will not be run again.

The completed first-repetition pass also exposed an overly broad checker-error
classification. One PATH-persistence task invokes `echo-love` after sourcing
`~/.bashrc`; when an agent changed only its current shell PATH, the checker
correctly encountered command-not-found exit 127. That exit describes an
incorrect agent outcome rather than broken checker infrastructure. Checker
exits 126 and 127 are therefore classified as incorrect, while other unexpected
nonzero exits remain infrastructure errors. The four original affected
trajectories are recovered from their saved task-client records with explicit
`checker_command_unavailable` provenance and no additional model calls. The
historical error records remain unchanged for auditability.

During the second repetition, one provider response used the full 1,024-token
completion allowance for internal reasoning and returned no agent action. This
failure occurred before an action was sent to the environment. Empty responses
with `finish_reason='length'` are therefore retried within the existing
three-attempt HTTP-client policy. The model snapshot, reasoning setting, and
completion allowance remain unchanged. If all three calls return empty
length-limited responses, the episode remains an explicit `AGENT_FAILED`
record rather than being converted into a task outcome. The interrupted
repetition is resumed in its stable output directory, where completed episode
identities are skipped and unresolved identities are rerun.

Later in the resumed second repetition, a shell command produced no output for
more than the Docker socket's five-second polling interval. The transport had
treated that temporary silence as command completion although the command was
still running. A subsequent action could consequently be sent to a busy shell,
causing stream desynchronization and an `INTERACT_FAILED` record. The transport
now continues polling until the existing 30-second command limit. At that
limit, the running command is interrupted and the shell prompt is recovered
before another action can be accepted. The failed identity is rerun in the
same stable repetition directory; completed identities and the frozen
experimental parameters remain unchanged.

A later recursive filesystem command reached the same 30-second command limit
but did not return the prompt after the first interrupt within the original
ten-second recovery window. The command allowance remains 30 seconds. During
prompt recovery, the transport now repeats the interrupt after each silent
socket interval for at most 30 seconds. This bounded recovery accommodates
commands that react slowly while blocked in filesystem operations without
allowing further actions to enter a busy shell. Failure to recover the prompt
still produces an explicit infrastructure-error record, which is excluded
from completed outcomes and rerun under the same frozen identity.

## Full Execution and Integrity Checks

Five repetitions will be executed sequentially after the validation sequence
has passed. Each repetition will contain 576 episodes: 144 tasks under four
factorial conditions. Repetition outputs will use stable identifiers rather
than dates.

The frozen assignment files are
`configs/assignments/gpt5_osbench_factorial_full_r1.yaml` through
`gpt5_osbench_factorial_full_r5.yaml`. A single repetition is started at a
time. The four task workers remain available, while agent concurrency is fixed
at one to preserve the experimental execution setting. The combined initial
smoke and targeted-rerun wall time corresponds to an approximate 30-hour point
projection for all 2,880 episodes, or about six hours per repetition. This is
only an operational estimate because task mix, provider latency, retries, and
host load can change the realized duration.

After each repetition, task coverage, unique episode identifiers, configuration
labels, model identity, container identity, token metadata, evaluator errors,
provider failures, and observed cost will be checked. Provider or infrastructure
failures that prevent valid evaluation will be reported separately and may be
rerun under the same task, condition, and repetition identifier. Incorrect
agent outcomes will not be rerun.

## Analysis Boundary

OSBench task success will use the benchmark's task-specific checker or match
result after evaluator integrity has been established. Trajectory efficiency,
execution-validity, repair, and repeated-output-variability measures will be
calculated separately from task success. Entropy and modal consistency will be
treated as descriptive summaries of five repetitions, not as reliability,
hallucination probability, semantic uncertainty, or validated general
behavioral stability. The factorial and repeated-measures analysis will follow
the prespecified DBBench principles, with OS-specific outcome forms and model
diagnostics recorded before the full results are interpreted.

The OSBench analysis contributes evidence toward the four study research
questions concerning configuration-level efficiency (RQ1), associations with
the P and C interventions (RQ2), ranking sensitivity relative to success-only
evaluation (RQ3), and relationships among efficiency, execution validity, and
descriptive repeated-output variability (RQ4). It is framed as an empirical
analysis of efficiency and repeated-output variability under controlled
interventions; an efficiency--stability trade-off is not assumed.

Cross-environment comparisons will distinguish replication of a directional
pattern from equality of effect sizes. A result observed in only one
environment will not be generalized to interactive agent environments as a
whole.
