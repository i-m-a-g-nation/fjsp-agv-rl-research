from __future__ import annotations

import csv
import io
import time
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.scheduling.encoding import ScheduleResult
from src.scheduling.feasibility import check_feasibility
from src.data.instance import FJSPInstance, validate_instance


def experiment_output_dir(experiment_id: str, argv=None) -> Path:
    """Give simple experiment CLIs a fresh default and an explicit output path."""
    import argparse
    from uuid import uuid4
    parser = argparse.ArgumentParser(description=experiment_id)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args(argv)
    if args.output_dir is not None:
        return args.output_dir
    return Path(__file__).resolve().parent / 'runs' / f'{experiment_id}-{uuid4().hex[:12]}'


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
    evidence: dict | None = None


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
    evidence: dict | None = None

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
    from experiments.artifacts import write_bundle
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for record in records:
        writer.writerow(record.to_csv_row())
    write_bundle(output_path, buffer.getvalue().encode("utf-8"), records)


def run_solver_once(
    name: str,
    solver_fn: Callable[[], ScheduleResult],
    success_note: str = "PASS",
    *, expected_instance: FJSPInstance,
) -> SolverRun:
    """Run one solver and validate its ScheduleResult."""

    from experiments.artifacts import capture_run, source_hashes
    validate_instance(expected_instance)
    original = deepcopy(expected_instance)
    sources = source_hashes()
    start = time.perf_counter()
    try:
        result = solver_fn()
        elapsed = time.perf_counter() - start
        if expected_instance != original:
            raise ValueError("INSTANCE_CHANGED: solver changed the original instance")
        if not isinstance(result, ScheduleResult):
            raise ValueError("INVALID_RESULT: solver must return ScheduleResult")
        feasible, violations = check_feasibility(result, expected_instance=original)
        if source_hashes() != sources:
            raise ValueError("SOURCE_CHANGED: source changed during solver execution")
        if not feasible:
            return SolverRun(
                algorithm=name,
                result=result,
                makespan=result.makespan,
                feasible=False,
                runtime_s=elapsed,
                note=f"violations={violations}",
                evidence=capture_run(original, result, False, [v.code for v in violations], None, sources),
            )
        return SolverRun(
            algorithm=name,
            result=result,
            makespan=result.makespan,
            feasible=True,
            runtime_s=elapsed,
            note=result.solver_status or success_note,
            evidence=capture_run(original, result, True, [], None, sources),
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
            evidence=capture_run(original, None, False, [], message, sources),
        )


def run_solver_suite(
    solvers: list[tuple[str, Callable[[], ScheduleResult]]],
    success_note: str = "PASS",
    *, expected_instance: FJSPInstance,
) -> list[SolverRun]:
    """Run a list of named solvers with the same validation contract."""

    validate_instance(expected_instance)
    original = deepcopy(expected_instance)
    def guarded(solver_fn):
        def solve():
            if expected_instance != original:
                raise ValueError("INSTANCE_CHANGED: suite input changed before execution")
            result = solver_fn()
            if expected_instance != original:
                raise ValueError("INSTANCE_CHANGED: solver changed the suite input")
            return result
        return solve
    return [
        run_solver_once(name, guarded(solver_fn), success_note=success_note, expected_instance=original)
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
        evidence=deepcopy(run.evidence),
    )
