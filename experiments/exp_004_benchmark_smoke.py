"""
exp_004_benchmark_smoke.py

Phase 1 benchmark-loader smoke experiment:
- Load small benchmark-format instances from instances/
- Run selected simple baselines, strict dispatching rules, and CP-SAT
- Validate every schedule through feasibility checker
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.instance import FJSPInstance
from src.data.loader import load_benchmark_file
from src.scheduling.encoding import ScheduleResult
from src.scheduling.feasibility import check_feasibility
from src.solvers.heuristics import (
    dispatch_eft_solve,
    dispatch_spt_solve,
    fifo_solve,
    spt_solve,
)
from src.solvers.ortools_solver import ortools_solve


def run_solver(
    instance: FJSPInstance,
    name: str,
    solver_fn: Callable[[FJSPInstance], ScheduleResult],
) -> tuple[str, int | None, bool, float, str]:
    start = time.perf_counter()
    try:
        result = solver_fn(instance)
        elapsed = time.perf_counter() - start
        feasible, violations = check_feasibility(result)
        if not feasible:
            return name, result.makespan, False, elapsed, f"violations={violations}"
        note = result.solver_status or "PASS"
        return name, result.makespan, True, elapsed, note
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return name, None, False, elapsed, f"ERROR: {exc}"


def main() -> None:
    root = Path(__file__).parent.parent
    benchmark_files = [
        root / "instances" / "toy_3x3_0based.fjs",
        root / "instances" / "tiny_2x2_1based.fjs",
    ]

    solvers: list[tuple[str, Callable[[FJSPInstance], ScheduleResult]]] = [
        ("FIFO", fifo_solve),
        ("SPT", spt_solve),
        ("DispatchSPT", dispatch_spt_solve),
        ("DispatchEFT", dispatch_eft_solve),
        ("CP-SAT(tl=10s)", lambda inst: ortools_solve(inst, time_limit=10.0)),
    ]

    failures: list[str] = []
    for path in benchmark_files:
        instance = load_benchmark_file(path)
        print(f"Instance: {path.name} ({instance.num_jobs} jobs x {instance.num_machines} machines, {instance.total_ops} ops)")
        header = f"{'Algorithm':18s} {'makespan':>8s}  {'feasible':>8s}  {'runtime_s':>10s}  note"
        print(header)
        print("-" * len(header))

        for name, solver_fn in solvers:
            algo, makespan, feasible, elapsed, note = run_solver(instance, name, solver_fn)
            mk_str = str(makespan) if makespan is not None else "N/A"
            status = "PASS" if feasible else "FAIL"
            print(f"{algo:18s} {mk_str:>8s}  {status:>8s}  {elapsed:>10.4f}  {note}")
            if not feasible:
                failures.append(f"{path.name} / {algo}: {note}")
        print()

    if failures:
        print("FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        sys.exit(1)

    print("All benchmark smoke schedules passed feasibility check.")
    sys.exit(0)


if __name__ == "__main__":
    main()
