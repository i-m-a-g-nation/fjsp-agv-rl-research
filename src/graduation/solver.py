"""Small fixed/joint maintenance CP-SAT reference; objective is total tardiness."""

import math

from ortools.sat.python import cp_model

from src.graduation.data import ParallelMaintenanceInstance, to_fjsp_instance
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.metrics import calculate_total_tardiness
from src.graduation.result import MaintenanceRecord, MaintenanceScheduleResult


class GraduationSolverError(RuntimeError):
    """No accepted schedule can be extracted from this solver run."""


def solve_parallel_maintenance(data: ParallelMaintenanceInstance, *, mode: str,
                               time_limit: float = 10.0, num_workers: int = 1,
                               seed: int = 42) -> MaintenanceScheduleResult:
    if not isinstance(data, ParallelMaintenanceInstance) or mode not in ('fixed', 'joint'):
        raise ValueError('Expected typed G1 data and explicit fixed/joint mode')
    if mode == 'fixed' and any(item.fixed_start is None for item in data.maintenance):
        raise ValueError('fixed mode requires fixed_start for every machine')
    if type(time_limit) not in (int, float) or not math.isfinite(time_limit) or time_limit <= 0:
        raise ValueError('time_limit must be finite and positive')
    if type(num_workers) is not int or not 1 <= num_workers <= 64:
        raise ValueError('num_workers must be an integer in 1..64')
    if type(seed) is not int or not 0 <= seed < 2**31:
        raise ValueError('seed must be an integer in 0..2^31-1')
    n, m = len(data.tasks), data.num_machines
    horizon = max(item.window_end for item in data.maintenance) + sum(task.processing_time for task in data.tasks)
    # Conservative domain/aggregate limit also keeps integer objectives exactly
    # representable by the solver's floating-point diagnostic API.
    if max(horizon * (4*n*m + 4*m + 4*n + 1), max(task.due_date for task in data.tasks)) > 2**50:
        raise ValueError('Instance exceeds the supported CP-SAT numeric domain')

    model = cp_model.CpModel()
    starts, ends, choices, machine_intervals, maintenance = {}, {}, {}, [[] for _ in range(m)], {}
    tardiness = []
    for task in data.tasks:
        j = task.job_id
        starts[j] = model.NewIntVar(0, horizon, f's{j}')
        ends[j] = model.NewIntVar(0, horizon, f'e{j}')
        for machine in range(m):
            active = model.NewBoolVar(f'x{j}_{machine}')
            choices[j, machine] = active
            interval = model.NewOptionalIntervalVar(starts[j], task.processing_time, ends[j], active, f'p{j}_{machine}')
            machine_intervals[machine].append(interval)
        model.AddExactlyOne(choices[j, machine] for machine in range(m))
        late = model.NewIntVar(0, horizon, f't{j}')
        model.AddMaxEquality(late, [0, ends[j] - task.due_date])
        tardiness.append(late)
    for requirement in data.maintenance:
        machine = requirement.machine_id
        start = model.NewIntVar(requirement.window_start, requirement.window_end - requirement.duration, f'ms{machine}')
        end = model.NewIntVar(0, horizon, f'me{machine}')
        interval = model.NewIntervalVar(start, requirement.duration, end, f'maintenance{machine}')
        machine_intervals[machine].append(interval)
        maintenance[machine] = (start, end)
        if mode == 'fixed':
            model.Add(start == requirement.fixed_start)
        model.AddNoOverlap(machine_intervals[machine])
    model.Minimize(sum(tardiness))
    invalid = model.Validate()
    if invalid:
        raise GraduationSolverError(f'CP-SAT model invalid: {invalid}')
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = num_workers
    solver.parameters.random_seed = seed
    solver.parameters.log_search_progress = False
    status = solver.Solve(model)
    name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise GraduationSolverError(f'CP-SAT returned {name}; no accepted schedule')
    try:
        result = MaintenanceScheduleResult(instance=to_fjsp_instance(data), solver_status=name,
            solver_objective_value=float(solver.ObjectiveValue()),
            solver_objective_bound=float(solver.BestObjectiveBound()), solver_wall_time=float(solver.WallTime()))
        for task in data.tasks:
            selected = [machine for machine in range(m) if solver.Value(choices[task.job_id, machine]) == 1]
            if len(selected) != 1:
                raise GraduationSolverError('Extraction did not assign exactly one machine')
            start, end = solver.Value(starts[task.job_id]), solver.Value(ends[task.job_id])
            if end - start != task.processing_time:
                raise GraduationSolverError('Extracted production duration mismatch')
            result.add_record(task.job_id, 0, selected[0], start, task.processing_time)
        result.maintenance_records = [MaintenanceRecord(machine, solver.Value(start), solver.Value(end),
            data.maintenance[machine].duration) for machine, (start, end) in maintenance.items()]
        result.compute_makespan()
        result.total_tardiness = calculate_total_tardiness(data, result)
        objective, bound = result.solver_objective_value, result.solver_objective_bound
        if (not math.isfinite(objective) or objective != result.total_tardiness
                or not math.isfinite(bound) or not 0 <= bound <= objective):
            raise GraduationSolverError('Solver objective/bound disagrees with independent total tardiness')
        result.solver_gap = (objective - bound) / max(1.0, objective)
        accepted, issues = check_parallel_maintenance_feasibility(result, data, mode=mode)
        if not accepted:
            raise GraduationSolverError(f'Extracted schedule rejected: {issues}')
        return result
    except GraduationSolverError:
        raise
    except Exception as exc:
        raise GraduationSolverError(f'Solution extraction/validation failed: {type(exc).__name__}: {exc}') from exc
