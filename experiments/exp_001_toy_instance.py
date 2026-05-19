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

from src.data.instance import create_toy_instance
from src.scheduling.feasibility import check_feasibility
from src.solvers.heuristics import (
    fifo_solve,
    spt_solve,
    earliest_finish_time_solve,
    random_solve,
)
from src.vis.gantt import plot_gantt


def main() -> None:
    instance = create_toy_instance()
    print(f"Instance: {instance.num_jobs} jobs x {instance.num_machines} machines, {instance.total_ops} ops")
    print()

    results: dict[str, int] = {}
    all_results: list = []

    methods = [
        ("FIFO", lambda: fifo_solve(instance)),
        ("SPT", lambda: spt_solve(instance)),
        ("EarliestFinishTime", lambda: earliest_finish_time_solve(instance)),
    ]
    for seed in [42, 123, 999]:
        methods.append((f"Random(s={seed})", lambda s=seed: random_solve(instance, seed=s)))

    for name, solver_fn in methods:
        result = solver_fn()
        feasible, violations = check_feasibility(result)
        status = "PASS" if feasible else "FAIL"
        print(f"  {name:25s}  makespan={result.makespan:3d}  feasible={status}")
        if not feasible:
            for v in violations:
                print(f"    VIOLATION: {v}")
        results[name] = result.makespan
        all_results.append((name, result, feasible))

    print()
    best_name, best_result, _ = min(all_results, key=lambda x: x[1].makespan)
    print(f"Best: {best_name} with makespan = {best_result.makespan}")
    print()

    failed = [name for name, _, f in all_results if not f]
    if failed:
        print(f"FAILED: {failed}")
        sys.exit(1)
    else:
        print("All schedules passed feasibility check.")

    from datetime import datetime
    output_dir = Path(__file__).parent
    save_path = output_dir / "exp_001_gantt_latest.png"
    plot_gantt(best_result, title=f"Best Schedule: {best_name} (makespan={best_result.makespan})",
               save_path=str(save_path))
    print(f"Gantt chart saved to: {save_path}")


if __name__ == "__main__":
    main()
