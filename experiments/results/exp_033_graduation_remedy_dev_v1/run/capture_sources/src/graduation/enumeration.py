"""Bounded exact tiny-instance oracle, independent of CP-SAT modeling."""

from itertools import permutations, product
from math import prod
from time import perf_counter

from src.graduation.data import ParallelMaintenanceInstance, to_fjsp_instance
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.result import MaintenanceRecord, MaintenanceScheduleResult


class EnumerationLimitError(RuntimeError):
    """The complete search cannot be certified within the tiny oracle budget."""


def enumerate_parallel_maintenance(data: ParallelMaintenanceInstance, *, mode: str,
                                   max_states: int = 200000) -> MaintenanceScheduleResult:
    if not isinstance(data, ParallelMaintenanceInstance) or mode not in ('fixed', 'joint'):
        raise ValueError('Expected typed G1 data and explicit fixed/joint mode')
    if mode == 'fixed' and any(item.fixed_start is None for item in data.maintenance):
        raise ValueError('fixed mode requires fixed_start for every machine')
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
                            records.append((j, machine, clock, task.processing_time))
                            total += max(0, end - task.due_date)
                            clock = end
                        if not valid:
                            break
                    if valid and (best_total is None or total < best_total):
                        best_total, best_records, best_maintenance = total, records, maintenance_starts
    if best_total is None:
        raise RuntimeError('No complete feasible enumeration result')
    result = MaintenanceScheduleResult(instance=to_fjsp_instance(data), total_tardiness=best_total,
        solver_status='OPTIMAL', solver_objective_value=float(best_total), solver_objective_bound=float(best_total),
        solver_gap=0.0, solver_wall_time=perf_counter() - started)
    for j, machine, start, duration in best_records:
        result.add_record(j, 0, machine, start, duration)
    result.maintenance_records = [MaintenanceRecord(machine, start, start + data.maintenance[machine].duration,
        data.maintenance[machine].duration) for machine, start in enumerate(best_maintenance)]
    result.compute_makespan()
    accepted, issues = check_parallel_maintenance_feasibility(result, data, mode=mode)
    if not accepted:
        raise RuntimeError(f'Independent enumeration result rejected: {issues}')
    return result
