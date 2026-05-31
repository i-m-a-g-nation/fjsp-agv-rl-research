from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.scheduling.encoding import ScheduleResult
from src.scheduling.feasibility import check_feasibility


@dataclass(frozen=True)
class SolverRun:
    """Raw result of running one solver function once."""

    algorithm: str
    result: ScheduleResult | None
    makespan: int | None
    feasible: bool
    runtime_s: float
    note: str
    error: str | None = None


@dataclass(frozen=True)
class ExperimentRecord:
    """One normalized row for an experiment result table."""

    experiment_id: str
    instance_name: str
    algorithm: str
    makespan: int | None
    feasible: bool
    runtime_s: float
    note: str
    objective_bound: float | None = None
    gap: float | None = None
    solver_wall_time: float | None = None

    def to_csv_row(self) -> dict[str, str]:
        """Convert the record to stable text values for CSV output."""

        return {
            "experiment_id": self.experiment_id,
            "instance_name": self.instance_name,
            "algorithm": self.algorithm,
            "makespan": "" if self.makespan is None else str(self.makespan),
            "feasible": "PASS" if self.feasible else "FAIL",
            "runtime_s": f"{self.runtime_s:.6f}",
            "note": self.note,
            "objective_bound": "" if self.objective_bound is None else f"{self.objective_bound:.6f}",
            "gap": "" if self.gap is None else f"{self.gap:.6f}",
            "solver_wall_time": "" if self.solver_wall_time is None else f"{self.solver_wall_time:.6f}",
        }


def write_results_csv(path: str | Path, records: list[ExperimentRecord]) -> None:
    """Write normalized experiment records to a UTF-8 CSV file."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "experiment_id",
        "instance_name",
        "algorithm",
        "makespan",
        "feasible",
        "runtime_s",
        "note",
        "objective_bound",
        "gap",
        "solver_wall_time",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_csv_row())


def run_solver_once(
    name: str,
    solver_fn: Callable[[], ScheduleResult],
    success_note: str = "PASS",
) -> SolverRun:
    """Run one solver and validate its ScheduleResult."""

    start = time.perf_counter()
    try:
        result = solver_fn()
        elapsed = time.perf_counter() - start
        feasible, violations = check_feasibility(result)
        if not feasible:
            return SolverRun(
                algorithm=name,
                result=result,
                makespan=result.makespan,
                feasible=False,
                runtime_s=elapsed,
                note=f"violations={violations}",
            )
        return SolverRun(
            algorithm=name,
            result=result,
            makespan=result.makespan,
            feasible=True,
            runtime_s=elapsed,
            note=result.solver_status or success_note,
        )
    except Exception as exc:
        elapsed = time.perf_counter() - start
        message = str(exc)
        return SolverRun(
            algorithm=name,
            result=None,
            makespan=None,
            feasible=False,
            runtime_s=elapsed,
            note=f"ERROR: {message}",
            error=message,
        )


def run_solver_suite(
    solvers: list[tuple[str, Callable[[], ScheduleResult]]],
    success_note: str = "PASS",
) -> list[SolverRun]:
    """Run a list of named solvers with the same validation contract."""

    return [
        run_solver_once(name, solver_fn, success_note=success_note)
        for name, solver_fn in solvers
    ]


def print_solver_runs(runs: list[SolverRun], algorithm_width: int = 24) -> None:
    """Print a stable console table for solver runs."""

    header = (
        f"{'Algorithm':{algorithm_width}s} "
        f"{'makespan':>8s}  {'feasible':>8s}  {'runtime_s':>10s}  note"
    )
    print(header)
    print("-" * len(header))
    for run in runs:
        mk_str = str(run.makespan) if run.makespan is not None else "N/A"
        status = "PASS" if run.feasible else "FAIL"
        print(
            f"{run.algorithm:{algorithm_width}s} "
            f"{mk_str:>8s}  {status:>8s}  {run.runtime_s:>10.4f}  {run.note}"
        )


def record_from_run(
    experiment_id: str,
    instance_name: str,
    run: SolverRun,
    note: str | None = None,
) -> ExperimentRecord:
    """Build a normalized CSV record from a solver run."""

    result = run.result
    return ExperimentRecord(
        experiment_id=experiment_id,
        instance_name=instance_name,
        algorithm=run.algorithm,
        makespan=run.makespan,
        feasible=run.feasible,
        runtime_s=run.runtime_s,
        note=run.note if note is None else note,
        objective_bound=None if result is None else result.solver_objective_bound,
        gap=None if result is None else result.solver_gap,
        solver_wall_time=None if result is None else result.solver_wall_time,
    )
