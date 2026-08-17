# Cross-Environment Configuration-Ranking Results

## Analysis status

The analysis follows the fixed sensitivity grid in
`cross_environment_ranking_analysis_plan.md`. Because the original protocol did
not specify composite weights or a rank-aggregation formula, this is a
descriptive protocol-completion analysis rather than a fully prespecified
confirmatory test.

## Cross-environment rankings

DBBench and OSBench received equal weight after condition means were converted
to direction-aware within-environment ranks.

| Scheme | Rank 1 | Rank 2 | Rank 3 | Rank 4 | Spearman correlation with success-only |
|---|---|---|---|---|---:|
| Success only | P1C1 | P1C0 | P0C1 | P0C0 | 1.00 |
| Core, domain balanced | P1C0 | P1C1 | P0C0 | P0C1 | 0.60 |
| Core, metric balanced | P1C0 | P0C0 | P1C1 | P0C1 | 0.00 |
| Broad, domain balanced | P1C1 | P1C0 | P0C0 | P0C1 | 0.80 |

The success-only ordering was not invariant to the inclusion of efficiency and
repeated-output consistency. Under both core schemes, P1C0 replaced P1C1 at
rank 1. Under equal metric weighting, P1C1 moved from rank 1 to rank 3 and the
rank correlation with success-only was zero. When execution-validity outcomes
were added as an equally weighted fourth domain, P1C1 returned to rank 1, while
P0C1 remained last in every multi-metric scheme.

## Interpretation

These results support the RQ3 claim that configuration rankings can change
when evaluation includes trajectory measures rather than success alone. They
also show that the resulting ordering depends on the aggregation rule and
metric set: there is no single scheme-invariant best configuration. The
rankings therefore describe sensitivity to explicit evaluation priorities,
not a universal performance hierarchy. With four alternatives, the reported
rank correlations are descriptive and no inferential claim is attached to
them.

The repeated-output measures remain five-repeat modal-consistency summaries.
Their use in this sensitivity analysis does not make them validated reliability
measures.
