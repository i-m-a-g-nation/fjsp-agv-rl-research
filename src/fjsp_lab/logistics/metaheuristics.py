"""Genetic algorithm for the L1 logistics model (reference method for larger instances).

Chromosome:

* ``order``: job ids with repetition; the k-th occurrence of job j stands
  for its k-th operation (operation sequence);
* ``machines``: one eligible machine per operation (operations job by job);
* ``trips``: a permutation of trip slots ``(job, leg)`` - one slot per
  operation (the trip into it) plus, with return to L/U, one per job home;
* ``vehicles``: a vehicle per trip slot.

Decoding: the machine sequences follow ``order``, the needed trips (a slot
whose operation stays on the same machine needs none) are given to their
vehicles in ``trips`` order, and ``sequences.decode_sequences`` builds the
earliest schedule. With unlimited buffers this can express every
semi-active schedule (it reproduces CP-SAT optima exactly). Contradictory
sequences fall back to ``PriorityDecoder``: the event simulator with
lookahead deadlock avoidance, taking at each decision the operation that
comes first in ``order`` on its chosen machine. Every result passes the
checker.

Search: elitist GA (tournament selection, POX crossover on ``order``,
order crossover on ``trips``, uniform crossover on ``machines`` and
``vehicles``, swap / insertion / reassignment mutation) plus a
first-improvement local search on the best chromosome after every
generation, under a hard budget of decodings and a seed (reproducible).
The four avoided rule schedules seed the population and compete for the
best result, so the GA never returns anything worse than them.
"""

from __future__ import annotations

from dataclasses import dataclass
import random

from fjsp_lab.logistics.instance import LogisticsInstance
from fjsp_lab.logistics.rules import RULES, solve_rule
from fjsp_lab.logistics.schedule import LogisticsSchedule
from fjsp_lab.logistics.sequences import decode_sequences
from fjsp_lab.logistics.simulator import Candidate, LogisticsSimulator, SimulationDeadlock, avoid_deadlock, simulate


@dataclass(frozen=True)
class Chromosome:
    order: tuple[int, ...]                  # job ids; k-th occurrence = k-th operation of that job
    machines: tuple[int, ...]               # machine per operation, operations listed job by job
    trips: tuple[tuple[int, int], ...]      # permutation of the trip slots (job, leg)
    vehicles: tuple[int, ...]               # vehicle per trip slot, slots listed job by job


@dataclass(frozen=True)
class SearchOutcome:
    schedule: LogisticsSchedule
    chromosome: Chromosome
    evaluations: int
    fallback_decodings: int                 # sequences contradicted each other; priority decoder used
    infeasible_decodings: int               # even the fallback deadlocked
    trace: tuple[tuple[int, int], ...]      # (evaluations so far, best makespan) at each improvement


class Codec:
    """Encoding and decoding of chromosomes for one instance."""

    def __init__(self, instance: LogisticsInstance):
        self.instance = instance
        jobs = instance.production.jobs
        self.operations = [(job.job_id, op) for job in jobs for op in range(job.num_ops)]
        self.op_index = {key: i for i, key in enumerate(self.operations)}
        self.eligible = [[m for m, _ in jobs[j].operations[o].machine_options] for j, o in self.operations]
        self.slots = [(job.job_id, leg) for job in jobs
                      for leg in range(job.num_ops + int(instance.return_to_lu))]
        self.slot_index = {key: i for i, key in enumerate(self.slots)}

    def operation_order(self, chromosome: Chromosome) -> list[tuple[int, int]]:
        seen: dict[int, int] = {}
        ops = []
        for job in chromosome.order:
            op = seen.get(job, 0)
            seen[job] = op + 1
            ops.append((job, op))
        return ops

    def sequences(self, chromosome: Chromosome) -> tuple[list[list[tuple[int, int]]], list[list[tuple[int, int]]]]:
        """Machine sequences and vehicle sequences of a chromosome."""
        machine_of = {op: chromosome.machines[i] for op, i in self.op_index.items()}
        machines = [[] for _ in range(self.instance.num_machines)]
        for op in self.operation_order(chromosome):
            machines[machine_of[op]].append(op)
        vehicles = [[] for _ in range(self.instance.num_vehicles)]
        for job, leg in chromosome.trips:
            needed = leg == 0 or leg == self.instance.production.jobs[job].num_ops or \
                machine_of[job, leg] != machine_of[job, leg - 1]
            if needed:
                vehicles[chromosome.vehicles[self.slot_index[job, leg]]].append((job, leg))
        return machines, vehicles

    def decode(self, chromosome: Chromosome) -> tuple[LogisticsSchedule, bool]:
        """(checker-accepted schedule, whether the priority fallback was used); raises SimulationDeadlock.

        Contradictory sequences are first repaired by putting the trips in operation order
        (contradiction-free without blocking); only if that also fails is the priority decoder used.
        """
        for candidate in (chromosome, self.with_trips_in_operation_order(chromosome)):
            try:
                return decode_sequences(self.instance, *self.sequences(candidate)), False
            except ValueError:
                continue
        return self.decode_by_priority(chromosome), True

    def with_trips_in_operation_order(self, chromosome: Chromosome) -> Chromosome:
        trips = []
        for job, op in self.operation_order(chromosome):
            trips.append((job, op))                                    # the trip into the operation
            if op == self.instance.production.jobs[job].num_ops - 1 and self.instance.return_to_lu:
                trips.append((job, op + 1))                            # the trip home
        return Chromosome(chromosome.order, chromosome.machines, tuple(trips), chromosome.vehicles)

    def decode_by_priority(self, chromosome: Chromosome) -> LogisticsSchedule:
        rank = {op: i for i, op in enumerate(self.operation_order(chromosome))}
        machines, jobs = chromosome.machines, self.instance.production.jobs

        def policy(sim: LogisticsSimulator, options: list[Candidate]) -> Candidate:
            def key(c: Candidate) -> tuple:
                op = min(c.leg, jobs[c.job].num_ops - 1)
                preferred = c.leg >= jobs[c.job].num_ops or machines[self.op_index[c.job, op]] == c.machine
                return (rank[c.job, op], not preferred, c.finish, c.pickup, c.machine,
                        -1 if c.vehicle is None else c.vehicle)
            return min(options, key=key)

        return simulate(self.instance, avoid_deadlock(policy))

    def from_schedule(self, schedule: LogisticsSchedule) -> Chromosome:
        """Chromosome that decodes to a schedule at least as good (operations by start, trips by dispatch)."""
        records = sorted(schedule.production.records, key=lambda r: (r.start, r.job_id, r.op_id))
        machines = [0] * len(self.operations)
        for r in records:
            machines[self.op_index[r.job_id, r.op_id]] = r.machine_id
        trips = [(t.job_id, t.leg) for t in sorted(schedule.transports, key=lambda t: (t.dispatch, t.pickup, t.job_id))]
        trips += [slot for slot in self.slots if slot not in set(trips)]
        vehicles = [0] * len(self.slots)
        for t in schedule.transports:
            vehicles[self.slot_index[t.job_id, t.leg]] = t.vehicle
        return Chromosome(tuple(r.job_id for r in records), tuple(machines), tuple(trips), tuple(vehicles))

    def random(self, rng: random.Random) -> Chromosome:
        """Random chromosome whose trip order follows its operation order (no contradiction without blocking)."""
        order = [j for j, _ in self.operations]
        rng.shuffle(order)
        chromosome = Chromosome(tuple(order), tuple(rng.choice(options) for options in self.eligible), (),
                                tuple(rng.randrange(self.instance.num_vehicles) for _ in self.slots))
        return self.with_trips_in_operation_order(chromosome)


def _pox(a: tuple[int, ...], b: tuple[int, ...], rng: random.Random) -> tuple[int, ...]:
    """Precedence-preserving order crossover: jobs in a random subset keep a's positions, the rest follow b."""
    jobs = sorted(set(a))
    kept = set(rng.sample(jobs, max(1, len(jobs) // 2)))
    filler = iter(job for job in b if job not in kept)
    return tuple(job if job in kept else next(filler) for job in a)


def _order_crossover(a: tuple, b: tuple, rng: random.Random) -> tuple:
    """OX on permutations: keep a slice of a, fill the rest in b's order."""
    i, k = sorted(rng.sample(range(len(a) + 1), 2))
    kept = set(a[i:k])
    filler = [item for item in b if item not in kept]
    return tuple(filler[:i]) + a[i:k] + tuple(filler[i:])


def _mutate(chromosome: Chromosome, codec: Codec, rng: random.Random) -> Chromosome:
    order, machines = list(chromosome.order), list(chromosome.machines)
    trips, vehicles = list(chromosome.trips), list(chromosome.vehicles)
    move = rng.randrange(6)
    if move in (0, 1):                                       # swap / insert in the operation order
        i, k = rng.randrange(len(order)), rng.randrange(len(order))
        if move == 0:
            order[i], order[k] = order[k], order[i]
        else:
            order.insert(k, order.pop(i))
    elif move in (2, 3):                                     # swap / insert in the trip order
        i, k = rng.randrange(len(trips)), rng.randrange(len(trips))
        if move == 2:
            trips[i], trips[k] = trips[k], trips[i]
        else:
            trips.insert(k, trips.pop(i))
    elif move == 4:
        op = rng.randrange(len(machines))
        machines[op] = rng.choice(codec.eligible[op])
    else:
        vehicles[rng.randrange(len(vehicles))] = rng.randrange(codec.instance.num_vehicles)
    return Chromosome(tuple(order), tuple(machines), tuple(trips), tuple(vehicles))


def solve_ga(instance: LogisticsInstance, *, evaluations: int = 500, seed: int = 0, population: int = 20,
             crossover_rate: float = 0.8, mutation_rate: float = 0.3, elite: int = 2,
             local_search: int = 10) -> SearchOutcome:
    """Run the GA for exactly ``evaluations`` decodings (each rule schedule counts as one)."""
    if evaluations < 1 or population < 2 or not 0 <= elite < population:
        raise ValueError('Need evaluations >= 1, population >= 2 and 0 <= elite < population')
    rng = random.Random(seed)
    codec = Codec(instance)
    used = fallbacks = failed = 0
    trace: list[tuple[int, int]] = []
    best: tuple[int, Chromosome, LogisticsSchedule] | None = None

    def consider(schedule: LogisticsSchedule, chromosome: Chromosome) -> None:
        nonlocal best
        if best is None or schedule.makespan < best[0]:
            best = (schedule.makespan, chromosome, schedule)
            trace.append((used, schedule.makespan))

    def evaluate(chromosome: Chromosome) -> float:
        nonlocal used, fallbacks, failed
        used += 1
        try:
            schedule, fallback = codec.decode(chromosome)
        except SimulationDeadlock:
            failed += 1
            return float('inf')
        fallbacks += fallback
        consider(schedule, chromosome)
        return schedule.makespan

    starts = []
    for rule in RULES[:4]:                                   # EFT and the decoupled rules, all avoided
        if used >= evaluations:
            break
        used += 1
        try:
            schedule = solve_rule(instance, rule, avoid_deadlock=True)
        except SimulationDeadlock:
            failed += 1
            continue
        chromosome = codec.from_schedule(schedule)
        starts.append(chromosome)
        consider(schedule, chromosome)
    while len(starts) < population:
        starts.append(codec.random(rng))
    scored = []
    for chromosome in starts[:population]:
        if used >= evaluations:
            break
        scored.append((evaluate(chromosome), chromosome))

    def tournament() -> Chromosome:
        a, b = rng.sample(scored, 2)
        return a[1] if a[0] <= b[0] else b[1]

    while used < evaluations and len(scored) >= 2:
        scored.sort(key=lambda item: item[0])
        children = list(scored[:elite])
        while len(children) < population and used < evaluations:
            mother, father = tournament(), tournament()
            if rng.random() < crossover_rate:
                child = Chromosome(
                    _pox(mother.order, father.order, rng),
                    tuple(m if rng.random() < 0.5 else f for m, f in zip(mother.machines, father.machines)),
                    _order_crossover(mother.trips, father.trips, rng),
                    tuple(m if rng.random() < 0.5 else f for m, f in zip(mother.vehicles, father.vehicles)))
            else:
                child = mother
            if rng.random() < mutation_rate:
                child = _mutate(child, codec, rng)
            children.append((evaluate(child), child))
        scored = sorted(children, key=lambda item: item[0])
        value, current = scored[0]
        for _ in range(local_search):                       # first-improvement moves on the best
            if used >= evaluations or value == float('inf'):
                break
            neighbour = _mutate(current, codec, rng)
            candidate = evaluate(neighbour)
            if candidate < value:
                value, current = candidate, neighbour
                scored[0] = (value, current)
    if best is None:
        raise SimulationDeadlock('Every decoding deadlocked; no schedule')
    return SearchOutcome(best[2], best[1], used, fallbacks, failed, tuple(trace))


def solve_sa(instance: LogisticsInstance, *, evaluations: int = 500, seed: int = 0,
             start_temperature: float = 0.05, end_temperature: float = 0.002) -> SearchOutcome:
    """Simulated annealing from the best avoided rule schedule, same neighbourhood as the GA mutation.

    Temperatures are fractions of the start makespan; geometric cooling over the budget.
    """
    if evaluations < 1:
        raise ValueError('Need evaluations >= 1')
    rng = random.Random(seed)
    codec = Codec(instance)
    used = fallbacks = failed = 0
    trace: list[tuple[int, int]] = []
    best: tuple[int, Chromosome, LogisticsSchedule] | None = None
    for rule in RULES[:4]:
        if used >= evaluations:
            break
        used += 1
        try:
            schedule = solve_rule(instance, rule, avoid_deadlock=True)
        except SimulationDeadlock:
            failed += 1
            continue
        if best is None or schedule.makespan < best[0]:
            best = (schedule.makespan, codec.from_schedule(schedule), schedule)
            trace.append((used, schedule.makespan))
    if best is None:
        raise SimulationDeadlock('Every rule deadlocked; no start for annealing')
    value, current = best[0], best[1]
    hot, cold = start_temperature * value, end_temperature * value
    steps = max(1, evaluations - used)
    while used < evaluations:
        temperature = hot * (cold / hot) ** ((used - 4) / steps)
        neighbour = _mutate(current, codec, rng)
        used += 1
        try:
            schedule, fallback = codec.decode(neighbour)
        except SimulationDeadlock:
            failed += 1
            continue
        fallbacks += fallback
        delta = schedule.makespan - value
        if delta <= 0 or rng.random() < pow(2.718281828, -delta / temperature):
            value, current = schedule.makespan, neighbour
            if value < best[0]:
                best = (value, current, schedule)
                trace.append((used, value))
    return SearchOutcome(best[2], best[1], used, fallbacks, failed, tuple(trace))
