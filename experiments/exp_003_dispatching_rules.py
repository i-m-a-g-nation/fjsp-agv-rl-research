"""
exp_003_dispatching_rules.py

Phase 1 strict dispatching-rule experiment:
- Run strict FIFO, SPT, EFT, MWKR, and Random dispatching rules on the toy instance
- Validate every result through feasibility checker
- Report makespan and runtime
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.common import ExperimentRecord, write_results_csv
from src.data.instance import create_toy_instance
from src.scheduling.encoding import ScheduleResult
from src.scheduling.feasibility import check_feasibility
from src.solvers.heuristics import (
    dispatch_eft_solve,
    dispatch_fifo_solve,
    dispatch_mwkr_solve,
    dispatch_random_solve,
    dispatch_spt_solve,
)


def run_solver(name: str, solver_fn: Callable[[], ScheduleResult]) -> tuple[str, int | None, bool, float, str]:
    start = time.perf_counter()
    try:
        result = solver_fn()
        elapsed = time.perf_counter() - start
        feasible, violations = check_feasibility(result)
        if not feasible:
            return name, result.makespan, False, elapsed, f"violations={violations}"
        return name, result.makespan, True, elapsed, "PASS"
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return name, None, False, elapsed, f"ERROR: {exc}"


def main() -> None:
    root = Path(__file__).parent.parent
    experiment_id = "exp_003_dispatching_rules"
    instance_name = "toy_3x3"
    instance = create_toy_instance()
    print(f"Instance: {instance.num_jobs} jobs x {instance.num_machines} machines, {instance.total_ops} ops")
    print()

    solvers: list[tuple[str, Callable[[], ScheduleResult]]] = [
        ("DispatchFIFO", lambda: dispatch_fifo_solve(instance)),
        ("DispatchSPT", lambda: dispatch_spt_solve(instance)),
        ("DispatchEFT", lambda: dispatch_eft_solve(instance)),
        ("DispatchMWKR", lambda: dispatch_mwkr_solve(instance)),
        ("DispatchRandom(42)", lambda: dispatch_random_solve(instance, seed=42)),
    ]

    header = f"{'Algorithm':24s} {'makespan':>8s}  {'feasible':>8s}  {'runtime_s':>10s}  note"
    print(header)
    print("-" * len(header))

    failures: list[str] = []
    records: list[ExperimentRecord] = []
    for name, solver_fn in solvers:
        algo, makespan, feasible, elapsed, note = run_solver(name, solver_fn)
        records.append(ExperimentRecord(
            experiment_id=experiment_id,
            instance_name=instance_name,
            algorithm=algo,
            makespan=makespan,
            feasible=feasible,
            runtime_s=elapsed,
            note=note,
        ))
        mk_str = str(makespan) if makespan is not None else "N/A"
        status = "PASS" if feasible else "FAIL"
        print(f"{algo:24s} {mk_str:>8s}  {status:>8s}  {elapsed:>10.4f}  {note}")
        if not feasible:
            failures.append(f"{algo}: {note}")

    output_path = root / "experiments" / "results" / f"{experiment_id}.csv"
    write_results_csv(output_path, records)
    print()
    print(f"CSV results written to: {output_path}")

    if failures:
        print()
        print("FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        sys.exit(1)

    print()
    print("All strict dispatching results passed feasibility check.")
    sys.exit(0)


if __name__ == "__main__":
    main()
