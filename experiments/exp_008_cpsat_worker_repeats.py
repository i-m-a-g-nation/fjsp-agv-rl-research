"""
exp_008_cpsat_worker_repeats.py

Phase 1 repeated CP-SAT worker-count experiment:
- Load one tracked static FJSP benchmark instance
- Repeat each worker-count configuration under the same time limit
- Preserve every feasibility-checked raw run
- Aggregate incumbent, bound, gap, runtime, and solver-status observations
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.common import (  # noqa: E402
    ExperimentRecord,
    SolverRun,
    record_from_run,
    run_solver_suite,
    write_results_csv,
)
from experiments.exp_006_cpsat_time_limit_sweep import (  # noqa: E402
    CpSatSolveFn,
    print_sweep_runs,
)
from experiments.exp_007_cpsat_worker_sweep import (  # noqa: E402
    validate_worker_counts,
    worker_label,
)
from src.data.instance import FJSPInstance  # noqa: E402
from src.data.loader import load_project_benchmark_file as load_benchmark_file  # noqa: E402
from src.scheduling.encoding import ScheduleResult  # noqa: E402
from src.solvers.ortools_solver import ortools_solve  # noqa: E402


@dataclass(frozen=True)
class WorkerAggregate:
    """Summary statistics for repeated runs of one worker configuration."""

    num_workers: int
    repeats: int
    feasible_runs: int
    best_makespan: int | None
    mean_makespan: float | None
    stdev_makespan: float | None
    worst_makespan: int | None
    best_bound: float | None
    mean_bound: float | None
    best_gap: float | None
    mean_gap: float | None
    mean_runtime_s: float
    mean_solver_wall_time: float | None
    statuses: str

    def to_csv_row(self) -> dict[str, str]:
        """Convert aggregate statistics to stable CSV text values."""

        return {
            "workers": worker_label(self.num_workers),
            "repeats": str(self.repeats),
            "feasible_runs": str(self.feasible_runs),
            "best_makespan": _format_optional(self.best_makespan),
            "mean_makespan": _format_optional(self.mean_makespan),
            "stdev_makespan": _format_optional(self.stdev_makespan),
            "worst_makespan": _format_optional(self.worst_makespan),
            "best_bound": _format_optional(self.best_bound),
            "mean_bound": _format_optional(self.mean_bound),
            "best_gap": _format_optional(self.best_gap),
            "mean_gap": _format_optional(self.mean_gap),
            "mean_runtime_s": f"{self.mean_runtime_s:.6f}",
            "mean_solver_wall_time": _format_optional(self.mean_solver_wall_time),
            "statuses": self.statuses,
        }


def _format_optional(value: float | int | None) -> str:
    """Format optional aggregate values for tracked CSV output."""

    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return f"{value:.6f}"


def _optional_mean(values: Sequence[float | None]) -> float | None:
    """Return the mean of available values, or None when no value exists."""

    available = [value for value in values if value is not None]
    return statistics.mean(available) if available else None


def validate_repeats(repeats: int) -> int:
    """Return a positive repetition count."""

    if repeats <= 0:
        raise ValueError("repeats must be positive")
    return repeats


def build_repeated_worker_solvers(
    instance: FJSPInstance,
    worker_counts: Sequence[int],
    repeats: int = 3,
    time_limit: float = 10.0,
    solver_fn: CpSatSolveFn = ortools_solve,
) -> list[tuple[str, Callable[[], ScheduleResult]]]:
    """Bind repeated CP-SAT solver calls in worker-major, run-minor order."""

    counts = validate_worker_counts(worker_counts)
    count_repeats = validate_repeats(repeats)
    if time_limit <= 0:
        raise ValueError("time_limit must be positive")
    return [
        (
            (
                f"CP-SAT(workers={worker_label(workers)},"
                f"tl={time_limit:g}s,run={run_id}/{count_repeats})"
            ),
            lambda num_workers=workers: solver_fn(
                instance,
                time_limit=time_limit,
                num_workers=num_workers,
            ),
        )
        for workers in counts
        for run_id in range(1, count_repeats + 1)
    ]


def aggregate_worker_runs(
    runs: Sequence[SolverRun],
    worker_counts: Sequence[int],
    repeats: int,
) -> list[WorkerAggregate]:
    """Aggregate worker-major repeated runs without hiding failed attempts."""

    counts = validate_worker_counts(worker_counts)
    count_repeats = validate_repeats(repeats)
    expected = len(counts) * count_repeats
    if len(runs) != expected:
        raise ValueError(f"expected {expected} solver runs, got {len(runs)}")

    aggregates = []
    for index, num_workers in enumerate(counts):
        group = list(runs[index * count_repeats : (index + 1) * count_repeats])
        feasible = [run for run in group if run.feasible and run.result is not None]
        makespans = [run.makespan for run in feasible if run.makespan is not None]
        bounds = [run.result.solver_objective_bound for run in feasible]
        gaps = [run.result.solver_gap for run in feasible]
        solver_wall_times = [run.result.solver_wall_time for run in feasible]
        status_counts = Counter(run.note for run in group)
        aggregates.append(
            WorkerAggregate(
                num_workers=num_workers,
                repeats=count_repeats,
                feasible_runs=len(feasible),
                best_makespan=min(makespans) if makespans else None,
                mean_makespan=float(statistics.mean(makespans)) if makespans else None,
                stdev_makespan=statistics.pstdev(makespans) if makespans else None,
                worst_makespan=max(makespans) if makespans else None,
                best_bound=max((bound for bound in bounds if bound is not None), default=None),
                mean_bound=_optional_mean(bounds),
                best_gap=min((gap for gap in gaps if gap is not None), default=None),
                mean_gap=_optional_mean(gaps),
                mean_runtime_s=statistics.mean(run.runtime_s for run in group),
                mean_solver_wall_time=_optional_mean(solver_wall_times),
                statuses=";".join(
                    f"{status}:{count}"
                    for status, count in sorted(status_counts.items())
                ),
            )
        )
    return aggregates


def write_worker_aggregates_csv(
    path: str | Path,
    aggregates: Sequence[WorkerAggregate],
) -> None:
    """Write repeated worker-count summaries to a UTF-8 CSV file."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
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


def print_worker_aggregates(aggregates: Sequence[WorkerAggregate]) -> None:
    """Print a compact summary table for repeated worker-count runs."""

    header = (
        f"{'workers':>7s} {'pass':>7s} {'best':>6s} {'mean':>9s} "
        f"{'stdev':>9s} {'worst':>6s} {'bound':>9s} {'gap':>9s}"
    )
    print(header)
    print("-" * len(header))
    for aggregate in aggregates:
        print(
            f"{worker_label(aggregate.num_workers):>7s} "
            f"{aggregate.feasible_runs:>3d}/{aggregate.repeats:<3d} "
            f"{_format_optional(aggregate.best_makespan):>6s} "
            f"{_format_optional(aggregate.mean_makespan):>9s} "
            f"{_format_optional(aggregate.stdev_makespan):>9s} "
            f"{_format_optional(aggregate.worst_makespan):>6s} "
            f"{_format_optional(aggregate.best_bound):>9s} "
            f"{_format_optional(aggregate.best_gap):>9s}"
        )


def run_repeated_worker_sweep(
    instance_path: str | Path,
    worker_counts: Sequence[int],
    repeats: int = 3,
    time_limit: float = 10.0,
    instance_name: str | None = None,
    solver_fn: CpSatSolveFn = ortools_solve,
    experiment_id: str = "exp_008_cpsat_worker_repeats",
) -> tuple[list[ExperimentRecord], list[WorkerAggregate], list[str]]:
    """Run repeated CP-SAT worker-count configurations and aggregate results."""

    path = Path(instance_path)
    instance = load_benchmark_file(path)
    label = path.as_posix() if instance_name is None else instance_name
    solvers = build_repeated_worker_solvers(
        instance,
        worker_counts,
        repeats=repeats,
        time_limit=time_limit,
        solver_fn=solver_fn,
    )
    print(
        f"Instance: {label} "
        f"({instance.num_jobs} jobs x {instance.num_machines} machines, "
        f"{instance.total_ops} ops)"
    )
    runs = run_solver_suite(solvers, expected_instance=instance)
    print_sweep_runs(runs, algorithm_width=44)
    aggregates = aggregate_worker_runs(runs, worker_counts, repeats)
    print()
    print("Aggregate observations:")
    print_worker_aggregates(aggregates)

    records = [record_from_run(experiment_id, label, run) for run in runs]
    failures = [
        f"{run.algorithm}: {run.note}"
        for run in runs
        if not run.feasible
    ]
    return records, aggregates, failures


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the repeated worker-count experiment."""

    root = Path(__file__).parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--instance",
        type=Path,
        default=root / "instances" / "fjsplib" / "Brandimarte1993" / "mk03.fjs",
        help="Tracked benchmark file evaluated by the experiment",
    )
    parser.add_argument(
        "--worker-counts",
        type=int,
        nargs="+",
        default=[1, 2, 4, 0],
        help="Distinct worker counts; zero means OR-Tools automatic configuration",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Positive number of repeated runs for each worker configuration",
    )
    parser.add_argument(
        "--time-limit",
        type=float,
        default=10.0,
        help="Positive CP-SAT time limit shared by every run",
    )
    parser.add_argument(
        "--runs-output",
        type=Path,
        default=root / "experiments" / "results" / "exp_008_cpsat_worker_repeats_runs.csv",
        help="Normalized per-run CSV output path",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=root / "experiments" / "results" / "exp_008_cpsat_worker_repeats_summary.csv",
        help="Aggregate CSV output path",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run repeated worker-count observations and return a process exit code."""

    args = parse_args(argv)
    root = Path(__file__).parent.parent
    try:
        counts = validate_worker_counts(args.worker_counts)
        count_repeats = validate_repeats(args.repeats)
        try:
            instance_name = args.instance.resolve().relative_to(
                (root / "instances").resolve()
            ).as_posix()
        except ValueError:
            instance_name = args.instance.name
        records, aggregates, failures = run_repeated_worker_sweep(
            args.instance,
            counts,
            repeats=count_repeats,
            time_limit=args.time_limit,
            instance_name=instance_name,
        )
    except (OSError, ValueError) as exc:
        print(f"Configuration error: {exc}")
        return 2

    write_results_csv(args.runs_output, records)
    write_worker_aggregates_csv(args.summary_output, aggregates)
    print()
    print(f"Per-run CSV results written to: {args.runs_output}")
    print(f"Aggregate CSV results written to: {args.summary_output}")

    if failures:
        print("FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("All repeated CP-SAT schedules passed feasibility check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
