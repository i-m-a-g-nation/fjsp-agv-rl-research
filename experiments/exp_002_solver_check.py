"""
exp_002_solver_check.py

Phase 1 solver comparison experiment:
- Run heuristics and OR-Tools CP-SAT on toy instance
- Compare makespan, feasibility, runtime, solver_status
- All results must pass feasibility checker
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.instance import create_toy_instance
from src.scheduling.feasibility import check_feasibility, Violation
from src.solvers.heuristics import (
    fifo_solve,
    spt_solve,
    earliest_finish_time_solve,
    random_solve,
)
from src.solvers.ortools_solver import ortools_solve, OrtoolsSolverError


def run_solver(name: str, fn, instance):
    start = time.perf_counter()
    try:
        result = fn()
        elapsed = time.perf_counter() - start
        feasible, violations = check_feasibility(result)
        return name, result.makespan, feasible, violations, elapsed, None, result.solver_status
    except Exception as e:
        elapsed = time.perf_counter() - start
        return name, None, False, [], elapsed, str(e), None


def main() -> None:
    instance = create_toy_instance()
    print(f"Instance: {instance.num_jobs} jobs x {instance.num_machines} machines, {instance.total_ops} ops")
    print()

    solvers: list[tuple[str, callable]] = [
        ("FIFO", lambda: fifo_solve(instance)),
        ("SPT", lambda: spt_solve(instance)),
        ("EarliestFinishTime", lambda: earliest_finish_time_solve(instance)),
        ("Random(42)", lambda: random_solve(instance, seed=42)),
    ]

    for time_lim in [30.0, 60.0]:
        solvers.append(
            (f"CP-SAT(tl={time_lim:.0f}s)", lambda tl=time_lim: ortools_solve(instance, time_limit=tl))
        )

    header = f"{'Algorithm':30s} {'makespan':>8s}  {'feasible':>8s}  {'runtime_s':>10s}  {'note':>20s}"
    print(header)
    print("-" * len(header))

    rows: list[dict] = []
    failures: list[str] = []

    for name, fn in solvers:
        algo, mk, feasible, violations, elapsed, error, solver_status = run_solver(name, fn, instance)
        mk_str = str(mk) if mk is not None else "N/A"
        status = "PASS" if feasible else "FAIL"
        note = ""
        is_failure = False
        failure_reason = ""

        if error:
            note = f"ERROR: {error[:40]}"
            is_failure = True
            failure_reason = f"{algo}: {error}"
        elif not feasible:
            is_failure = True
            failure_reason = f"{algo}: infeasible"
        elif solver_status:
            if solver_status == "OPTIMAL":
                note = "CP-SAT optimal"
            elif solver_status == "FEASIBLE":
                note = "CP-SAT feasible ref"
            else:
                note = solver_status
        elif "CP-SAT" in name:
            note = "CP-SAT (no status)"
        else:
            note = "HEURISTIC"

        print(f"{algo:30s} {mk_str:>8s}  {status:>8s}  {elapsed:>10.4f}  {note:>20s}")

        if violations:
            for v in violations[:3]:
                print(f"  -> {v}")
            if len(violations) > 3:
                print(f"  ... and {len(violations) - 3} more violations")

        if is_failure:
            failures.append(failure_reason)
        else:
            rows.append({"algorithm": algo, "makespan": mk, "runtime_s": elapsed, "status": note})

    print()

    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All results validated through feasibility checker.")
        sys.exit(0)


if __name__ == "__main__":
    main()
