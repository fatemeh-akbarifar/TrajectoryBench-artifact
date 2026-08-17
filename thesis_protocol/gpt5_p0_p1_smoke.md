# GPT-5 DBBench P0/P1 Smoke

## Purpose

This smoke evaluation assessed GPT-5 compatibility and the DBBench P0/P1 task
variants before full-scale execution. The sample was used for engineering
validation rather than inference about policy effects.

## Run Identity

- Run label: `gpt5-dbbench-p0-p1-smoke-v1`
- Branch: `experiment/gpt5-p0-p1`
- Code commit before smoke configuration changes: `859be18`
- Model alias: `gpt-5` (exact provider snapshot was not persisted)
- Temperature: `1`
- Reasoning effort: `minimal`
- Maximum completion tokens: `1024`
- Dataset: five unique tasks copied from `data/dbbench/standard.jsonl`
- Smoke dataset SHA-256:
  `0445b05043bb003fa29bd091b30650506bb36030c383c8d1b03c4831a559a9ea`
- P0 maximum rounds: `15`
- P1 maximum rounds: `10`
- Agent concurrency: `1`

Raw outputs were retained locally under the ignored `outputs/` directory and
excluded from version control.

## Results

| Metric | P0 | P1 |
|---|---:|---:|
| Episodes | 5 | 5 |
| Framework completion rate | 1.0 | 1.0 |
| Official SELECT accuracy | 0.4 | 0.4 |
| Average steps | 4.0 | 3.4 |
| Average history length | 8.0 | 6.8 |
| Average SQL operations | 2.0 | 1.4 |
| SQL error rate | 0.0 | 0.0 |
| Format error rate | 0.0 | 0.0 |
| Invalid action rate | 0.0 | 0.0 |
| Context-limit rate | 0.0 | 0.0 |
| Task-limit rate | 0.0 | 0.0 |

All ten episodes produced a final answer and at least one SQL operation. One
task required six SQL operations under P0 and two under P1. Both variants
returned `16` for a task whose benchmark reference was `2`. This case
illustrates the distinction between framework completion and task-specific
correctness.

## Gate Decision

The results supported the use of GPT-5 and the P0/P1 variants in subsequent
bounded DBBench evaluations. Full-scale execution was deferred because
provider metadata, cost estimation, and the C0/C1 factor had not yet been
validated.

The later engineering validations are documented in the four-cell factorial
smoke record. This file is retained as the historical record of the earlier
P0/P1 compatibility evaluation.
