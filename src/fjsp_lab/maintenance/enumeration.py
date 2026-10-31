"""Exact brute-force oracle for tiny instances (n <= 5, m <= 3), independent of CP-SAT.

It enumerates the start of every maintenance window, machine assignments,
job orders and the positions of the maintenances in each machine sequence,
placing jobs left-shifted.
Used only to cross-check the CP-SAT model on small cases.
"""

from __future__ import annotations

from itertools import combinations_with_replacement, permutations, product
from math import prod
from time import perf_counter

from fjsp_lab.maintenance.feasibility import build_plan, require_feasible, validate_problem
from fjsp_lab.maintenance.instance import ParallelMaintenanceInstance
from fjsp_lab.maintenance.schedule import MaintenanceScheduleResult


class EnumerationLimitError(RuntimeError):
    """The complete search cannot be certified within the tiny oracle budget."""


def _place_machine(data, machine, jobs, cuts, starts):
    """Left-shifted placement of one machine's jobs with maintenance k before position cuts[k].

    Returns (records, tardiness) or None if a job would run into a maintenance.
    """
    windows = data.windows[machine]
    records, total, clock, k = [], 0, 0, 0
    for position in range(len(jobs) + 1):
        while k < len(windows) and cuts[k] == position:
            if clock > starts[k]:
                return None
            clock = starts[k] + windows[k].duration
            k += 1
        if position == len(jobs):
            break
        task = data.tasks[jobs[position]]
        records.append((task.job_id, machine, clock))
        clock += task.processing_time
        total += max(0, clock - task.due_date)
    return records, total


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
    keys = [(machine, k) for machine, windows in enumerate(data.windows) for k in range(len(windows))]
    choices = [(item.fixed_start,) if mode == 'fixed' else
               range(item.window_start, item.window_end - item.duration + 1)
               for item in (data.windows[machine][k] for machine, k in keys)]
    # itertools.product materializes its input pools before producing a state.
    # This lower bound must be checked before even entering that iterator.
    if prod(len(choice) for choice in choices) > max_states:
        raise EnumerationLimitError('Maintenance start combinations already exceed the state budget')
    started, visited = perf_counter(), 0
    best_total, best_records, best_maintenance = None, None, None
    for flat_starts in product(*choices):
        starts = [[s for (machine, _), s in zip(keys, flat_starts) if machine == i] for i in range(m)]
        for assignment in product(range(m), repeat=n):
            for order in permutations(range(n)):
                machine_jobs = [[j for j in order if assignment[j] == machine] for machine in range(m)]
                cut_options = [list(combinations_with_replacement(range(len(jobs) + 1), len(data.windows[machine])))
                               for machine, jobs in enumerate(machine_jobs)]
                for cuts in product(*cut_options):
                    visited += 1
                    if visited > max_states:
                        raise EnumerationLimitError(f'Enumeration exceeded {max_states} states; no optimal result returned')
                    records, total = [], 0
                    for machine, jobs in enumerate(machine_jobs):
                        placed = _place_machine(data, machine, jobs, cuts[machine], starts[machine])
                        if placed is None:
                            break
                        records += placed[0]
                        total += placed[1]
                    else:
                        if best_total is None or total < best_total:
                            best_total, best_records, best_maintenance = total, records, flat_starts
    if best_total is None:
        raise RuntimeError('No complete feasible enumeration result')
    result = build_plan(data, best_records, [(machine, k, s) for (machine, k), s in zip(keys, best_maintenance)])
    if result.total_tardiness != best_total:
        raise RuntimeError('Enumerated tardiness differs from independent recomputation')
    result.solver_status = 'OPTIMAL'
    result.solver_objective_value = result.solver_objective_bound = float(best_total)
    result.solver_gap, result.solver_wall_time = 0.0, perf_counter() - started
    return require_feasible(result, data, mode=mode, source='Enumeration')
