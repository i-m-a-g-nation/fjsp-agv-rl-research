"""Exact brute-force oracle for tiny instances (n <= 5, m <= 3), independent of CP-SAT.

It enumerates maintenance starts, machine assignments, job orders and the
position of maintenance in each machine sequence, placing jobs left-shifted.
Used only to cross-check the CP-SAT model on small cases.
"""

from __future__ import annotations

from itertools import permutations, product
from math import prod
from time import perf_counter

from fjsp_lab.maintenance.feasibility import build_plan, require_feasible, validate_problem
from fjsp_lab.maintenance.instance import ParallelMaintenanceInstance
from fjsp_lab.maintenance.schedule import MaintenanceScheduleResult


class EnumerationLimitError(RuntimeError):
    """The complete search cannot be certified within the tiny oracle budget."""


def enumerate_parallel_maintenance(data: ParallelMaintenanceInstance, *, mode: str,
                                   max_states: int = 200000) -> MaintenanceScheduleResult:
    validate_problem(data, mode)
    if type(max_states) is not int or not 1 <= max_states <= 200000:
        raise ValueError('max_states must be an integer in 1..200000')
    n, m = len(data.tasks), data.num_machines
    if n > 5 or m > 3:
        raise EnumerationLimitError('Exact oracle supports at most 5 tasks and 3 machines')
    horizon = max(item.window_end for item in data.maintenance) + sum(task.processing_time for task in data.tasks)
    if max(n*horizon, max(task.due_date for task in data.tasks)) > 2**50:
        raise ValueError('Instance exceeds the tiny oracle numeric domain')
    windows = [(item.fixed_start,) if mode == 'fixed' else
               range(item.window_start, item.window_end - item.duration + 1) for item in data.maintenance]
    # itertools.product materializes its input pools before producing a state.
    # This lower bound must be checked before even entering that iterator.
    if prod(len(window) for window in windows) > max_states:
        raise EnumerationLimitError('Maintenance start combinations already exceed the state budget')
    started, visited = perf_counter(), 0
    best_total, best_records, best_maintenance = None, None, None
    for maintenance_starts in product(*windows):
        for assignment in product(range(m), repeat=n):
            for order in permutations(range(n)):
                machine_jobs = [[j for j in order if assignment[j] == machine] for machine in range(m)]
                for cuts in product(*(range(len(jobs) + 1) for jobs in machine_jobs)):
                    visited += 1
                    if visited > max_states:
                        raise EnumerationLimitError(f'Enumeration exceeded {max_states} states; no optimal result returned')
                    records, total, valid = [], 0, True
                    for machine, jobs in enumerate(machine_jobs):
                        clock = 0
                        maintenance_start = maintenance_starts[machine]
                        for position, j in enumerate(jobs):
                            if position == cuts[machine]:
                                clock = maintenance_start + data.maintenance[machine].duration
                            task = data.tasks[j]
                            end = clock + task.processing_time
                            if position < cuts[machine] and end > maintenance_start:
                                valid = False
                                break
                            records.append((j, machine, clock))
                            total += max(0, end - task.due_date)
                            clock = end
                        if not valid:
                            break
                    if valid and (best_total is None or total < best_total):
                        best_total, best_records, best_maintenance = total, records, maintenance_starts
    if best_total is None:
        raise RuntimeError('No complete feasible enumeration result')
    result = build_plan(data, best_records, enumerate(best_maintenance))
    if result.total_tardiness != best_total:
        raise RuntimeError('Enumerated tardiness differs from independent recomputation')
    result.solver_status = 'OPTIMAL'
    result.solver_objective_value = result.solver_objective_bound = float(best_total)
    result.solver_gap, result.solver_wall_time = 0.0, perf_counter() - started
    return require_feasible(result, data, mode=mode, source='Enumeration')
