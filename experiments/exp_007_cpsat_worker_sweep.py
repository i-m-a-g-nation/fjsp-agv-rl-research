"""
exp_007_cpsat_worker_sweep.py

Phase 1 CP-SAT worker-count sweep:
- Load one tracked static FJSP benchmark instance
- Keep the CP-SAT time limit fixed while varying worker count
- Treat zero workers explicitly as OR-Tools automatic configuration
- Validate every returned schedule and record bound-gap diagnostics
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Sequence

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.common import (  # noqa: E402
    ExperimentRecord,
    record_from_run,
    run_solver_suite,
    write_results_csv,
)
from experiments.exp_006_cpsat_time_limit_sweep import (  # noqa: E402
    CpSatSolveFn,
    print_sweep_runs,
)
from src.data.instance import FJSPInstance  # noqa: E402
from src.data.loader import load_project_benchmark_file as load_benchmark_file  # noqa: E402
from src.scheduling.encoding import ScheduleResult  # noqa: E402
from src.solvers.ortools_solver import ortools_solve  # noqa: E402


def validate_worker_counts(worker_counts: Sequence[int]) -> list[int]:
    """Return distinct non-negative worker counts in caller order."""

    counts = list(worker_counts)
    if not counts:
        raise ValueError("at least one CP-SAT worker count is required")
    if any(count < 0 for count in counts):
        raise ValueError("CP-SAT worker counts must be non-negative")
    if len(set(counts)) != len(counts):
        raise ValueError("CP-SAT worker counts must be distinct")
    return counts


def worker_label(num_workers: int) -> str:
    """Return the user-facing worker label used in tracked CSV records."""

    return "auto" if num_workers == 0 else str(num_workers)


def build_worker_solvers(
    instance: FJSPInstance,
    worker_counts: Sequence[int],
    time_limit: float = 10.0,
    solver_fn: CpSatSolveFn = ortools_solve,
) -> list[tuple[str, Callable[[], ScheduleResult]]]:
    """Bind one CP-SAT solver call per worker-count configuration."""

    counts = validate_worker_counts(worker_counts)
    if time_limit <= 0:
        raise ValueError("time_limit must be positive")
    return [
        (
            f"CP-SAT(workers={worker_label(count)},tl={time_limit:g}s)",
            lambda workers=count: solver_fn(
                instance,
                time_limit=time_limit,
                num_workers=workers,
            ),
        )
        for count in counts
    ]


def run_worker_sweep(
    instance_path: str | Path,
    worker_counts: Sequence[int],
    time_limit: float = 10.0,
    instance_name: str | None = None,
    solver_fn: CpSatSolveFn = ortools_solve,
    experiment_id: str = "exp_007_cpsat_worker_sweep",
) -> tuple[list[ExperimentRecord], list[str]]:
    """Run and normalize a CP-SAT worker-count sweep for one benchmark."""

    path = Path(instance_path)
    instance = load_benchmark_file(path)
    label = path.as_posix() if instance_name is None else instance_name
    print(
        f"Instance: {label} "
        f"({instance.num_jobs} jobs x {instance.num_machines} machines, "
        f"{instance.total_ops} ops)"
    )
    runs = run_solver_suite(
        build_worker_solvers(
            instance,
            worker_counts,
            time_limit=time_limit,
            solver_fn=solver_fn,
        ),
        expected_instance=instance,
    )
    print_sweep_runs(runs, algorithm_width=34)

    records = [
        record_from_run(experiment_id, label, run)
        for run in runs
    ]
    failures = [
        f"{run.algorithm}: {run.note}"
        for run in runs
        if not run.feasible
    ]
    return records, failures


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the CP-SAT worker sweep."""

    root = Path(__file__).parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--instance",
        type=Path,
        default=root / "instances" / "fjsplib" / "Brandimarte1993" / "mk03.fjs",
        help="Tracked benchmark file evaluated by the sweep",
    )
    parser.add_argument(
        "--worker-counts",
        type=int,
        nargs="+",
        default=[1, 2, 4, 0],
        help="Distinct worker counts; zero means OR-Tools automatic configuration",
    )
    parser.add_argument(
        "--time-limit",
        type=float,
        default=10.0,
        help="Positive CP-SAT time limit shared by every worker configuration",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "experiments" / "results" / "exp_007_cpsat_worker_sweep.csv",
        help="Normalized CSV output path",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the configured worker sweep and return a process exit code."""

    args = parse_args(argv)
    root = Path(__file__).parent.parent
    try:
        counts = validate_worker_counts(args.worker_counts)
        try:
            instance_name = args.instance.resolve().relative_to(
                (root / "instances").resolve()
            ).as_posix()
        except ValueError:
            instance_name = args.instance.name
        records, failures = run_worker_sweep(
            args.instance,
            counts,
            time_limit=args.time_limit,
            instance_name=instance_name,
        )
    except (OSError, ValueError) as exc:
        print(f"Configuration error: {exc}")
        return 2

    write_results_csv(args.output, records)
    print()
    print(f"CSV results written to: {args.output}")

    if failures:
        print("FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("All CP-SAT worker-sweep schedules passed feasibility check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
