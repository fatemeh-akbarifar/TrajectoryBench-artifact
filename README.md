# TrajectoryBench

TrajectoryBench is the research artifact for the bachelor thesis *Experimental Multi-Metric Evaluation of Interactive LLM Agents: Efficiency, Repeated-Trajectory Variability, and Ranking Sensitivity*. It extends [AgentBench](https://github.com/THUDM/AgentBench) with a repeated, trajectory-level factorial evaluation of one frozen GPT-5 snapshot in DBBench and OSBench.

The study evaluates four configurations formed by two factors:

- **P0/P1:** the released round budget versus an environment-specific reduced round budget;
- **C0/C1:** legacy output handling versus a strict environment-specific action envelope with one format-repair opportunity.

The completed dataset contains 8,880 analyzed episodes: 300 DBBench tasks and 144 OSBench tasks, four configurations, and five repeated executions. Official correctness, framework completion, resource use, execution events, repeated-output recurrence, and ranking sensitivity are reported separately.

## Relationship to AgentBench

This repository is a derivative of AgentBench v0.2. AgentBench supplies the benchmark framework, environments, task data, and much of the original runtime. TrajectoryBench adds the thesis-specific factorial interventions, integrity checks, recovery provenance, repeated-run extraction, correlated statistical analyses, cross-environment ranking analysis, tests, and technical reports.

Framework code for AgentBench environments outside the completed study, including Mind2Web, remains in the derivative repository for upstream compatibility. The reported TrajectoryBench study evaluated only DBBench and OSBench.

## Study results

- [Study protocol](thesis_protocol/study_protocol.md)
- [DBBench audited results](thesis_protocol/dbbench_full_results.md)
- [OSBench audited results](thesis_protocol/osbench_full_results.md)
- [Cross-environment ranking plan](thesis_protocol/cross_environment_ranking_analysis_plan.md)
- [Cross-environment ranking results](thesis_protocol/cross_environment_ranking_results.md)
- [DBBench experiment plan](thesis_protocol/dbbench_full_experiment_plan.md)
- [OSBench experiment plan](thesis_protocol/osbench_full_experiment_plan.md)

The result reports distinguish prespecified analyses, pre-effect amendments, sensitivity analyses, descriptive post-collection protocol completion, and evaluator-recovery procedures.

## Repository map

| Path | Purpose |
|---|---|
| `configs/` | Agent, task, and frozen factorial assignment definitions |
| `scripts/` | Extraction, validation, recovery, analysis, and reporting programs |
| `tests/` | Regression tests for the thesis-specific pipeline |
| `analysis/r-glmm/` | Pinned R environment for random-intercept logistic sensitivity models |
| `thesis_protocol/` | Frozen plans, audited reports, checksums, and reviewed figures |
| `docs/` | Focused execution and analysis instructions |
| `src/` and `data/` | AgentBench runtime and benchmark components, including study modifications |

## Reproducing the study

There are three distinct reproduction levels:

1. **Stored-data analysis:** regenerate statistical results from the archived, checksum-verified derived datasets. This is the recommended no-API route.
2. **Recurrence verification:** recalculate exact-match recurrence summaries from sanitized outcome and action-sequence hashes in the research archive.
3. **Full experimental rerun:** call the proprietary model API and recreate the benchmark environments. This requires credentials, Docker, time, and API cost and may not reproduce identical responses.

See [REPRODUCING.md](REPRODUCING.md) for the commands, expected checksums, artifact-to-result mapping, and limitations. The Git repository intentionally excludes local credentials and generated `outputs/` and `results/`. The fixed research archive supplies sanitized numerical inputs and recurrence hashes, not raw trajectories or provider response identifiers.

## Installation

The original framework targets Python 3.9. For analysis-only reproduction, create an isolated environment and install both dependency sets:

```bash
python3.9 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-analysis.txt
```

Docker is required for benchmark reruns and the pinned R GLMM sensitivity analyses. Do not place credentials in tracked YAML. The tracked OpenAI configuration reads `OPENAI_API_KEY` from the environment.

## Tests

Focused tests can be run from the repository root, for example:

```bash
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests
```

The audited DBBench and OSBench reports record the narrower validated test sets used at their respective checkpoints.

## Citation

Citation metadata are provided in [CITATION.cff](CITATION.cff). This public reproducibility repository is <https://github.com/fatemeh-akbarifar/TrajectoryBench-artifact>. The fixed version is `v1.0.0`, archived under the published Zenodo DOI [10.5281/zenodo.21971301](https://doi.org/10.5281/zenodo.21971301).

The public `v1.0.0` tag was created from the audited private-development commit `8d42fc5218ece8ba51b290b55c5038313b3c546e`. Both tags have the same Git tree, `151e3878a3cd39980244765027020c4893761375`. This repository starts with a clean public history so that revoked credentials present only in the earlier private history are not redistributed.

When describing the benchmark framework or its original environments, also cite AgentBench:

> Liu, X. et al. (2024). AgentBench: Evaluating LLMs as Agents. *International Conference on Learning Representations (ICLR)*.

## License and attribution

Code in this derivative repository remains under the [Apache License 2.0](LICENSE), consistent with upstream AgentBench. See [NOTICE](NOTICE) for attribution and modification scope and [THIRD_PARTY.md](THIRD_PARTY.md) for the bounded archive policy. Original numerical data and archive documentation are released separately under CC BY 4.0. Benchmark datasets, bundled components, model outputs, and other third-party material may have separate terms; their inclusion must not be inferred from the root code license.

## Security and privacy

Never commit API keys or local credential files. Before a public release, scan the current tree and full Git history for secrets and inspect trajectories for provider identifiers, personal paths, and private data.

## AI-assisted tools disclosure

OpenAI ChatGPT and Codex supported research planning, literature discovery and verification, documentation, testing, debugging, and review. The author selected the research questions and methods, verified cited sources and generated outputs, executed and validated the experiments, interpreted the results, and takes responsibility for the thesis and this repository. AI-generated material was not treated as scientific evidence.

