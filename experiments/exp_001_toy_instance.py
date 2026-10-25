"""
exp_001_toy_instance.py

Phase 1 toy instance experiment:
- Create toy 3x3 FJSP instance
- Run all heuristic baselines: FIFO, SPT, EFT, Random(x3)
- Validate all results through feasibility checker
- Report makespan comparison
- Generate Gantt chart for best result
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.common import record_from_run, run_solver_once, write_results_csv
from src.data.instance import create_toy_instance
from src.solvers.heuristics import (
    earliest_available_machine_solve,
    fifo_solve,
    spt_solve,
    earliest_finish_time_solve,
    random_solve,
)
from src.vis.gantt import plot_gantt


def main() -> None:
    root = Path(__file__).parent.parent
    experiment_id = "exp_001_toy_instance"
    instance_name = "toy_3x3"
    instance = create_toy_instance()
    print(f"Instance: {instance.num_jobs} jobs x {instance.num_machines} machines, {instance.total_ops} ops")
    print()

    results: dict[str, int] = {}
    all_results: list = []
    records = []

    methods = [
        ("FIFO", lambda: fifo_solve(instance)),
        ("SPT", lambda: spt_solve(instance)),
        ("EarliestAvailableMachine", lambda: earliest_available_machine_solve(instance)),
        ("EarliestFinishTime", lambda: earliest_finish_time_solve(instance)),
    ]
    for seed in [42, 123, 999]:
        methods.append((f"Random(s={seed})", lambda s=seed: random_solve(instance, seed=s)))

    for name, solver_fn in methods:
        run = run_solver_once(name, solver_fn)
        if run.result is None:
            print(f"  {name:25s}  makespan=N/A  feasible=FAIL")
            records.append(record_from_run(experiment_id, instance_name, run))
            all_results.append((name, None, False))
            continue
        result = run.result
        status = "PASS" if run.feasible else "FAIL"
        print(f"  {name:25s}  makespan={result.makespan:3d}  feasible={status}")
        if not run.feasible:
            print(f"    {run.note}")
        records.append(record_from_run(experiment_id, instance_name, run))
        results[name] = result.makespan
        all_results.append((name, result, run.feasible))

    print()
    successful_results = [item for item in all_results if item[1] is not None and item[2]]
    failed = [name for name, _, f in all_results if not f]

    csv_path = root / "experiments" / "results" / f"{experiment_id}.csv"
    write_results_csv(csv_path, records)
    print(f"CSV results written to: {csv_path}")

    if failed:
        print(f"FAILED: {failed}")
        sys.exit(1)

    best_name, best_result, _ = min(successful_results, key=lambda x: x[1].makespan)
    print(f"Best: {best_name} with makespan = {best_result.makespan}")
    print()
    print("All schedules passed feasibility check.")

    output_dir = Path(__file__).parent
    save_path = output_dir / "exp_001_gantt_latest.png"
    plot_gantt(best_result, title=f"Best Schedule: {best_name} (makespan={best_result.makespan})",
               save_path=str(save_path))
    print(f"Gantt chart saved to: {save_path}")


if __name__ == "__main__":
    main()
