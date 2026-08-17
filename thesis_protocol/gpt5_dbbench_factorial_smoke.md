# GPT-5 DBBench Factorial Smoke

## Purpose

This smoke evaluation assessed the complete P0/P1 x C0/C1 DBBench execution
and measurement path before full-scale execution. The five-task sample was
used for engineering validation rather than inference about factor effects.

## Run Identity

- Run label: `gpt5-dbbench-factorial-smoke-v1`
- Branch: `feature/factorial-framework`
- C0/C1 implementation commit: `b866091`
- Factorial assignment commit: `1ae96b2`
- Model alias: `gpt-5`
- Returned provider model: `gpt-5-2025-08-07`
- Temperature: `1`
- Reasoning effort: `minimal`
- Maximum completion tokens: `1024`
- Dataset: five unique tasks copied from `data/dbbench/standard.jsonl`
- Smoke dataset SHA-256:
  `0445b05043bb003fa29bd091b30650506bb36030c383c8d1b03c4831a559a9ea`
- P0 maximum rounds: `15`
- P1 maximum rounds: `10`
- C0 repair allowance: `0`
- C1 repair allowance: `1` per episode
- Agent concurrency: `1`

Raw outputs were retained locally under the ignored `outputs/` directory and
excluded from version control. Credentials, local output paths, and
calendar-based run identifiers were omitted from the tracked record.

## Results

| Metric | P0C0 | P0C1 | P1C0 | P1C1 |
|---|---:|---:|---:|---:|
| Episodes | 5 | 5 | 5 | 5 |
| Framework completion rate | 1.0 | 1.0 | 1.0 | 1.0 |
| Official SELECT accuracy | 0.2 | 0.4 | 0.4 | 0.4 |
| Average steps | 3.8 | 3.8 | 3.8 | 3.8 |
| Average history length | 7.6 | 7.6 | 7.6 | 7.6 |
| Average SQL operations | 1.8 | 1.8 | 1.8 | 1.8 |
| SQL error rate | 0.0 | 0.2 | 0.2 | 0.0 |
| Format error rate | 0.0 | 0.0 | 0.0 | 0.0 |
| Invalid action rate | 0.0 | 0.0 | 0.0 | 0.0 |
| Task-limit rate | 0.0 | 0.0 | 0.0 | 0.0 |
| Repair attempt rate | 0.0 | 0.0 | 0.0 | 0.0 |
| Input tokens | 7,247 | 7,529 | 7,302 | 8,028 |
| Output tokens | 1,765 | 1,818 | 1,751 | 2,032 |
| Total tokens | 9,012 | 9,347 | 9,053 | 10,060 |

The same five task indices were used in all four cells. All provider responses
had the finish reason `stop`, and every episode included the provider model and
token usage metadata. No repair attempts were observed in the C1 episodes, so
the smoke does not provide an estimate of repair frequency or repair success.
The repair and repair-exhaustion paths were validated separately with
automated tests.

The cost of the 20 observed episodes was estimated as USD 0.1113 under the
stated rate assumptions: USD 1.25 per million uncached input tokens, USD 0.125
per million cached input tokens, and USD 10 per million output tokens. These
rates are inputs to the estimator rather than properties of the stored
trajectories and will be verified again before the full experiment.

## Interpretation Boundary

The lower P0C0 accuracy corresponds to one additional incorrect answer in a
five-task cell. Given the sample size and absence of repeated samples, this
difference is not interpreted as evidence of a control-policy effect, an
output-constraint effect, or their interaction. The result is reported only as
part of the engineering validation.

## Gate Decision

The smoke results support the technical readiness of the DBBench factorial
framework for bounded execution. Full-scale execution will begin after the
applicable API rates, cost projection, and analysis plan have been verified and
documented.
