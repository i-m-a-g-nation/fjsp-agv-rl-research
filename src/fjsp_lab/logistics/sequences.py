"""Decode machine and vehicle sequences into the earliest logistics schedule.

Given the operations each machine processes (in order) and the trips each
vehicle drives (in order), every time is set as early as the precedences
allow: operation after its inbound trip and the job's previous operation,
after the machine's previous occupant has left (picked up, with blocking);
trip after the operation it leaves and after the vehicle's previous trip plus
the empty run. A finite station capacity c is enforced as a precedence too:
the visits of a machine are served in its sequence order, and the inbound
trip of the k-th visit is dispatched only after the (k - c)-th visit has
left. This is sufficient for the capacity (and exact when places are
reserved in processing order), so with finite buffers some schedules cannot
be expressed; with unlimited buffers every semi-active schedule can.
Contradictory sequences form a cycle and raise ValueError.

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

    # Precedence graph: an edge (a, b, w) means time[b] >= time[a] + w. Nodes are ('S', op) operation
    # starts, ('D', trip) dispatches and ('P', trip) pickups; every time is also >= 0.
    edges: list[tuple[tuple, tuple, int]] = []
    for (job, op) in machine_of:
        if op > 0:
            edges.append((('S', (job, op - 1)), ('S', (job, op)), p(job, op - 1)))
        if (job, op) in route:
            edges.append((('P', (job, op)), ('S', (job, op)), instance.loaded_time(*route[job, op])))
    for (job, leg) in route:
        if leg > 0:
            edges.append((('S', (job, leg - 1)), ('P', (job, leg)), p(job, leg - 1)))
        edges.append((('D', (job, leg)), ('P', (job, leg)), 0))

    def release(job: int, op: int) -> tuple[tuple, int]:
        """(node, offset) of the moment the machine is free again after operation (job, op)."""
        last = op == production.jobs[job].num_ops - 1
        if not instance.blocking or (last and not instance.return_to_lu):
            return ('S', (job, op)), p(job, op)
        if not last and machine_of[job, op + 1] == machine_of[job, op]:
            return ('S', (job, op + 1)), 0
        return ('P', (job, op + 1)), 0

    for sequence in machine_sequences:
        for a, b in zip(sequence, sequence[1:]):
            node, offset = release(*a)
            edges.append((node, ('S', b), offset))

    # Visits (maximal runs of a job on one machine) in each machine's order, for the capacity precedence.
    position = {op: i for sequence in machine_sequences for i, op in enumerate(sequence)}
    visits = [[] for _ in machine_sequences]
    for job in production.jobs:
        first = 0
        for last in range(job.num_ops):
            if last + 1 < job.num_ops and machine_of[job.job_id, last + 1] == machine_of[job.job_id, first]:
                continue
            visits[machine_of[job.job_id, first]].append((position[job.job_id, first], job.job_id, first, last))
            first = last + 1
    for machine, machine_visits in enumerate(visits):
        machine_visits.sort()
        capacity = instance.station_capacity(machine)
        if capacity is None:
            continue
        for k in range(capacity, len(machine_visits)):
            _, job, first, _ = machine_visits[k]
            _, earlier, _, earlier_last = machine_visits[k - capacity]
            if instance.blocking and (earlier, earlier_last + 1) in route:      # place freed at pickup
                edges.append((('P', (earlier, earlier_last + 1)), ('D', (job, first)), 0))
            else:                                                                  # or at the end of the visit
                edges.append((('S', (earlier, earlier_last)), ('D', (job, first)), p(earlier, earlier_last)))
    for trips in vehicle_sequences:
        here, previous = lu, None
        for trip in trips:
            if previous is not None:
                edges.append((('P', previous), ('D', trip), instance.loaded_time(*route[previous])))
            edges.append((('D', trip), ('P', trip), instance.travel[here][route[trip][0]]))
            here, previous = route[trip][1], trip

    # Longest paths by topological order (Kahn); a cycle means contradictory sequences.
    nodes = [('S', key) for key in machine_of] + [(kind, trip) for trip in route for kind in 'DP']
    successors: dict[tuple, list[tuple[tuple, int]]] = {node: [] for node in nodes}
    indegree = dict.fromkeys(nodes, 0)
    for a, b, w in edges:
        if a == b:
            if w > 0:
                raise ValueError('Machine and vehicle sequences contradict each other (cyclic precedences)')
            continue
        successors[a].append((b, w))
        indegree[b] += 1
    time = dict.fromkeys(nodes, 0)
    ready = [node for node in nodes if indegree[node] == 0]
    done = 0
    while ready:
        node = ready.pop()
        done += 1
        for nxt, w in successors[node]:
            time[nxt] = max(time[nxt], time[node] + w)
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
    if done != len(nodes):
        raise ValueError('Machine and vehicle sequences contradict each other (cyclic precedences)')
    S = {key: time['S', key] for key in machine_of}
    D = {trip: time['D', trip] for trip in route}
    P = {trip: time['P', trip] for trip in route}

    def delivery(trip: Trip) -> int:
        return P[trip] + instance.loaded_time(*route[trip])

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
