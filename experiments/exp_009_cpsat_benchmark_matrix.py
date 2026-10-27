"""
exp_009_cpsat_benchmark_matrix.py

Phase 1 repeated CP-SAT benchmark matrix:
- Discover tracked static FJSPLib files recursively in stable path order
- Repeat controlled worker-count configurations for every loaded instance
- Preserve loader failures and every feasibility-checked raw solver run
- Record per-instance worker aggregate statistics in a separate CSV
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.common import ExperimentRecord, write_results_csv  # noqa: E402
from experiments.exp_005_benchmark_batch import discover_benchmark_files  # noqa: E402
from experiments.exp_006_cpsat_time_limit_sweep import CpSatSolveFn  # noqa: E402
from experiments.exp_007_cpsat_worker_sweep import validate_worker_counts  # noqa: E402
from experiments.exp_008_cpsat_worker_repeats import (  # noqa: E402
    WorkerAggregate,
    run_repeated_worker_sweep,
    validate_repeats,
)
from src.data.loader import load_project_benchmark_file as load_benchmark_file  # noqa: E402
from src.solvers.ortools_solver import ortools_solve  # noqa: E402


@dataclass(frozen=True)
class BenchmarkWorkerAggregate:
    """One per-instance worker aggregate row for the benchmark matrix."""

    instance_name: str
    aggregate: WorkerAggregate

    def to_csv_row(self) -> dict[str, str]:
        """Convert the instance aggregate to stable CSV text values."""

        return {
            "instance_name": self.instance_name,
            **self.aggregate.to_csv_row(),
        }


def write_benchmark_aggregates_csv(
    path: str | Path,
    aggregates: Sequence[BenchmarkWorkerAggregate],
) -> None:
    """Write benchmark-matrix summaries to a UTF-8 CSV file."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "instance_name",
        "workers",
        "repeats",
        "feasible_runs",
        "best_makespan",
        "mean_makespan",
        "stdev_makespan",
        "worst_makespan",
        "best_bound",
        "mean_bound",
        "best_gap",
        "mean_gap",
        "mean_runtime_s",
        "mean_solver_wall_time",
        "statuses",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for aggregate in aggregates:
            writer.writerow(aggregate.to_csv_row())


def run_benchmark_matrix(
    paths: Sequence[Path],
    input_dir: str | Path,
    worker_counts: Sequence[int],
    repeats: int = 2,
    time_limit: float = 3.0,
    solver_fn: CpSatSolveFn = ortools_solve,
    experiment_id: str = "exp_009_cpsat_benchmark_matrix",
) -> tuple[list[ExperimentRecord], list[BenchmarkWorkerAggregate], list[str]]:
    """Run repeated CP-SAT configurations across benchmark paths."""

    root = Path(input_dir)
    counts = validate_worker_counts(worker_counts)
    count_repeats = validate_repeats(repeats)
    if time_limit <= 0:
        raise ValueError("time_limit must be positive")

    records: list[ExperimentRecord] = []
    aggregates: list[BenchmarkWorkerAggregate] = []
    failures: list[str] = []

    for path in paths:
        instance_name = path.relative_to(root).as_posix()
        try:
            load_benchmark_file(path)
        except Exception as exc:
            message = f"ERROR: {exc}"
            records.append(
                ExperimentRecord(
                    experiment_id=experiment_id,
                    instance_name=instance_name,
                    algorithm="LOAD",
                    makespan=None,
                    feasible=False,
                    runtime_s=0.0,
                    note=message,
                )
            )
            failures.append(f"{instance_name} / LOAD: {message}")
            print(f"Instance: {instance_name}")
            print(f"  LOAD FAILED: {exc}")
            print()
            continue

        instance_records, instance_aggregates, instance_failures = (
            run_repeated_worker_sweep(
                path,
                counts,
                repeats=count_repeats,
                time_limit=time_limit,
                instance_name=instance_name,
                solver_fn=solver_fn,
                experiment_id=experiment_id,
            )
        )
        records.extend(instance_records)
        aggregates.extend(
            BenchmarkWorkerAggregate(instance_name, aggregate)
            for aggregate in instance_aggregates
        )
        failures.extend(
            f"{instance_name} / {failure}"
            for failure in instance_failures
        )
        print()

    return records, aggregates, failures


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the benchmark matrix."""

    root = Path(__file__).parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=root / "instances" / "fjsplib",
        help="Directory scanned recursively for tracked benchmark files",
    )
    parser.add_argument(
        "--pattern",
        default="*.fjs",
        help="Filename pattern used during recursive discovery",
    )
    parser.add_argument(
        "--worker-counts",
        type=int,
        nargs="+",
        default=[1, 0],
        help="Distinct worker counts; zero means OR-Tools automatic configuration",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=2,
        help="Positive number of repeated runs for every worker configuration",
    )
    parser.add_argument(
        "--time-limit",
        type=float,
        default=3.0,
        help="Positive CP-SAT time limit shared by every run",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Optional positive cap for quick controlled runs",
    )
    parser.add_argument(
        "--runs-output",
        type=Path,
        default=root / "experiments" / "results" / "exp_009_cpsat_benchmark_matrix_runs.csv",
        help="Normalized per-run CSV output path",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=root / "experiments" / "results" / "exp_009_cpsat_benchmark_matrix_summary.csv",
        help="Per-instance aggregate CSV output path",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the benchmark matrix and return a process exit code."""

    args = parse_args(argv)
    try:
        paths = discover_benchmark_files(
            args.input_dir,
            pattern=args.pattern,
            max_files=args.max_files,
        )
        counts = validate_worker_counts(args.worker_counts)
        count_repeats = validate_repeats(args.repeats)
        if args.time_limit <= 0:
            raise ValueError("time_limit must be positive")
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return 2

    if not paths:
        print(
            f"No benchmark files matched {args.pattern!r} "
            f"under {args.input_dir}"
        )
        return 2

    records, aggregates, failures = run_benchmark_matrix(
        paths,
        args.input_dir,
        counts,
        repeats=count_repeats,
        time_limit=args.time_limit,
    )
    write_results_csv(args.runs_output, records)
    write_benchmark_aggregates_csv(args.summary_output, aggregates)
    print(f"Per-run CSV results written to: {args.runs_output}")
    print(f"Aggregate CSV results written to: {args.summary_output}")

    if failures:
        print("FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("All benchmark-matrix schedules passed feasibility check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
