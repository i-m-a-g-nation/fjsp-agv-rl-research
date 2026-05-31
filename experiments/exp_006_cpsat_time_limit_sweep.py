"""
exp_006_cpsat_time_limit_sweep.py

Phase 1 CP-SAT time-limit sweep:
- Load one tracked static FJSP benchmark instance
- Run the same CP-SAT baseline under several positive time limits
- Validate every returned schedule through the independent feasibility checker
- Record status, objective bound, relative gap, and solver wall time
"""
from __future__ import annotations

import argparse
import sys
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
from src.data.instance import FJSPInstance  # noqa: E402
from src.data.loader import load_benchmark_file  # noqa: E402
from src.scheduling.encoding import ScheduleResult  # noqa: E402
from src.solvers.ortools_solver import ortools_solve  # noqa: E402

CpSatSolveFn = Callable[..., ScheduleResult]


def validate_time_limits(time_limits: Sequence[float]) -> list[float]:
    """Return positive CP-SAT time limits while preserving caller order."""

    limits = list(time_limits)
    if not limits:
        raise ValueError("at least one CP-SAT time limit is required")
    if any(limit <= 0 for limit in limits):
        raise ValueError("CP-SAT time limits must be positive")
    return limits


def build_cpsat_solvers(
    instance: FJSPInstance,
    time_limits: Sequence[float],
    num_workers: int = 1,
    solver_fn: CpSatSolveFn = ortools_solve,
) -> list[tuple[str, Callable[[], ScheduleResult]]]:
    """Bind one CP-SAT solver call per configured time limit."""

    limits = validate_time_limits(time_limits)
    if num_workers <= 0:
        raise ValueError("num_workers must be positive")
    return [
        (
            f"CP-SAT(tl={limit:g}s)",
            lambda tl=limit: solver_fn(
                instance,
                time_limit=tl,
                num_workers=num_workers,
            ),
        )
        for limit in limits
    ]


def print_sweep_runs(
    runs: Sequence[SolverRun],
    algorithm_width: int = 18,
) -> None:
    """Print CP-SAT diagnostics in a stable compact table."""

    header = (
        f"{'Algorithm':{algorithm_width}s} {'makespan':>8s}  {'status':>8s}  "
        f"{'bound':>10s}  {'gap':>10s}  {'solver_s':>10s}"
    )
    print(header)
    print("-" * len(header))
    for run in runs:
        result = run.result
        mk_str = "N/A" if run.makespan is None else str(run.makespan)
        bound = None if result is None else result.solver_objective_bound
        gap = None if result is None else result.solver_gap
        wall_time = None if result is None else result.solver_wall_time
        print(
            f"{run.algorithm:{algorithm_width}s} {mk_str:>8s}  {run.note:>8s}  "
            f"{_format_optional(bound):>10s}  {_format_optional(gap):>10s}  "
            f"{_format_optional(wall_time):>10s}"
        )


def _format_optional(value: float | None) -> str:
    """Format optional diagnostic values for console output."""

    return "N/A" if value is None else f"{value:.6f}"


def run_cpsat_sweep(
    instance_path: str | Path,
    time_limits: Sequence[float],
    instance_name: str | None = None,
    num_workers: int = 1,
    solver_fn: CpSatSolveFn = ortools_solve,
    experiment_id: str = "exp_006_cpsat_time_limit_sweep",
) -> tuple[list[ExperimentRecord], list[str]]:
    """Run and normalize a CP-SAT time-limit sweep for one benchmark."""

    path = Path(instance_path)
    instance = load_benchmark_file(path)
    label = path.as_posix() if instance_name is None else instance_name
    print(
        f"Instance: {label} "
        f"({instance.num_jobs} jobs x {instance.num_machines} machines, "
        f"{instance.total_ops} ops)"
    )
    runs = run_solver_suite(
        build_cpsat_solvers(
            instance,
            time_limits,
            num_workers=num_workers,
            solver_fn=solver_fn,
        )
    )
    print_sweep_runs(runs)

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
    """Parse command-line options for the CP-SAT sweep."""

    root = Path(__file__).parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--instance",
        type=Path,
        default=root / "instances" / "fjsplib" / "Brandimarte1993" / "mk03.fjs",
        help="Tracked benchmark file evaluated by the sweep",
    )
    parser.add_argument(
        "--time-limits",
        type=float,
        nargs="+",
        default=[1.0, 3.0, 10.0],
        help="Positive CP-SAT limits in seconds, evaluated in the given order",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "experiments" / "results" / "exp_006_cpsat_time_limit_sweep.csv",
        help="Normalized CSV output path",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=1,
        help="Positive fixed CP-SAT worker count; default 1 reduces sweep noise",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the configured sweep and return a process exit code."""

    args = parse_args(argv)
    root = Path(__file__).parent.parent
    try:
        limits = validate_time_limits(args.time_limits)
        try:
            instance_name = args.instance.resolve().relative_to(
                (root / "instances").resolve()
            ).as_posix()
        except ValueError:
            instance_name = args.instance.name
        records, failures = run_cpsat_sweep(
            args.instance,
            limits,
            instance_name=instance_name,
            num_workers=args.num_workers,
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

    print("All CP-SAT sweep schedules passed feasibility check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
