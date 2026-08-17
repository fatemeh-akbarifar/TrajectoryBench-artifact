# Cross-Environment Configuration-Ranking Analysis Plan

## Status and purpose

This document completes the operational definition of the RQ3 ranking
analysis. The study protocol prespecified comparison of success-only and
multi-metric rankings, but it did not specify a composite formula or metric
weights. This plan was written after the DBBench and OSBench outcomes had been
collected and their descriptive summaries had been inspected. It is therefore
not presented as a preregistered or fully prespecified analysis.

The analysis will not select a preferred weighting from the observed results.
Instead, it will report a fixed sensitivity grid of transparent, direction-aware
rank aggregations. No multi-metric ordering will be described as intrinsically
more correct than the success-only ordering.

## Configurations and environments

The ranked alternatives are the four frozen configurations P0C0, P0C1, P1C0,
and P1C1. DBBench and OSBench are first ranked separately. A cross-environment
ordering then gives the two environments equal weight, regardless of their
different numbers of tasks or episodes.

## Metric directions and domains

Only measures with the same operational role in both environments enter the
cross-environment ranking.

| Domain | Measure | Preferred direction |
|---|---|---|
| Success | Official task success | Higher |
| Efficiency | Interaction steps | Lower |
| Efficiency | Executable actions | Lower |
| Efficiency | Total tokens | Lower |
| Execution validity | Format-error occurrence | Lower |
| Execution validity | Invalid-action occurrence | Lower |
| Execution validity | Task-limit occurrence | Lower |
| Repeated-output variability | Final-outcome modal consistency | Higher |
| Repeated-output variability | Action-sequence modal consistency | Higher |

DBBench SQL operations and OSBench shell actions are treated as the common
executable-action measure. Environment-specific outcomes, including DBBench
SQL errors and OSBench framework completion, are excluded from the common
ranking. Repair success is excluded because it is conditional on a repair
attempt and repair is structurally unavailable under C0. Entropy is excluded
from the ranking because it is mathematically paired with modal consistency in
this five-repeat design and including both would duplicate the same variability
domain. It remains available for descriptive analysis.

## Rank transformation

For every environment and metric, the four condition means are converted to
average ranks, with rank 1 assigned to the preferred value and exact ties given
their average rank. Ranks are converted to utilities on `[0, 1]` as
`(4 - rank) / 3`. This transformation prevents measurement scale from acting as
an implicit weight.

## Frozen sensitivity grid

Four schemes will be reported:

1. `success_only`: official success alone.
2. `core_domain_balanced`: equal weight for success, efficiency, and
   repeated-output variability; metrics receive equal weight within a domain.
3. `core_metric_balanced`: equal weight for the six core metrics (success,
   three efficiency measures, and two consistency measures).
4. `broad_domain_balanced`: equal weight for success, efficiency, execution
   validity, and repeated-output variability; metrics receive equal weight
   within a domain.

The domain-balanced and metric-balanced core schemes expose the sensitivity to
whether domains or individual measures receive equal weight. The broad scheme
exposes sensitivity to adding execution-validity outcomes. These schemes form
a sensitivity grid; none is designated post hoc as the primary multi-metric
score.

For each scheme, environment-specific utilities are averaged across the two
environments and reranked to form the cross-environment ordering. The report
will include configuration ranks, utility values, changes from success-only
rank, and rank correlations with the success-only ordering. With only four
configurations, rank correlations are descriptive.

## Interpretation boundary

The analysis describes how rankings change under the fixed schemes above. It
does not estimate stakeholder preferences, establish a universally optimal
configuration, or convert descriptive five-repeat variability into a measure
of reliability. If rankings differ across reasonable schemes, that
sensitivity is itself the RQ3 result.
