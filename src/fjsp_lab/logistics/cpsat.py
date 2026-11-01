"""CP-SAT reference model of the L1 logistics problem (small instances only).

Per operation: start/end and one optional processing choice per eligible
machine (exactly one present). Per job and leg (operation it is carried to,
plus the trip back to L/U when required): dispatch, pickup, delivery and a
literal ``needed`` = the machine differs from the previous one. A trip that is
not needed is pinned to the end of the previous operation and has zero length.

Vehicles: each vehicle routes its trips in one ``AddCircuit`` (depot = its
start at L/U); an arc t -> u forces u's dispatch after t's delivery and u's
pickup after the empty trip from t's destination to u's origin.

Blocking: an operation occupies its machine from its start until the job is
picked up (or, if it stays, until its next operation starts); occupations
never overlap on a machine. Without blocking only processing occupies it.
Buffers: from the dispatch of the inbound trip until the machine releases the
job (without blocking: until the operation ends, or the next operation starts
if the job stays), the job uses one of the 1 + B places of the station
(cumulative). Objective: minimize the makespan of docs/models/logistics_model_zh.md.

With ``machine_plan`` (the ordered operations of every machine) the machine
choices and orders are fixed and only vehicles and times are optimized: the
second stage of the decoupled baseline in ``logistics.decoupled``.

Only OPTIMAL is called optimal; FEASIBLE is a time-limited reference. The
extracted schedule must pass the logistics checker.
"""

from __future__ import annotations

import math
from typing import Sequence

from ortools.sat.python import cp_model

from fjsp_lab.fjsp.schedule import ScheduleRecord, ScheduleResult
from fjsp_lab.logistics.feasibility import logistics_makespan, require_feasible
from fjsp_lab.logistics.instance import LogisticsInstance
from fjsp_lab.logistics.schedule import LogisticsSchedule, TransportRecord

MachinePlan = Sequence[Sequence[tuple[int, int]]]     # machine -> its operations (job, op) in order


class LogisticsCpSatError(RuntimeError):
    """No accepted schedule could be extracted from this solver run (``status``: solver status, if any)."""

    def __init__(self, message: str, status: str | None = None):
        super().__init__(message)
        self.status = status


def horizon(instance: LogisticsInstance) -> int:
    """Makespan of the serial schedule (one job and one trip at a time), an upper bound on the optimum."""
    longest = max(max(row) for row in instance.travel)
    work = sum(max(p for _, p in op.machine_options) for job in instance.production.jobs for op in job.operations)
    trips = sum(job.num_ops + int(instance.return_to_lu) for job in instance.production.jobs)
    return work + trips * (2 * longest + instance.handling_time)


def solve_cpsat(instance: LogisticsInstance, *, time_limit: float = 10.0, num_workers: int = 1,
                seed: int = 0, machine_plan: MachinePlan | None = None) -> LogisticsSchedule:
    """Solve once; return the checker-accepted schedule with solver status and bound."""
    if not isinstance(instance, LogisticsInstance):
        raise ValueError('Expected a LogisticsInstance')
    if machine_plan is not None:
        planned = [(op, machine) for machine, ops in enumerate(machine_plan) for op in ops]
        if (len(machine_plan) != instance.num_machines or len(planned) != instance.production.total_ops
                or len({op for op, _ in planned}) != len(planned)
                or not all(instance.production.is_machine_eligible(*op, machine) for op, machine in planned)):
            raise ValueError('machine_plan must list every operation once, on an eligible machine')
    if type(time_limit) not in (int, float) or not math.isfinite(time_limit) or time_limit <= 0:
        raise ValueError('time_limit must be finite and positive')
    production, lu = instance.production, instance.lu
    m, size = production.num_machines, production.num_machines + 1
    H = horizon(instance)
    flat_travel = [instance.travel[a][b] for a in range(size) for b in range(size)]
    model = cp_model.CpModel()

    def travel_between(origin, destination, name: str) -> cp_model.IntVar:
        """travel[origin][destination] for fixed locations or location variables."""
        if isinstance(origin, int) and isinstance(destination, int):
            return model.NewConstant(instance.travel[origin][destination])
        index = model.NewIntVar(0, size * size - 1, f'i_{name}')
        model.Add(index == origin * size + destination)
        value = model.NewIntVar(0, max(flat_travel), name)
        model.AddElement(index, flat_travel, value)
        return value

    start, end, choice, location = {}, {}, {}, {}
    for job in production.jobs:
        for op in job.operations:
            key = (job.job_id, op.op_id)
            start[key], end[key] = model.NewIntVar(0, H, f's{key}'), model.NewIntVar(0, H, f'e{key}')
            for machine, p in op.machine_options:
                lit = model.NewBoolVar(f'x{key}_{machine}')
                choice[key, machine] = lit
                model.Add(end[key] == start[key] + p).OnlyEnforceIf(lit)
            model.AddExactlyOne(choice[key, machine] for machine, _ in op.machine_options)
            location[key] = model.NewIntVar(0, m - 1, f'loc{key}')
            model.Add(location[key] == sum(machine * choice[key, machine] for machine, _ in op.machine_options))
            if op.op_id > 0:
                model.Add(start[key] >= end[job.job_id, op.op_id - 1])
    if machine_plan is not None:
        for machine, ops in enumerate(machine_plan):
            for key in ops:
                model.Add(choice[key, machine] == 1)

    # Trips.
    trips = []                       # (job, leg, needed, origin_var_or_int, destination_var_or_int, D, P, Q)
    for job in production.jobs:
        j, n = job.job_id, job.num_ops
        for leg in range(n + int(instance.return_to_lu)):
            origin = lu if leg == 0 else location[j, leg - 1]
            destination = lu if leg == n else location[j, leg]
            needed = model.NewBoolVar(f'need{j}_{leg}')
            if leg == 0 or leg == n:
                model.Add(needed == 1)
            else:
                model.Add(location[j, leg] != location[j, leg - 1]).OnlyEnforceIf(needed)
                model.Add(location[j, leg] == location[j, leg - 1]).OnlyEnforceIf(needed.Not())
            D, P, Q = (model.NewIntVar(0, H, f'{name}{j}_{leg}') for name in 'dpq')
            loaded = model.NewIntVar(0, H, f'load{j}_{leg}')
            raw = travel_between(origin, destination, f'raw{j}_{leg}')
            model.Add(loaded == raw + instance.handling_time).OnlyEnforceIf(needed)
            model.Add(loaded == 0).OnlyEnforceIf(needed.Not())
            model.Add(Q == P + loaded)
            model.Add(D <= P)
            ready = 0 if leg == 0 else end[j, leg - 1]
            model.Add(P >= ready)
            model.Add(P == ready).OnlyEnforceIf(needed.Not())
            model.Add(D == P).OnlyEnforceIf(needed.Not())
            if leg < n:
                model.Add(start[j, leg] >= Q)
            trips.append((j, leg, needed, origin, destination, D, P, Q))

    # Vehicles: one circuit each over its trips; node 0 is the depot (L/U at time 0).
    # Empty travel between two trips depends on the machines chosen, not on the vehicle.
    empty_between = {(t, u): travel_between(trips[t - 1][4], trips[u - 1][3], f'empty{t}_{u}')
                     for t in range(1, len(trips) + 1) for u in range(1, len(trips) + 1) if t != u}
    assigned = {}
    for v in range(instance.num_vehicles):
        arcs = [(0, 0, model.NewBoolVar(f'idle{v}'))]
        for t, trip in enumerate(trips, start=1):
            lit = model.NewBoolVar(f'a{t}_{v}')
            assigned[t, v] = lit
            arcs.append((t, t, lit.Not()))
        for t, (_, _, _, origin, _, D, P, _) in enumerate(trips, start=1):
            first = model.NewBoolVar(f'first{t}_{v}')
            arcs += [(0, t, first), (t, 0, model.NewBoolVar(f'last{t}_{v}'))]
            model.Add(P >= D + travel_between(lu, origin, f'empty0_{t}_{v}')).OnlyEnforceIf(first)
        for t, (_, _, _, _, destination, _, _, Q) in enumerate(trips, start=1):
            for u, (_, _, _, origin, _, D, P, _) in enumerate(trips, start=1):
                if t == u:
                    continue
                lit = model.NewBoolVar(f'arc{t}_{u}_{v}')
                arcs.append((t, u, lit))
                model.Add(D >= Q).OnlyEnforceIf(lit)
                model.Add(P >= D + empty_between[t, u]).OnlyEnforceIf(lit)
        model.AddCircuit(arcs)
    for t, (_, _, needed, *_rest) in enumerate(trips, start=1):
        model.Add(sum(assigned[t, v] for v in range(instance.num_vehicles)) == needed)

    # Blocking and buffers.
    trip_of = {(j, leg): trip for j, leg, *trip in trips}
    occupation, places, freed_at = [[] for _ in range(m)], [[] for _ in range(m)], {}
    for job in production.jobs:
        j, n = job.job_id, job.num_ops
        for o in range(n):
            needed_in, _, _, D_in, _, _ = trip_of[j, o]
            reserve = model.NewIntVar(0, H, f'r{j}_{o}')
            model.Add(reserve == D_in).OnlyEnforceIf(needed_in)
            model.Add(reserve == start[j, o]).OnlyEnforceIf(needed_in.Not())
            release = model.NewIntVar(0, H, f'l{j}_{o}')          # end of the station place
            if o + 1 < n or instance.return_to_lu:
                needed_out, _, _, _, P_out, _ = trip_of[j, o + 1]
                after = start[j, o + 1] if o + 1 < n else end[j, o]
                model.Add(release == (P_out if instance.blocking else end[j, o])).OnlyEnforceIf(needed_out)
                model.Add(release == after).OnlyEnforceIf(needed_out.Not())
            else:
                model.Add(release == end[j, o])
            freed = release if instance.blocking else end[j, o]   # end of the machine occupation
            freed_at[j, o] = freed
            for machine, _ in job.operations[o].machine_options:
                lit = choice[(j, o), machine]
                hold = model.NewIntVar(0, H, f'h{j}_{o}_{machine}')
                occupation[machine].append(model.NewOptionalIntervalVar(start[j, o], hold, freed, lit, f'm{j}_{o}_{machine}'))
                if instance.station_capacity(machine) is not None:
                    stay = model.NewIntVar(0, H, f'b{j}_{o}_{machine}')
                    places[machine].append(model.NewOptionalIntervalVar(reserve, stay, release, lit, f'b{j}_{o}_{machine}'))
    if machine_plan is not None:                                    # keep each machine's order
        for ops in machine_plan:
            for a, b in zip(ops, ops[1:]):
                model.Add(start[b] >= freed_at[a])
    for machine in range(m):
        model.AddNoOverlap(occupation[machine])
        if places[machine]:
            model.AddCumulative(places[machine], [1] * len(places[machine]), instance.station_capacity(machine))

    makespan = model.NewIntVar(0, H, 'makespan')
    for job in production.jobs:
        j, n = job.job_id, job.num_ops
        model.Add(makespan >= (trip_of[j, n][5] if instance.return_to_lu else end[j, n - 1]))
    model.Minimize(makespan)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = num_workers
    solver.parameters.random_seed = seed
    status = solver.Solve(model)
    name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise LogisticsCpSatError(f'CP-SAT returned {name}; no schedule', status=name)
    try:
        records = []
        for job in production.jobs:
            for op in job.operations:
                key = (job.job_id, op.op_id)
                machine = next(i for i, _ in op.machine_options if solver.Value(choice[key, i]))
                records.append(ScheduleRecord.placed(job.job_id, op.op_id, machine, solver.Value(start[key]),
                                                     production.get_processing_time(job.job_id, op.op_id, machine)))
        transports = []
        for t, (j, leg, needed, origin, destination, D, P, Q) in enumerate(trips, start=1):
            if not solver.Value(needed):
                continue
            vehicle = next(v for v in range(instance.num_vehicles) if solver.Value(assigned[t, v]))
            transports.append(TransportRecord(j, leg, vehicle, solver.Value(origin) if not isinstance(origin, int) else origin,
                                              solver.Value(destination) if not isinstance(destination, int) else destination,
                                              solver.Value(D), solver.Value(P), solver.Value(Q)))
        result = ScheduleResult.from_records(records, instance=production)
        total = logistics_makespan(result, transports, instance)
        if total > solver.ObjectiveValue() or (name == 'OPTIMAL' and total != solver.ObjectiveValue()):
            raise LogisticsCpSatError('Extracted makespan differs from the solver objective')
        schedule = LogisticsSchedule(result, tuple(transports), total, solver_status=name,
                                     solver_objective_bound=float(solver.BestObjectiveBound()),
                                     solver_wall_time=float(solver.WallTime()))
        return require_feasible(schedule, instance, source='CP-SAT')
    except LogisticsCpSatError:
        raise
    except Exception as exc:
        raise LogisticsCpSatError(f'Extraction/validation failed: {type(exc).__name__}: {exc}') from exc
