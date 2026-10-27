"""
exp_005_benchmark_batch.py

Phase 1 batch benchmark experiment:
- Discover benchmark-format instances recursively under a directory
- Run selected baselines, strict dispatching rules, and optional CP-SAT
- Record loader failures and solver failures in a normalized CSV
- Require every returned schedule to pass the independent feasibility checker
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Sequence

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.common import (  # noqa: E402
    ExperimentRecord,
    print_solver_runs,
    record_from_run,
    run_solver_suite,
    write_results_csv,
)
from src.data.instance import FJSPInstance  # noqa: E402
from src.data.loader import load_project_benchmark_file as load_benchmark_file  # noqa: E402
from src.scheduling.encoding import ScheduleResult  # noqa: E402
from src.solvers.heuristics import (  # noqa: E402
    dispatch_eft_solve,
    dispatch_fifo_solve,
    dispatch_mopnr_solve,
    dispatch_mwkr_solve,
    dispatch_spt_solve,
    fifo_solve,
    spt_solve,
)
from src.solvers.ortools_solver import ortools_solve  # noqa: E402

SolverSpec = tuple[str, Callable[[FJSPInstance], ScheduleResult]]


def discover_benchmark_files(
    input_dir: str | Path,
    pattern: str = "*.fjs",
    max_files: int | None = None,
) -> list[Path]:
    """Return recursively discovered benchmark files in stable path order."""

    directory = Path(input_dir)
    if not directory.is_dir():
        raise ValueError(f"Benchmark input directory does not exist: {directory}")
    if max_files is not None and max_files <= 0:
        raise ValueError("max_files must be positive when provided")

    paths = sorted(
        (path for path in directory.rglob(pattern) if path.is_file()),
        key=lambda path: path.as_posix(),
    )
    return paths if max_files is None else paths[:max_files]


def build_solver_specs(
    cp_sat_time_limit: float = 10.0,
    include_cp_sat: bool = True,
) -> list[SolverSpec]:
    """Build the Phase 1 algorithm list for a benchmark batch."""

    if cp_sat_time_limit <= 0:
        raise ValueError("cp_sat_time_limit must be positive")

    solvers: list[SolverSpec] = [
        ("FIFO", fifo_solve),
        ("SPT", spt_solve),
        ("DispatchFIFO", dispatch_fifo_solve),
        ("DispatchSPT", dispatch_spt_solve),
        ("DispatchEFT", dispatch_eft_solve),
        ("DispatchMWKR", dispatch_mwkr_solve),
        ("DispatchMOPNR", dispatch_mopnr_solve),
    ]
    if include_cp_sat:
        solvers.append(
            (
                f"CP-SAT(tl={cp_sat_time_limit:g}s)",
                lambda instance: ortools_solve(
                    instance,
                    time_limit=cp_sat_time_limit,
                ),
            )
        )
    return solvers


def run_benchmark_batch(
    paths: Sequence[Path],
    input_dir: str | Path,
    solvers: Sequence[SolverSpec],
    experiment_id: str = "exp_005_benchmark_batch",
) -> tuple[list[ExperimentRecord], list[str]]:
    """Load and evaluate benchmark paths while retaining failure records."""

    root = Path(input_dir)
    records: list[ExperimentRecord] = []
    failures: list[str] = []

    for path in paths:
        instance_name = path.relative_to(root).as_posix()
        try:
            instance = load_benchmark_file(path)
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

        print(
            f"Instance: {instance_name} "
            f"({instance.num_jobs} jobs x {instance.num_machines} machines, "
            f"{instance.total_ops} ops)"
        )
        instance_solvers = [
            (name, lambda fn=solver_fn, inst=instance: fn(inst))
            for name, solver_fn in solvers
        ]
        runs = run_solver_suite(instance_solvers, expected_instance=instance)
        print_solver_runs(runs, algorithm_width=20)
        records.extend(
            record_from_run(experiment_id, instance_name, run)
            for run in runs
        )
        failures.extend(
            f"{instance_name} / {run.algorithm}: {run.note}"
            for run in runs
            if not run.feasible
        )
        print()

    return records, failures


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the batch benchmark experiment."""

    root = Path(__file__).parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=root / "instances",
        help="Directory scanned recursively for benchmark files",
    )
    parser.add_argument(
        "--pattern",
        default="*.fjs",
        help="Filename pattern used during recursive discovery",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "experiments" / "results" / "exp_005_benchmark_batch.csv",
        help="Normalized CSV output path",
    )
    parser.add_argument(
        "--cp-sat-time-limit",
        type=float,
        default=10.0,
        help="CP-SAT time limit per instance in seconds",
    )
    parser.add_argument(
        "--skip-cp-sat",
        action="store_true",
        help="Run heuristic baselines only",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Optional positive cap for quick controlled runs",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the configured benchmark batch and return a process exit code."""

    args = parse_args(argv)
    try:
        paths = discover_benchmark_files(
            args.input_dir,
            pattern=args.pattern,
            max_files=args.max_files,
        )
        solvers = build_solver_specs(
            cp_sat_time_limit=args.cp_sat_time_limit,
            include_cp_sat=not args.skip_cp_sat,
        )
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return 2

    if not paths:
        print(
            f"No benchmark files matched {args.pattern!r} "
            f"under {args.input_dir}"
        )
        return 2

    records, failures = run_benchmark_batch(paths, args.input_dir, solvers)
    write_results_csv(args.output, records)
    print(f"CSV results written to: {args.output}")

    if failures:
        print("FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("All batch benchmark schedules passed feasibility check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
