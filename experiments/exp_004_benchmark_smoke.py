"""
exp_004_benchmark_smoke.py

Phase 1 benchmark-loader smoke experiment:
- Load small benchmark-format instances from instances/
- Run selected simple baselines, strict dispatching rules, and CP-SAT
- Validate every schedule through feasibility checker
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
from src.data.instance import FJSPInstance
from src.data.loader import load_project_benchmark_file as load_benchmark_file
from src.scheduling.encoding import ScheduleResult
from src.solvers.heuristics import (
    dispatch_eft_solve,
    dispatch_mopnr_solve,
    dispatch_mwkr_solve,
    dispatch_spt_solve,
    earliest_available_machine_solve,
    fifo_solve,
    spt_solve,
)
from src.solvers.ortools_solver import ortools_solve


def main(argv=None) -> None:
    root = Path(__file__).parent.parent
    experiment_id = "exp_004_benchmark_smoke"
    output_dir = experiment_output_dir(experiment_id, argv)
    benchmark_files = [
        root / "instances" / "toy_3x3_0based.fjs",
        root / "instances" / "tiny_2x2_1based.fjs",
    ]

    solvers: list[tuple[str, Callable[[FJSPInstance], ScheduleResult]]] = [
        ("FIFO", fifo_solve),
        ("SPT", spt_solve),
        ("EarliestAvailableMachine", earliest_available_machine_solve),
        ("DispatchSPT", dispatch_spt_solve),
        ("DispatchEFT", dispatch_eft_solve),
        ("DispatchMWKR", dispatch_mwkr_solve),
        ("DispatchMOPNR", dispatch_mopnr_solve),
        ("CP-SAT(tl=10s)", lambda inst: ortools_solve(inst, time_limit=10.0)),
    ]

    failures: list[str] = []
    records = []
    for path in benchmark_files:
        instance = load_benchmark_file(path)
        print(f"Instance: {path.name} ({instance.num_jobs} jobs x {instance.num_machines} machines, {instance.total_ops} ops)")
        instance_solvers = [
            (name, lambda fn=solver_fn, inst=instance: fn(inst))
            for name, solver_fn in solvers
        ]
        runs = run_solver_suite(instance_solvers, expected_instance=instance)
        print_solver_runs(runs, algorithm_width=18)

        records.extend(
            record_from_run(experiment_id, path.name, run)
            for run in runs
        )
        failures.extend(
            f"{path.name} / {run.algorithm}: {run.note}"
            for run in runs
            if not run.feasible
        )
        print()

    output_path = output_dir / f"{experiment_id}.csv"
    write_results_csv(output_path, records)
    print(f"CSV results written to: {output_path}")

    if failures:
        print("FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        sys.exit(1)

    print("All benchmark smoke schedules passed feasibility check.")
    sys.exit(0)


if __name__ == "__main__":
    main()
