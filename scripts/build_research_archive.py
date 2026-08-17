#!/usr/bin/env python3
"""Build a sanitized, analysis-ready TrajectoryBench data archive."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path


TEXT_AND_PROVIDER_FIELDS = {
    "source_file",
    "timestamp",
    "result_answer",
    "result_error",
    "repair_rejection_reasons",
    "provider_response_ids",
    "final_agent_message",
    "mutation_replay_answer",
    "normalized_final_answer",
    "normalized_final_outcome",
    "normalized_action_sequence",
}

COPY_PATHS = (
    "results/dbbench_factorial_cell_summaries.csv",
    "results/dbbench_factorial_stability_metrics.csv",
    "results/dbbench_factorial_analysis/cell_descriptives.csv",
    "results/dbbench_factorial_analysis/factorial_effects.csv",
    "results/dbbench_factorial_analysis/model_diagnostics.json",
    "results/dbbench_factorial_analysis/explanatory_cross_validation.json",
    "results/dbbench_factorial_analysis/explanatory_likelihood_comparison.json",
    "results/dbbench_factorial_publication_tables/primary_success_effects.csv",
    "results/dbbench_factorial_publication_tables/secondary_effects.csv",
    "results/dbbench_factorial_publication_tables/stability_by_condition.csv",
    "results/dbbench_factorial_publication_tables/success_by_condition.csv",
    "results/osbench_factorial_cell_summaries.csv",
    "results/osbench_factorial_stability_metrics.csv",
    "results/osbench_factorial_analysis/cell_descriptives.csv",
    "results/osbench_factorial_analysis/factorial_effects.csv",
    "results/osbench_factorial_analysis/model_diagnostics.json",
    "results/osbench_factorial_analysis/explanatory_cross_validation.json",
    "results/osbench_factorial_analysis/explanatory_likelihood_comparison.json",
    "results/cross_environment_rankings/rankings.csv",
    "results/cross_environment_rankings/summary.json",
    "thesis_protocol/dbbench_success_glmm_sensitivity.json",
    "thesis_protocol/osbench_success_glmm_sensitivity.json",
)

SANITIZED_EPISODE_FILES = (
    (
        "results/dbbench_factorial_rescored_episode_metrics.csv",
        "data/dbbench_factorial_episode_metrics.csv",
        None,
    ),
    (
        "results/osbench_factorial_episode_metrics.csv",
        "data/osbench_factorial_episode_metrics.csv",
        None,
    ),
    (
        "results/dbbench_factorial_episode_stability.csv",
        "data/dbbench_factorial_episode_stability.csv",
        "normalized_final_answer",
    ),
    (
        "results/osbench_factorial_episode_stability.csv",
        "data/osbench_factorial_episode_stability.csv",
        "normalized_final_outcome",
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sanitized_csv(source: Path, destination: Path, final_field: str | None) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open(newline="", encoding="utf-8") as input_stream:
        reader = csv.DictReader(input_stream)
        if reader.fieldnames is None:
            raise ValueError(f"missing CSV header: {source}")
        retained = [name for name in reader.fieldnames if name not in TEXT_AND_PROVIDER_FIELDS]
        if final_field:
            if final_field not in reader.fieldnames:
                raise ValueError(f"missing recurrence field {final_field}: {source}")
            retained.append("final_outcome_sha256")
        with destination.open("w", newline="", encoding="utf-8") as output_stream:
            writer = csv.DictWriter(output_stream, fieldnames=retained)
            writer.writeheader()
            rows = 0
            for row in reader:
                clean = {name: row.get(name, "") for name in retained}
                if final_field:
                    clean["final_outcome_sha256"] = hashlib.sha256(
                        row[final_field].encode("utf-8")
                    ).hexdigest()
                writer.writerow(clean)
                rows += 1
    return rows


def copy_required(source_root: Path, destination_root: Path, relative: str) -> None:
    source = source_root / relative
    if not source.is_file():
        raise FileNotFoundError(source)
    destination = destination_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def write_archive_readme(output: Path, source_checksums: dict[str, str]) -> None:
    text = f"""# TrajectoryBench research data archive

This package contains the analysis-ready numerical data and derived outputs for
the TrajectoryBench thesis study. It excludes raw trajectories, model-generated
free text, provider response identifiers, credentials, timestamps, and local
source paths.

The authoritative private analysis inputs had these audited checksums before
sanitization:

- DBBench: `{source_checksums['dbbench']}`
- OSBench: `{source_checksums['osbench']}`

Sanitization removed text and provider-only fields but did not change the
outcomes, experimental factors, task identifiers, resource measurements, or
statistical inputs. In the episode-level recurrence files, normalized final
outcomes are represented by SHA-256 values and action sequences by the hashes
already produced by the audited pipeline. This preserves exact-match grouping
without redistributing the underlying text.

`MANIFEST.csv` records every included file, its byte size, checksum, source,
and transformation. `SHA256SUMS` supports independent integrity checking.

The original code, frozen configurations, technical reports, and reproduction
commands belong to the TrajectoryBench software release. Numerical data and
original archive documentation are licensed under CC BY 4.0 as described in
`DATA_LICENSE.txt`. No license is granted here for excluded benchmark content,
raw model text, or other third-party material.
"""
    (output / "README.md").write_text(text, encoding="utf-8")


def build_archive(repo_root: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    output.mkdir(parents=True)

    source_checksums = {
        "dbbench": sha256_file(repo_root / SANITIZED_EPISODE_FILES[0][0]),
        "osbench": sha256_file(repo_root / SANITIZED_EPISODE_FILES[1][0]),
    }
    manifest_rows: list[dict[str, str | int]] = []

    for source_relative, destination_relative, final_field in SANITIZED_EPISODE_FILES:
        source = repo_root / source_relative
        destination = output / destination_relative
        if not source.is_file():
            raise FileNotFoundError(source)
        rows = sanitized_csv(source, destination, final_field)
        manifest_rows.append(
            {
                "path": destination_relative,
                "bytes": destination.stat().st_size,
                "sha256": sha256_file(destination),
                "source": source_relative,
                "transformation": f"sanitized CSV; {rows} data rows",
            }
        )

    for relative in COPY_PATHS:
        copy_required(repo_root, output, relative)
        destination = output / relative
        manifest_rows.append(
            {
                "path": relative,
                "bytes": destination.stat().st_size,
                "sha256": sha256_file(destination),
                "source": relative,
                "transformation": "byte-identical copy",
            }
        )

    data_license = """TrajectoryBench research data archive\n\nCopyright 2026 Fatemeh Akbarifar\n\nThe original numerical data and archive documentation in this package are\nlicensed under the Creative Commons Attribution 4.0 International License:\nhttps://creativecommons.org/licenses/by/4.0/\n\nThis license does not apply to excluded raw trajectories, benchmark task\ncontent, third-party software or data, model services, or container images.\n"""
    (output / "DATA_LICENSE.txt").write_text(data_license, encoding="utf-8")
    write_archive_readme(output, source_checksums)

    for relative in ("README.md", "DATA_LICENSE.txt"):
        destination = output / relative
        manifest_rows.append(
            {
                "path": relative,
                "bytes": destination.stat().st_size,
                "sha256": sha256_file(destination),
                "source": "generated by scripts/build_research_archive.py",
                "transformation": "release documentation",
            }
        )

    manifest_rows.sort(key=lambda row: str(row["path"]))
    manifest_path = output / "MANIFEST.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=("path", "bytes", "sha256", "source", "transformation")
        )
        writer.writeheader()
        writer.writerows(manifest_rows)

    summary = {
        "files_in_manifest": len(manifest_rows),
        "source_dataset_checksums": source_checksums,
        "sanitization": sorted(TEXT_AND_PROVIDER_FIELDS),
    }
    summary_path = output / "archive_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    checksum_paths = [output / str(row["path"]) for row in manifest_rows]
    checksum_paths.extend((manifest_path, summary_path))
    with (output / "SHA256SUMS").open("w", encoding="utf-8") as stream:
        for path in sorted(checksum_paths, key=lambda item: item.relative_to(output).as_posix()):
            stream.write(f"{sha256_file(path)}  {path.relative_to(output).as_posix()}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build_archive(args.repo_root.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
