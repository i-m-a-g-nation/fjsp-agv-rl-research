"""
exp_010_heuristic_benchmark_matrix.py

Phase 1 heuristic benchmark matrix:
- Discover tracked static FJSPLib files recursively in stable path order
- Run deterministic baselines and strict dispatching rules once per instance
- Run seeded Random and DispatchRandom variants for reproducible observations
- Preserve every feasibility-checked raw run and per-family aggregate summary
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
    print_solver_runs,
    record_from_run,
    run_solver_suite,
    write_results_csv,
)
from experiments.exp_005_benchmark_batch import discover_benchmark_files  # noqa: E402
from src.data.instance import FJSPInstance  # noqa: E402
from src.data.loader import load_project_benchmark_file as load_benchmark_file  # noqa: E402
from src.scheduling.encoding import ScheduleResult  # noqa: E402
from src.solvers.heuristics import (  # noqa: E402
    dispatch_eft_solve,
    dispatch_fifo_solve,
    dispatch_mopnr_solve,
    dispatch_mwkr_solve,
    dispatch_random_solve,
    dispatch_spt_solve,
    earliest_finish_time_solve,
    fifo_solve,
    random_solve,
    spt_solve,
)


@dataclass(frozen=True)
class HeuristicSpec:
    """One named heuristic run and its aggregate family."""

    family: str
    run_label: str
    variant: str
    solver_fn: Callable[[FJSPInstance], ScheduleResult]


@dataclass(frozen=True)
class HeuristicAggregate:
    """Summary statistics for one algorithm family on one instance."""

    instance_name: str
    family: str
    variants: str
    runs: int
    feasible_runs: int
    best_makespan: int | None
    mean_makespan: float | None
    stdev_makespan: float | None
    worst_makespan: int | None
    mean_runtime_s: float
    statuses: str

    def to_csv_row(self) -> dict[str, str]:
        """Convert aggregate statistics to stable CSV text values."""

        return {
            "instance_name": self.instance_name,
            "algorithm_family": self.family,
            "variants": self.variants,
            "runs": str(self.runs),
            "feasible_runs": str(self.feasible_runs),
            "best_makespan": _format_optional(self.best_makespan),
            "mean_makespan": _format_optional(self.mean_makespan),
            "stdev_makespan": _format_optional(self.stdev_makespan),
            "worst_makespan": _format_optional(self.worst_makespan),
            "mean_runtime_s": f"{self.mean_runtime_s:.6f}",
            "statuses": self.statuses,
        }


def _format_optional(value: float | int | None) -> str:
    """Format optional aggregate values for tracked CSV output."""

    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return f"{value:.6f}"


def validate_seeds(seeds: Sequence[int]) -> list[int]:
    """Return distinct seeds in caller order."""

    values = list(seeds)
    if not values:
        raise ValueError("at least one random seed is required")
    if len(set(values)) != len(values):
        raise ValueError("random seeds must be distinct")
    return values


def build_heuristic_specs(seeds: Sequence[int]) -> list[HeuristicSpec]:
    """Build deterministic and reproducibly seeded Phase 1 heuristic specs."""

    values = validate_seeds(seeds)
    specs = [
        HeuristicSpec("FIFO", "FIFO", "fixed", fifo_solve),
        HeuristicSpec("SPT", "SPT", "fixed", spt_solve),
        HeuristicSpec(
            "EarliestFinishTime",
            "EarliestFinishTime",
            "fixed",
            earliest_finish_time_solve,
        ),
        HeuristicSpec("DispatchFIFO", "DispatchFIFO", "fixed", dispatch_fifo_solve),
        HeuristicSpec("DispatchSPT", "DispatchSPT", "fixed", dispatch_spt_solve),
        HeuristicSpec("DispatchEFT", "DispatchEFT", "fixed", dispatch_eft_solve),
        HeuristicSpec("DispatchMWKR", "DispatchMWKR", "fixed", dispatch_mwkr_solve),
        HeuristicSpec("DispatchMOPNR", "DispatchMOPNR", "fixed", dispatch_mopnr_solve),
    ]
    specs.extend(
        HeuristicSpec(
            "Random",
            f"Random(seed={seed})",
            f"seed={seed}",
            lambda instance, bound_seed=seed: random_solve(
                instance,
                seed=bound_seed,
            ),
        )
        for seed in values
    )
    specs.extend(
        HeuristicSpec(
            "DispatchRandom",
            f"DispatchRandom(seed={seed})",
            f"seed={seed}",
            lambda instance, bound_seed=seed: dispatch_random_solve(
                instance,
                seed=bound_seed,
            ),
        )
        for seed in values
    )
    return specs


def aggregate_heuristic_runs(
    instance_name: str,
    specs: Sequence[HeuristicSpec],
    runs: Sequence[SolverRun],
) -> list[HeuristicAggregate]:
    """Aggregate related heuristic variants without hiding failed attempts."""

    if len(specs) != len(runs):
        raise ValueError(f"expected {len(specs)} solver runs, got {len(runs)}")

    grouped: dict[str, list[tuple[HeuristicSpec, SolverRun]]] = {}
    for spec, run in zip(specs, runs):
        grouped.setdefault(spec.family, []).append((spec, run))

    aggregates = []
    for family, group in grouped.items():
        group_runs = [run for _spec, run in group]
        feasible = [run for run in group_runs if run.feasible]
        makespans = [run.makespan for run in feasible if run.makespan is not None]
        status_counts = Counter(run.note for run in group_runs)
        aggregates.append(
            HeuristicAggregate(
                instance_name=instance_name,
                family=family,
                variants=";".join(spec.variant for spec, _run in group),
                runs=len(group),
                feasible_runs=len(feasible),
                best_makespan=min(makespans) if makespans else None,
                mean_makespan=float(statistics.mean(makespans)) if makespans else None,
                stdev_makespan=statistics.pstdev(makespans) if makespans else None,
                worst_makespan=max(makespans) if makespans else None,
                mean_runtime_s=statistics.mean(run.runtime_s for run in group_runs),
                statuses=";".join(
                    f"{status}:{count}"
                    for status, count in sorted(status_counts.items())
                ),
            )
        )
    return aggregates


def write_heuristic_aggregates_csv(
    path: str | Path,
    aggregates: Sequence[HeuristicAggregate],
) -> None:
    """Write heuristic-family summaries to a UTF-8 CSV file."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "instance_name",
        "algorithm_family",
        "variants",
        "runs",
        "feasible_runs",
        "best_makespan",
        "mean_makespan",
        "stdev_makespan",
        "worst_makespan",
        "mean_runtime_s",
        "statuses",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for aggregate in aggregates:
            writer.writerow(aggregate.to_csv_row())


def run_heuristic_benchmark_matrix(
    paths: Sequence[Path],
    input_dir: str | Path,
    specs: Sequence[HeuristicSpec],
    experiment_id: str = "exp_010_heuristic_benchmark_matrix",
) -> tuple[list[ExperimentRecord], list[HeuristicAggregate], list[str]]:
    """Run heuristics across benchmark paths while retaining failure records."""

    root = Path(input_dir)
    records: list[ExperimentRecord] = []
    aggregates: list[HeuristicAggregate] = []
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
        runs = run_solver_suite(
            [
                (spec.run_label, lambda fn=spec.solver_fn, inst=instance: fn(inst))
                for spec in specs
            ],
            expected_instance=instance,
        )
        print_solver_runs(runs, algorithm_width=28)
        records.extend(
            record_from_run(experiment_id, instance_name, run)
            for run in runs
        )
        aggregates.extend(aggregate_heuristic_runs(instance_name, specs, runs))
        failures.extend(
            f"{instance_name} / {run.algorithm}: {run.note}"
            for run in runs
            if not run.feasible
        )
        print()

    return records, aggregates, failures


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the heuristic benchmark matrix."""

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
        "--seeds",
        type=int,
        nargs="+",
        default=[42, 123, 999],
        help="Distinct random seeds used by Random and DispatchRandom",
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
        default=root / "experiments" / "results" / "exp_010_heuristic_benchmark_matrix_runs.csv",
        help="Normalized per-run CSV output path",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=root / "experiments" / "results" / "exp_010_heuristic_benchmark_matrix_summary.csv",
        help="Per-instance aggregate CSV output path",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the heuristic benchmark matrix and return a process exit code."""

    args = parse_args(argv)
    try:
        paths = discover_benchmark_files(
            args.input_dir,
            pattern=args.pattern,
            max_files=args.max_files,
        )
        specs = build_heuristic_specs(args.seeds)
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return 2

    if not paths:
        print(
            f"No benchmark files matched {args.pattern!r} "
            f"under {args.input_dir}"
        )
        return 2

    records, aggregates, failures = run_heuristic_benchmark_matrix(
        paths,
        args.input_dir,
        specs,
    )
    write_results_csv(args.runs_output, records)
    write_heuristic_aggregates_csv(args.summary_output, aggregates)
    print(f"Per-run CSV results written to: {args.runs_output}")
    print(f"Aggregate CSV results written to: {args.summary_output}")

    if failures:
        print("FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("All heuristic benchmark-matrix schedules passed feasibility check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
