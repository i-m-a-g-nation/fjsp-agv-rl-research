"""Decoupled (sequential) baseline: plan the machines first, then the vehicles.

Stage 1 decides machine assignment and the order on every machine without
looking at the vehicles, with CP-SAT:

* ``transport_lags=False`` (D0): pure FJSP, transport ignored;
* ``transport_lags=True`` (D1): each move between machines (and from / back
  to L/U) costs its loaded travel time, as if a vehicle were always waiting
  there; no empty trips, no vehicle conflicts, no blocking, no buffers.

Stage 2 keeps that machine plan and lets CP-SAT optimize only vehicles and
times under the full model (``cpsat.solve_cpsat(machine_plan=...)``). The
difference to the joint CP-SAT on the same budget measures what decoupling
costs. A plan that cannot be executed at all (possible with blocking and
small buffers) raises ``DecoupledPlanInfeasible``; it is never repaired.
"""

from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from fjsp_lab.logistics.cpsat import LogisticsCpSatError, horizon, solve_cpsat
from fjsp_lab.logistics.instance import LogisticsInstance
from fjsp_lab.logistics.schedule import LogisticsSchedule


class DecoupledPlanInfeasible(RuntimeError):
    """Stage 2 proved that the stage 1 machine plan cannot be executed under the full model."""


@dataclass(frozen=True)
class MachinePlan:
    sequences: tuple[tuple[tuple[int, int], ...], ...]   # machine -> (job, op) in processing order
    status: str                                          # CP-SAT status of stage 1
    estimate: int                                        # stage 1 makespan (ignores vehicles)


def plan_machines(instance: LogisticsInstance, *, transport_lags: bool, time_limit: float = 30.0,
                  num_workers: int = 1, seed: int = 0) -> MachinePlan:
    """Stage 1: machine assignment and order, minimizing the stage 1 makespan."""
    production, lu = instance.production, instance.lu
    H = horizon(instance)
    model = cp_model.CpModel()
    start, end, choice, intervals = {}, {}, {}, [[] for _ in range(production.num_machines)]
    for job in production.jobs:
        for op in job.operations:
            key = (job.job_id, op.op_id)
            start[key], end[key] = model.NewIntVar(0, H, f's{key}'), model.NewIntVar(0, H, f'e{key}')
            for machine, p in op.machine_options:
                lit = choice[key, machine] = model.NewBoolVar(f'x{key}_{machine}')
                intervals[machine].append(model.NewOptionalIntervalVar(start[key], p, end[key], lit, f'i{key}_{machine}'))
            model.AddExactlyOne(choice[key, machine] for machine, _ in op.machine_options)
    for machine_intervals in intervals:
        model.AddNoOverlap(machine_intervals)
    makespan = model.NewIntVar(0, H, 'makespan')
    lag = instance.loaded_time if transport_lags else (lambda a, b: 0)
    for job in production.jobs:
        j, ops = job.job_id, job.operations
        for machine, _ in ops[0].machine_options:
            model.Add(start[j, 0] >= lag(lu, machine)).OnlyEnforceIf(choice[(j, 0), machine])
        for o in range(1, job.num_ops):
            for a, _ in ops[o - 1].machine_options:
                for b, _ in ops[o].machine_options:
                    gap = 0 if a == b else lag(a, b)
                    model.Add(start[j, o] >= end[j, o - 1] + gap).OnlyEnforceIf(
                        [choice[(j, o - 1), a], choice[(j, o), b]])
        last = job.num_ops - 1
        for machine, _ in ops[last].machine_options:
            back = lag(machine, lu) if instance.return_to_lu else 0
            model.Add(makespan >= end[j, last] + back).OnlyEnforceIf(choice[(j, last), machine])
    model.Minimize(makespan)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = num_workers
    solver.parameters.random_seed = seed
    status = solver.Solve(model)
    name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise LogisticsCpSatError(f'Stage 1 CP-SAT returned {name}', status=name)
    sequences = [[] for _ in range(production.num_machines)]
    for (key, machine), lit in choice.items():
        if solver.Value(lit):
            sequences[machine].append((solver.Value(start[key]), key))
    ordered = tuple(tuple(key for _, key in sorted(ops)) for ops in sequences)
    return MachinePlan(ordered, name, int(solver.ObjectiveValue()))


def solve_decoupled(instance: LogisticsInstance, *, transport_lags: bool = True, time_limit: float = 60.0,
                    num_workers: int = 1, seed: int = 0) -> tuple[LogisticsSchedule, MachinePlan]:
    """Both stages, each with half of ``time_limit``; the schedule's solver status is stage 2's."""
    plan = plan_machines(instance, transport_lags=transport_lags, time_limit=time_limit / 2,
                         num_workers=num_workers, seed=seed)
    try:
        schedule = solve_cpsat(instance, time_limit=time_limit / 2, num_workers=num_workers, seed=seed,
                               machine_plan=plan.sequences)
    except LogisticsCpSatError as exc:
        if exc.status == 'INFEASIBLE':
            raise DecoupledPlanInfeasible('The stage 1 machine plan cannot be executed under the full model') from exc
        raise
    return schedule, plan
