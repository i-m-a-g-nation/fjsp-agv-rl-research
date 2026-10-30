"""Fixed/joint maintenance CP-SAT reference with an upper-bound objective rule.

The model is identical to ``solver.py``. Only result acceptance differs:

* ``solver.py`` requires the reported objective to equal the returned plan's
  exact total tardiness. In the G3A main batch 5 of 480 FEASIBLE solves broke
  this (e.g. objective 88, plan 86; exp_030/exp_031), failing the whole batch.
* Presolve may relax ``t_j = max(0, C_j - d_j)`` to ``t_j >= C_j - d_j``, which
  is exact only at an optimum. A probe with that inequality written explicitly
  returned slack ``t_j`` and the same objectives (88/109/159/423/63) while the
  plans' exact tardiness stayed 86/106/141/422/61. A FEASIBLE objective is
  therefore an upper bound on the returned plan's exact tardiness.

So a result is accepted when the plan passes the G1 checker and
``0 <= bound <= T <= objective`` with integral objective and bound, where T is
recomputed from the plan. OPTIMAL additionally requires ``bound == T ==
objective``. T, not the objective, is the reported metric.

``solver.py`` and ``graduation_backend._checked_metrics`` stay byte-identical
because archived evidence (exp_025/026 references, exp_030/031/033 replays)
binds their SHA-256.
"""

import math

from ortools.sat.python import cp_model

from src.graduation.data import ParallelMaintenanceInstance, to_fjsp_instance
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.metrics import calculate_total_tardiness
from src.graduation.result import MaintenanceRecord, MaintenanceScheduleResult
from src.graduation.solver import GraduationSolverError

# Same fields as graduation_backend.METRICS (a test keeps them equal); defined
# here so the solver does not import the LangGraph/FAISS workflow package.
METRICS = ('makespan', 'total_tardiness', 'solver_status', 'solver_objective_value',
           'solver_objective_bound', 'solver_gap', 'solver_wall_time')


def check_objective_metadata(status: str, objective: float, bound: float, total: int) -> None:
    """Raise unless solver numbers are consistent with the plan's exact tardiness."""
    if status not in ('OPTIMAL', 'FEASIBLE'):
        raise GraduationSolverError(f'CP-SAT returned {status}; no accepted schedule')
    if (type(total) is not int or any(type(v) not in (int, float) or not math.isfinite(v)
                                      for v in (objective, bound))):
        raise GraduationSolverError('Solver objective/bound must be finite and T an integer')
    if not float(objective).is_integer() or not float(bound).is_integer():
        raise GraduationSolverError('Integer model reported a fractional objective or bound')
    if not 0 <= bound <= total <= objective:
        raise GraduationSolverError('Solver objective/bound do not bracket the plan tardiness')
    if status == 'OPTIMAL' and not bound == total == objective:
        raise GraduationSolverError('OPTIMAL objective/bound differ from the plan tardiness')


def solve_parallel_maintenance_v2(data: ParallelMaintenanceInstance, *, mode: str,
                                  time_limit: float = 10.0, num_workers: int = 1, seed: int = 42,
                                  max_deterministic_time: float | None = None) -> MaintenanceScheduleResult:
    """Solve once; return only a checker-accepted plan with T as the metric.

    ``max_deterministic_time`` optionally stops on CP-SAT's deterministic clock,
    which unlike wall-clock time gives repeatable single-worker runs.
    """
    if not isinstance(data, ParallelMaintenanceInstance) or mode not in ('fixed', 'joint'):
        raise ValueError('Expected typed G1 data and explicit fixed/joint mode')
    if mode == 'fixed' and any(item.fixed_start is None for item in data.maintenance):
        raise ValueError('fixed mode requires fixed_start for every machine')
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
    n, m = len(data.tasks), data.num_machines
    horizon = max(item.window_end for item in data.maintenance) + sum(task.processing_time for task in data.tasks)
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
    if max_deterministic_time is not None:
        solver.parameters.max_deterministic_time = float(max_deterministic_time)
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
        total = result.total_tardiness = calculate_total_tardiness(data, result)
        check_objective_metadata(name, result.solver_objective_value, result.solver_objective_bound, total)
        result.solver_gap = (total - result.solver_objective_bound) / max(1.0, total)
        accepted, issues = check_parallel_maintenance_feasibility(result, data, mode=mode)
        if not accepted:
            raise GraduationSolverError(f'Extracted schedule rejected: {issues}')
        return result
    except GraduationSolverError:
        raise
    except Exception as exc:
        raise GraduationSolverError(f'Solution extraction/validation failed: {type(exc).__name__}: {exc}') from exc


def checked_metrics_v2(data: ParallelMaintenanceInstance, result: MaintenanceScheduleResult, mode: str) -> dict:
    """Recheck a saved v2 result: plan legality, exact T and the upper-bound rule."""
    accepted, issues = check_parallel_maintenance_feasibility(result, data, mode=mode)
    if not accepted:
        raise ValueError(f'Graduation domain rejected schedule: {issues}')
    values = {field: getattr(result, field) for field in METRICS}
    try:
        check_objective_metadata(values['solver_status'], values['solver_objective_value'],
                                 values['solver_objective_bound'], values['total_tardiness'])
    except GraduationSolverError as exc:
        raise ValueError(str(exc)) from exc
    gap, elapsed = values['solver_gap'], values['solver_wall_time']
    expected_gap = (values['total_tardiness'] - values['solver_objective_bound']) / max(1.0, values['total_tardiness'])
    if (type(gap) not in (int, float) or type(elapsed) not in (int, float) or not math.isfinite(elapsed)
            or elapsed < 0 or not math.isclose(gap, expected_gap, rel_tol=0, abs_tol=1e-12)):
        raise ValueError('Saved gap or wall time disagrees with the plan tardiness')
    return values
