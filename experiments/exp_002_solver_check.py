"""
exp_002_solver_check.py

Phase 1 solver comparison experiment:
- Run heuristics and OR-Tools CP-SAT on toy instance
- Compare makespan, feasibility, runtime, solver_status
- All results must pass feasibility checker
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.common import record_from_run, run_solver_once, write_results_csv
from src.data.instance import create_toy_instance
from src.solvers.heuristics import (
    fifo_solve,
    spt_solve,
    earliest_finish_time_solve,
    random_solve,
)
from src.solvers.ortools_solver import ortools_solve


def main() -> None:
    root = Path(__file__).parent.parent
    experiment_id = "exp_002_solver_check"
    instance_name = "toy_3x3"
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

    records = []
    failures: list[str] = []

    for name, fn in solvers:
        run = run_solver_once(name, fn)
        note = "HEURISTIC"
        if run.error:
            note = f"ERROR: {run.error[:40]}"
            failures.append(f"{run.algorithm}: {run.error}")
        elif not run.feasible:
            note = run.note
            failures.append(f"{run.algorithm}: infeasible")
        elif run.result is not None and run.result.solver_status == "OPTIMAL":
            note = "CP-SAT optimal"
        elif run.result is not None and run.result.solver_status == "FEASIBLE":
            note = "CP-SAT feasible ref"
        elif "CP-SAT" in name:
            note = "CP-SAT (no status)"

        mk_str = str(run.makespan) if run.makespan is not None else "N/A"
        status = "PASS" if run.feasible else "FAIL"
        print(f"{run.algorithm:30s} {mk_str:>8s}  {status:>8s}  {run.runtime_s:>10.4f}  {note:>20s}")
        records.append(record_from_run(experiment_id, instance_name, run, note=note))

    print()

    csv_path = root / "experiments" / "results" / f"{experiment_id}.csv"
    write_results_csv(csv_path, records)
    print(f"CSV results written to: {csv_path}")
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
