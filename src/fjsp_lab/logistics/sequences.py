"""Decode machine and vehicle sequences into the earliest logistics schedule.

Given the operations each machine processes (in order) and the trips each
vehicle drives (in order), every time is set as early as the precedences
allow: operation after its inbound trip and the job's previous operation,
after the machine's previous occupant has left (picked up, with blocking);
trip after the operation it leaves and after the vehicle's previous trip plus
the empty run. Buffer capacity is not a precedence and is left to the
checker. Contradictory sequences form a cycle and raise ValueError.

Also reads the FJSPT reference-solution files of Berterottière et al.:
``Mk  ops`` (machine k, global 1-based operation ids numbered job by job) and
``Vk  Tx ..`` (vehicle k; ``Tx`` = trip that brings operation x to its machine).
"""

from __future__ import annotations

from typing import Sequence

from fjsp_lab.fjsp.schedule import ScheduleRecord, ScheduleResult
from fjsp_lab.logistics.feasibility import logistics_makespan, require_feasible
from fjsp_lab.logistics.instance import LogisticsInstance
from fjsp_lab.logistics.schedule import LogisticsSchedule, TransportRecord, required_transports

Operation = tuple[int, int]          # (job, op)
Trip = tuple[int, int]               # (job, leg)


def decode_sequences(instance: LogisticsInstance, machine_sequences: Sequence[Sequence[Operation]],
                     vehicle_sequences: Sequence[Sequence[Trip]]) -> LogisticsSchedule:
    """Earliest schedule for the given sequences; returns it only if the checker accepts it."""
    production, lu = instance.production, instance.lu
    machine_of = {}
    for machine, sequence in enumerate(machine_sequences):
        for job, op in sequence:
            if (job, op) in machine_of or not production.is_machine_eligible(job, op, machine):
                raise ValueError(f'Operation {(job, op)} is repeated or on an ineligible machine')
            machine_of[job, op] = machine
    if len(machine_of) != production.total_ops:
        raise ValueError('Every operation must appear in exactly one machine sequence')
    route = {}
    for job in production.jobs:
        machines = [machine_of[job.job_id, o] for o in range(job.num_ops)]
        for leg, origin, destination in required_transports(machines, lu, instance.return_to_lu):
            route[job.job_id, leg] = (origin, destination)
    vehicle_of = {trip: v for v, trips in enumerate(vehicle_sequences) for trip in trips}
    if sorted(vehicle_of) != sorted(route) or sum(map(len, vehicle_sequences)) != len(route):
        raise ValueError('Vehicle sequences must cover every required trip exactly once')

    def p(job: int, op: int) -> int:
        return production.get_processing_time(job, op, machine_of[job, op])

    S = {key: 0 for key in machine_of}
    D = {key: 0 for key in route}
    P = dict(D)

    def end(job: int, op: int) -> int:
        return S[job, op] + p(job, op)

    def delivery(trip: Trip) -> int:
        return P[trip] + instance.loaded_time(*route[trip])

    def release(job: int, op: int) -> int:
        """When the machine is free again after operation (job, op)."""
        last = op == production.jobs[job].num_ops - 1
        if not instance.blocking or (last and not instance.return_to_lu):
            return end(job, op)
        if not last and machine_of[job, op + 1] == machine_of[job, op]:
            return S[job, op + 1]
        return P[job, op + 1]

    limit = 2 * (len(S) + len(D)) + 10
    for _ in range(limit):
        changed = False

        def raise_to(times: dict, key: tuple, value: int) -> None:
            nonlocal changed
            if value > times[key]:
                times[key], changed = value, True

        for (job, op) in S:
            if op > 0:
                raise_to(S, (job, op), end(job, op - 1))
            if (job, op) in route:
                raise_to(S, (job, op), delivery((job, op)))
        for (job, leg) in route:
            if leg > 0:
                raise_to(P, (job, leg), end(job, leg - 1))
            raise_to(P, (job, leg), D[job, leg])
        for sequence in machine_sequences:
            for a, b in zip(sequence, sequence[1:]):
                raise_to(S, b, release(*a))
        for trips in vehicle_sequences:
            position, free = lu, 0
            for trip in trips:
                raise_to(D, trip, free)
                raise_to(P, trip, D[trip] + instance.travel[position][route[trip][0]])
                position, free = route[trip][1], delivery(trip)
        if not changed:
            break
    else:
        raise ValueError('Machine and vehicle sequences contradict each other (cyclic precedences)')

    records = [ScheduleRecord.placed(job, op, machine_of[job, op], S[job, op], p(job, op)) for job, op in sorted(S)]
    transports = [TransportRecord(job, leg, vehicle_of[job, leg], *route[job, leg], D[job, leg], P[job, leg],
                                  delivery((job, leg))) for job, leg in sorted(route)]
    result = ScheduleResult.from_records(records, instance=production)
    schedule = LogisticsSchedule(result, tuple(transports), logistics_makespan(result, transports, instance))
    return require_feasible(schedule, instance, source='Sequence decoder')


def parse_reference_solution(text: str, instance: LogisticsInstance) -> tuple[list, list, float]:
    """Machine sequences, vehicle sequences and reported Cmax of a reference-solution file."""
    production = instance.production
    operations = [(job.job_id, op) for job in production.jobs for op in range(job.num_ops)]
    lines = [line.split() for line in text.splitlines() if line.strip()]
    reported = float(lines[0][lines[0].index('Cmax:') + 1])
    machines = [[] for _ in range(production.num_machines)]
    vehicles = [[] for _ in range(instance.num_vehicles)]
    for parts in lines:
        if parts[0][0] == 'M' and parts[0][1:].isdigit():
            machines[int(parts[0][1:]) - 1] = [operations[int(x) - 1] for x in parts[1:]]
        elif parts[0][0] == 'V' and parts[0][1:].isdigit():
            vehicles[int(parts[0][1:]) - 1] = [operations[int(x[1:]) - 1] for x in parts[1:]]
    return machines, vehicles, reported
