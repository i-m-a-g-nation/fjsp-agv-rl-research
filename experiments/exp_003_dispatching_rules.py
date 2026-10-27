"""
exp_003_dispatching_rules.py

Phase 1 strict dispatching-rule experiment:
- Run strict FIFO, SPT, EFT, MWKR, MOPNR, and Random dispatching rules on the toy instance
- Validate every result through feasibility checker
- Report makespan and runtime
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.common import (
    print_solver_runs,
    record_from_run,
    run_solver_suite,
    write_results_csv,
)
from experiments.common import experiment_output_dir
from src.data.instance import create_toy_instance
from src.scheduling.encoding import ScheduleResult
from src.solvers.heuristics import (
    dispatch_eft_solve,
    dispatch_fifo_solve,
    dispatch_mopnr_solve,
    dispatch_mwkr_solve,
    dispatch_random_solve,
    dispatch_spt_solve,
)


def main(argv=None) -> None:
    root = Path(__file__).parent.parent
    experiment_id = "exp_003_dispatching_rules"
    output_dir = experiment_output_dir(experiment_id, argv)
    instance_name = "toy_3x3"
    instance = create_toy_instance()
    print(f"Instance: {instance.num_jobs} jobs x {instance.num_machines} machines, {instance.total_ops} ops")
    print()

    solvers: list[tuple[str, Callable[[], ScheduleResult]]] = [
        ("DispatchFIFO", lambda: dispatch_fifo_solve(instance)),
        ("DispatchSPT", lambda: dispatch_spt_solve(instance)),
        ("DispatchEFT", lambda: dispatch_eft_solve(instance)),
        ("DispatchMWKR", lambda: dispatch_mwkr_solve(instance)),
        ("DispatchMOPNR", lambda: dispatch_mopnr_solve(instance)),
        ("DispatchRandom(42)", lambda: dispatch_random_solve(instance, seed=42)),
    ]

    runs = run_solver_suite(solvers, expected_instance=instance)
    print_solver_runs(runs, algorithm_width=24)

    failures = [f"{run.algorithm}: {run.note}" for run in runs if not run.feasible]
    records = [
        record_from_run(experiment_id, instance_name, run)
        for run in runs
    ]

    output_path = output_dir / f"{experiment_id}.csv"
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
