"""CP-SAT reference model for fixed / joint maintenance, minimizing total tardiness.

Each job has one start and end and an optional interval on every machine
(exactly one present). Each machine has one mandatory maintenance interval
with start in [L_i, U_i - q_i] (fixed mode: start = f_i) and NoOverlap over
its jobs and maintenance. t_j = max(0, C_j - d_j), minimize sum t_j.

Acceptance: the extracted plan must pass the checker, and with T the plan's
recomputed total tardiness, ``0 <= bound <= T <= objective`` with integral
objective and bound (presolve may relax t_j = max(0, .) to t_j >= C_j - d_j,
so a FEASIBLE objective is only an upper bound on T); OPTIMAL additionally
requires bound == T == objective. T, not the objective, is the reported metric.
"""

from __future__ import annotations

import math

from ortools.sat.python import cp_model

from fjsp_lab.maintenance.feasibility import build_plan, require_feasible, validate_problem
from fjsp_lab.maintenance.instance import ParallelMaintenanceInstance
from fjsp_lab.maintenance.schedule import MaintenanceScheduleResult


class CpSatError(RuntimeError):
    """No accepted plan could be extracted from this solver run."""


def numeric_domain_ok(data: ParallelMaintenanceInstance) -> bool:
    """Conservative bound that keeps every CP-SAT domain and aggregate exact."""
    n, m = len(data.tasks), data.num_machines
    horizon = max(item.window_end for item in data.maintenance) + sum(task.processing_time for task in data.tasks)
    return max(horizon * (4 * n * m + 4 * m + 4 * n + 1), max(task.due_date for task in data.tasks)) <= 2**50


def check_objective_metadata(status: str, objective: float, bound: float, total: int) -> None:
    """Raise CpSatError unless solver numbers are consistent with the plan's exact tardiness."""
    if status not in ('OPTIMAL', 'FEASIBLE'):
        raise CpSatError(f'CP-SAT returned {status}; no accepted schedule')
    if type(total) is not int or any(type(v) not in (int, float) or not math.isfinite(v) for v in (objective, bound)):
        raise CpSatError('Solver objective/bound must be finite and T an integer')
    if not float(objective).is_integer() or not float(bound).is_integer():
        raise CpSatError('Integer model reported a fractional objective or bound')
    if not 0 <= bound <= total <= objective:
        raise CpSatError('Solver objective/bound do not bracket the plan tardiness')
    if status == 'OPTIMAL' and not bound == total == objective:
        raise CpSatError('OPTIMAL objective/bound differ from the plan tardiness')


def solve_cpsat(data: ParallelMaintenanceInstance, *, mode: str, time_limit: float = 10.0,
                num_workers: int = 1, seed: int = 42,
                max_deterministic_time: float | None = None) -> MaintenanceScheduleResult:
    """Solve once and return a checker-accepted plan with solver status, bound and gap.

    ``max_deterministic_time`` optionally stops on CP-SAT's deterministic clock,
    which unlike wall-clock time gives repeatable single-worker runs.
    """
    validate_problem(data, mode)
    if type(time_limit) not in (int, float) or not math.isfinite(time_limit) or time_limit <= 0:
        raise ValueError('time_limit must be finite and positive')
    if max_deterministic_time is not None and (
            type(max_deterministic_time) not in (int, float)
            or not math.isfinite(max_deterministic_time) or max_deterministic_time <= 0):
        raise ValueError('max_deterministic_time must be None or finite and positive')
    if type(num_workers) is not int or not 1 <= num_workers <= 64:
        raise ValueError('num_workers must be an integer in 1..64')
    if type(seed) is not int or not 0 <= seed < 2**31:
        raise ValueError('seed must be an integer in 0..2^31-1')
    if not numeric_domain_ok(data):
        raise ValueError('Instance exceeds the supported CP-SAT numeric domain')
    m = data.num_machines
    horizon = max(item.window_end for item in data.maintenance) + sum(task.processing_time for task in data.tasks)

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
            machine_intervals[machine].append(
                model.NewOptionalIntervalVar(starts[j], task.processing_time, ends[j], active, f'p{j}_{machine}'))
        model.AddExactlyOne(choices[j, machine] for machine in range(m))
        late = model.NewIntVar(0, horizon, f't{j}')
        model.AddMaxEquality(late, [0, ends[j] - task.due_date])
        tardiness.append(late)
    for requirement in data.maintenance:
        machine = requirement.machine_id
        start = model.NewIntVar(requirement.window_start, requirement.window_end - requirement.duration, f'ms{machine}')
        end = model.NewIntVar(0, horizon, f'me{machine}')
        machine_intervals[machine].append(model.NewIntervalVar(start, requirement.duration, end, f'maintenance{machine}'))
        maintenance[machine] = start
        if mode == 'fixed':
            model.Add(start == requirement.fixed_start)
        model.AddNoOverlap(machine_intervals[machine])
    model.Minimize(sum(tardiness))
    invalid = model.Validate()
    if invalid:
        raise CpSatError(f'CP-SAT model invalid: {invalid}')

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    if max_deterministic_time is not None:
        solver.parameters.max_deterministic_time = float(max_deterministic_time)
    solver.parameters.num_search_workers = num_workers
    solver.parameters.random_seed = seed
    solver.parameters.log_search_progress = False
    status = solver.Solve(model)
    name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise CpSatError(f'CP-SAT returned {name}; no accepted schedule')
    try:
        jobs = []
        for task in data.tasks:
            selected = [machine for machine in range(m) if solver.Value(choices[task.job_id, machine]) == 1]
            if len(selected) != 1:
                raise CpSatError('Extraction did not assign exactly one machine')
            start, end = solver.Value(starts[task.job_id]), solver.Value(ends[task.job_id])
            if end - start != task.processing_time:
                raise CpSatError('Extracted production duration mismatch')
            jobs.append((task.job_id, selected[0], start))
        result = build_plan(data, jobs, [(machine, solver.Value(start)) for machine, start in maintenance.items()])
        result.solver_status = name
        result.solver_objective_value = float(solver.ObjectiveValue())
        result.solver_objective_bound = float(solver.BestObjectiveBound())
        result.solver_wall_time = float(solver.WallTime())
        total = result.total_tardiness
        check_objective_metadata(name, result.solver_objective_value, result.solver_objective_bound, total)
        result.solver_gap = (total - result.solver_objective_bound) / max(1.0, total)
        return require_feasible(result, data, mode=mode, source='CP-SAT')
    except CpSatError:
        raise
    except Exception as exc:
        raise CpSatError(f'Solution extraction/validation failed: {type(exc).__name__}: {exc}') from exc
