"""Feasibility checker of the L1 logistics model.

A schedule is accepted only if (docs/models/logistics_model_zh.md, section 4):

1. its production part passes the unchanged static FJSP checker;
2. every job has exactly the trips its machine sequence needs, with matching
   origin and destination, and no other trip;
3. each trip lasts travel + handling, picks the job up no earlier than the end
   of the operation before it and delivers it no later than the start of the
   operation after it;
4. each vehicle starts at L/U and serves its trips one after another, with
   enough empty travel time between them;
5. with blocking, a job occupies its machine from the first operation of a
   visit until it is picked up, and these occupations do not overlap on any
   machine (without blocking the static checker's no-overlap suffices);
6. a machine's station (machine + input buffer) never holds more jobs than
   its capacity, a place being held from the dispatch of the inbound trip
   until the job is picked up (blocking) or its visit's last operation ends;
7. the reported makespan equals an independent recomputation.

Nothing is repaired; invalid schedules yield violations. Intervals are half-open.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from fjsp_lab.fjsp.feasibility import check_feasibility
from fjsp_lab.fjsp.schedule import ScheduleResult
from fjsp_lab.logistics.instance import LogisticsInstance
from fjsp_lab.logistics.schedule import LogisticsSchedule, TransportRecord, required_transports

_TRANSPORT_FIELDS = ('job_id', 'leg', 'vehicle', 'origin', 'destination', 'dispatch', 'pickup', 'delivery')


@dataclass(frozen=True)
class LogisticsViolation:
    code: str
    message: str


class InfeasibleLogisticsError(RuntimeError):
    """An algorithm produced a logistics schedule that the checker rejected."""


def _max_overlap(intervals: list[tuple[int, int]]) -> int:
    """Largest number of half-open intervals covering one instant."""
    events = sorted([(start, 1) for start, end in intervals if end > start]
                    + [(end, -1) for start, end in intervals if end > start])   # ends sort before starts
    best = current = 0
    for _, step in events:
        current += step
        best = max(best, current)
    return best


def check_logistics_feasibility(schedule: LogisticsSchedule,
                                instance: LogisticsInstance) -> tuple[bool, list[LogisticsViolation]]:
    """Return (accepted, violations). A malformed instance raises ValueError."""
    if not isinstance(instance, LogisticsInstance):
        raise ValueError('Expected a LogisticsInstance')
    issues: list[LogisticsViolation] = []

    def reject(code: str, message: str) -> None:
        issues.append(LogisticsViolation(code, message))

    if not isinstance(schedule, LogisticsSchedule) or not isinstance(schedule.production, ScheduleResult):
        return False, [LogisticsViolation('INVALID_SCHEDULE', 'Expected a LogisticsSchedule with a ScheduleResult')]
    try:
        accepted, violations = check_feasibility(schedule.production, expected_instance=instance.production)
    except Exception as exc:  # malformed objects must be rejected, never accepted
        accepted, violations = False, [f'{type(exc).__name__}: {str(exc)[:200]}']
    if not accepted:
        codes = ', '.join(getattr(v, 'code', str(v)) for v in violations[:20])
        return False, [LogisticsViolation('PRODUCTION_INVALID', f'Static checker rejected production: {codes}')]

    transports = schedule.transports
    if not isinstance(transports, (tuple, list)) or any(
            not isinstance(t, TransportRecord) or any(type(getattr(t, name)) is not int for name in _TRANSPORT_FIELDS)
            for t in transports):
        return False, [LogisticsViolation('TRANSPORT_MALFORMED', 'Transports must be TransportRecords with integer fields')]

    # Machine, start and end of every operation (the static checker guarantees completeness).
    op = {(r.job_id, r.op_id): r for r in schedule.production.records}
    jobs = instance.production.jobs
    machines = {j.job_id: [op[j.job_id, o].machine_id for o in range(j.num_ops)] for j in jobs}

    # 2. Required trips.
    by_leg: dict[tuple[int, int], TransportRecord] = {}
    for t in transports:
        if (t.job_id, t.leg) in by_leg:
            reject('TRANSPORT_DUPLICATE', f'Job {t.job_id} leg {t.leg} is transported more than once')
        by_leg[t.job_id, t.leg] = t
    required = {}
    for job in jobs:
        for leg, origin, destination in required_transports(machines[job.job_id], instance.lu, instance.return_to_lu):
            required[job.job_id, leg] = (origin, destination)
    for key, (origin, destination) in required.items():
        t = by_leg.get(key)
        if t is None:
            reject('TRANSPORT_MISSING', f'Job {key[0]} needs a trip to leg {key[1]}')
        elif (t.origin, t.destination) != (origin, destination):
            reject('TRANSPORT_ROUTE', f'Job {key[0]} leg {key[1]} must go {origin} -> {destination}')
    for key in by_leg.keys() - required.keys():
        reject('TRANSPORT_UNEXPECTED', f'Job {key[0]} leg {key[1]} needs no trip')
    if issues:
        return False, issues

    # 3. Trip timing against the operations it connects.
    for (job, leg), t in by_leg.items():
        if t.delivery != t.pickup + instance.loaded_time(t.origin, t.destination):
            reject('TRANSPORT_DURATION', f'Job {job} leg {leg}: delivery must be pickup + travel + handling')
        if not 0 <= t.dispatch <= t.pickup:
            reject('DISPATCH_INVALID', f'Job {job} leg {leg}: need 0 <= dispatch <= pickup')
        if leg > 0 and t.pickup < op[job, leg - 1].end:
            reject('PICKUP_BEFORE_READY', f'Job {job} leg {leg}: picked up before operation {leg - 1} ends')
        if leg < jobs[job].num_ops and op[job, leg].start < t.delivery:
            reject('START_BEFORE_DELIVERY', f'Job {job} operation {leg} starts before the job arrives')

    # 4. Vehicles: one trip at a time, starting from L/U, with enough empty travel.
    per_vehicle = defaultdict(list)
    for t in transports:
        if not 0 <= t.vehicle < instance.num_vehicles:
            reject('VEHICLE_INVALID', f'Job {t.job_id} leg {t.leg} uses vehicle {t.vehicle}')
        else:
            per_vehicle[t.vehicle].append(t)
    for vehicle, trips in per_vehicle.items():
        position, free = instance.lu, 0
        for t in sorted(trips, key=lambda t: (t.dispatch, t.pickup)):
            if t.dispatch < free:
                reject('VEHICLE_OVERLAP', f'Vehicle {vehicle} is dispatched for job {t.job_id} before finishing a trip')
            if t.dispatch + instance.travel[position][t.origin] > t.pickup:
                reject('EMPTY_TRAVEL_SHORT', f'Vehicle {vehicle} cannot reach job {t.job_id} by its pickup')
            position, free = t.destination, t.delivery

    # 5 and 6. Visits: blocking on the machine and places at the station.
    occupation, places = defaultdict(list), defaultdict(list)
    for job in jobs:
        sequence = machines[job.job_id]
        first = 0
        for last in range(job.num_ops):
            if last + 1 < job.num_ops and sequence[last + 1] == sequence[first]:
                continue
            outbound = by_leg.get((job.job_id, last + 1))
            release = op[job.job_id, last].end
            machine = sequence[first]
            if instance.blocking:
                release = outbound.pickup if outbound is not None else release
                occupation[machine].append((op[job.job_id, first].start, release, job.job_id))
            places[machine].append((by_leg[job.job_id, first].dispatch, release))
            first = last + 1
    for machine, visits in occupation.items():
        visits.sort()
        for (start, release, job), (next_start, _, next_job) in zip(visits, visits[1:]):
            if next_start < release:
                reject('MACHINE_BLOCKED', f'Machine {machine}: job {next_job} starts while job {job} still occupies it')
    for machine in places:
        capacity = instance.station_capacity(machine)
        if capacity is not None and _max_overlap(places[machine]) > capacity:
            reject('BUFFER_OVERFLOW', f'Machine {machine} holds more than {capacity} jobs at once')

    # 7. Makespan.
    completion = [by_leg[job.job_id, job.num_ops].delivery if instance.return_to_lu
                  else op[job.job_id, job.num_ops - 1].end for job in jobs]
    if type(schedule.makespan) is not int or schedule.makespan != max(completion):
        reject('MAKESPAN_MISMATCH', f'Reported makespan {schedule.makespan!r} differs from {max(completion)}')
    return not issues, issues


def require_feasible(schedule: LogisticsSchedule, instance: LogisticsInstance, *, source: str) -> LogisticsSchedule:
    """Return ``schedule`` if the checker accepts it, otherwise raise InfeasibleLogisticsError."""
    accepted, issues = check_logistics_feasibility(schedule, instance)
    if not accepted:
        raise InfeasibleLogisticsError(f'{source} produced a schedule the checker rejected: {issues}')
    return schedule


def logistics_makespan(production: ScheduleResult, transports: list[TransportRecord],
                       instance: LogisticsInstance) -> int:
    """Makespan of a schedule under the instance's completion definition (no checking)."""
    if instance.return_to_lu:
        return max(t.delivery for t in transports if t.destination == instance.lu)
    return production.makespan
