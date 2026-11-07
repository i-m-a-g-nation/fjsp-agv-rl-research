"""Event-driven simulator of the L1 logistics model.

Decisions are taken whenever something can be done now (non-delay). A
decision is a ``Candidate``: carry job j to the machine of its next operation
(or back to L/U) with an idle vehicle, or let it stay on its current machine
when that machine can also process the next operation. The machine is fixed
when the vehicle is dispatched, and the dispatch reserves a place at the
destination station. A delivered job waits in the input buffer; a machine
starts the waiting jobs in arrival order as soon as no job occupies it. With
blocking, a finished job stays on its machine until it is picked up; without
blocking it moves at once to an unlimited output buffer and leaves the
station, except that a job that may stay for its next operation keeps its
place until it is decided. Usually that is the same instant (a stay needs no
vehicle, so it remains a candidate until the job is decided), but a policy
or the deadlock guard may wait. The place is still held then, because a
later stay continues the same visit and the model counts the place over the
whole visit; if the job leaves instead, the simulator has held the place
longer than the model requires (conservative, never infeasible).

Same-time events are handled in a fixed order: operation ends, pickups,
deliveries; then idle machines start waiting jobs; then decisions are taken.
A policy may also return ``None`` to wait for the next event. If nothing is
pending and no decision is taken before every job is done, the system is
deadlocked and ``SimulationDeadlock`` is raised.

``avoid_deadlock(policy)`` wraps a policy with a one-step lookahead: a
decision is taken only if, after it, a conservative rollout finishes every
job on a copy of the simulator. The rollout moves the jobs already released
into the shop first (joint EFT among them) and releases a new job from L/U
only when the shop is empty. A successful rollout proves that the state is
not doomed; a failed one does not prove the opposite, so the guard is
conservative. Unsafe decisions are skipped in the policy's order of
preference; if none is safe the simulator waits.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import heapq
from typing import Callable

from fjsp_lab.fjsp.schedule import ScheduleRecord, ScheduleResult
from fjsp_lab.logistics.feasibility import logistics_makespan, require_feasible
from fjsp_lab.logistics.instance import LogisticsInstance
from fjsp_lab.logistics.schedule import LogisticsSchedule, TransportRecord

_OP_END, _PICKUP, _DELIVERY = 0, 1, 2          # same-time processing order


class SimulationDeadlock(RuntimeError):
    """No event is pending and no decision is possible, but jobs remain unfinished."""


@dataclass(frozen=True)
class Candidate:
    job: int
    leg: int                # next operation of the job; number of operations = trip back to L/U
    machine: int            # destination: machine id, or the L/U station
    vehicle: int | None     # None: the job stays on its machine for the next operation
    pickup: int             # earliest pickup (now for a stay)
    delivery: int           # arrival at the destination (now for a stay)
    processing_time: int    # of operation ``leg`` on ``machine`` (0 for L/U)
    machine_ready: int      # estimated time the destination could start it (queue estimate)

    @property
    def finish(self) -> int:
        """Estimated completion of the next operation (arrival at L/U for the final trip)."""
        return max(self.delivery, self.machine_ready) + self.processing_time


Policy = Callable[['LogisticsSimulator', list[Candidate]], 'Candidate | None']


class LogisticsSimulator:
    def __init__(self, instance: LogisticsInstance):
        self.instance = instance
        production = instance.production
        n, m = production.num_jobs, production.num_machines
        self.now = 0
        self.next_op = [0] * n                    # next operation to decide (num_ops: trip home)
        self.location = [instance.lu] * n         # where the job is; None while in transit
        self.ready = [0] * n                      # time the job became available for a decision
        self.awaiting = set(range(n))             # jobs waiting for a decision
        self.done = [False] * n
        self.holder: list[int | None] = [None] * m          # job occupying each machine
        self.busy_until = [0] * m                            # end of the operation in progress
        self.queue: list[deque] = [deque() for _ in range(m)]
        self.places = [0] * m                                # reserved or present jobs per station
        self.incoming_work = [0] * m                         # processing time reserved, queued or in transit
        self.keeps_place: list[int | None] = [None] * n      # non-blocking: station whose place a job still holds
        self.vehicle_position = [instance.lu] * instance.num_vehicles
        self.vehicle_free = [0] * instance.num_vehicles
        self.records: list[ScheduleRecord] = []
        self.transports: list[TransportRecord] = []
        self._events: list[tuple[int, int, int, tuple]] = []
        self._counter = 0

    def clone(self) -> LogisticsSimulator:
        """Independent copy of the current state (for lookahead rollouts)."""
        twin = object.__new__(LogisticsSimulator)
        for name, value in self.__dict__.items():
            if isinstance(value, list):
                value = [deque(item) if isinstance(item, deque) else item for item in value]
            elif isinstance(value, set):
                value = set(value)
            twin.__dict__[name] = value
        return twin

    # --- events -----------------------------------------------------------------
    def _push(self, time: int, kind: int, payload: tuple) -> None:
        heapq.heappush(self._events, (time, kind, self._counter, payload))
        self._counter += 1

    def _start(self, job: int, machine: int) -> None:
        op = self.next_op[job]
        p = self.instance.production.get_processing_time(job, op, machine)
        self.records.append(ScheduleRecord.placed(job, op, machine, self.now, p))
        self.holder[machine] = job
        self.busy_until[machine] = self.now + p
        self._push(self.now + p, _OP_END, (job, machine))

    def _start_waiting_jobs(self) -> None:
        for machine, waiting in enumerate(self.queue):
            if self.holder[machine] is None and waiting:
                job = waiting.popleft()
                self.incoming_work[machine] -= self.instance.production.get_processing_time(
                    job, self.next_op[job], machine)
                self._start(job, machine)

    def _leave(self, machine: int) -> None:
        self.holder[machine] = None
        self.places[machine] -= 1

    def _handle(self, kind: int, payload: tuple) -> None:
        if kind == _OP_END:
            job, machine = payload
            self.next_op[job] += 1
            self.ready[job] = self.now
            finished = self.next_op[job] == self.instance.production.jobs[job].num_ops
            if not self.instance.blocking:
                self.holder[machine] = None
                if not finished and self.instance.production.is_machine_eligible(job, self.next_op[job], machine):
                    self.keeps_place[job] = machine
                else:
                    self.places[machine] -= 1
            if finished and not self.instance.return_to_lu:
                self.done[job] = True
                if self.instance.blocking:
                    self._leave(machine)
            else:
                self.awaiting.add(job)
        elif kind == _PICKUP:
            job, origin = payload
            self.location[job] = None
            if origin != self.instance.lu and self.instance.blocking:
                self._leave(origin)
        else:
            job, destination = payload
            self.location[job] = destination
            if destination == self.instance.lu:
                self.done[job] = True
            else:
                self.queue[destination].append(job)

    # --- decisions --------------------------------------------------------------
    def candidates(self) -> list[Candidate]:
        """Every decision possible now, in a fixed order (job, leg, machine, vehicle)."""
        instance, production = self.instance, self.instance.production
        idle = [v for v in range(instance.num_vehicles) if self.vehicle_free[v] <= self.now]
        found = []
        for job in sorted(self.awaiting):
            leg, origin = self.next_op[job], self.location[job]
            if leg == production.jobs[job].num_ops:
                options = [(instance.lu, 0)]
            else:
                options = sorted(production.get_op_options(job, leg))
            for machine, p in options:
                if machine == instance.lu:
                    ready = self.now
                else:
                    ready = max(self.now, self.busy_until[machine]) + self.incoming_work[machine]
                if machine == origin:
                    found.append(Candidate(job, leg, machine, None, self.now, self.now, p, self.now))
                    continue
                capacity = None if machine == instance.lu else instance.station_capacity(machine)
                if capacity is not None and self.places[machine] >= capacity:
                    continue
                for v in idle:
                    pickup = self.now + instance.travel[self.vehicle_position[v]][origin]
                    found.append(Candidate(job, leg, machine, v, pickup,
                                           pickup + instance.loaded_time(origin, machine), p, ready))
        return found

    def apply(self, choice: Candidate) -> None:
        """Carry out one decision returned by ``candidates()`` at the current time."""
        instance = self.instance
        job = choice.job
        if job not in self.awaiting or self.next_op[job] != choice.leg:
            raise ValueError('Decision does not match a waiting job')
        self.awaiting.discard(job)
        kept, self.keeps_place[job] = self.keeps_place[job], None
        if choice.vehicle is None:
            if instance.blocking:
                self._start(job, choice.machine)
            else:                                   # back into the input buffer, keeping its place
                self.queue[choice.machine].append(job)
                self.incoming_work[choice.machine] += choice.processing_time
            return
        if kept is not None:
            self.places[kept] -= 1
        origin, v = self.location[job], choice.vehicle
        self.transports.append(TransportRecord(job, choice.leg, v, origin, choice.machine,
                                               self.now, choice.pickup, choice.delivery))
        if choice.machine != instance.lu:
            self.places[choice.machine] += 1
            self.incoming_work[choice.machine] += choice.processing_time
        self.vehicle_position[v] = choice.machine
        self.vehicle_free[v] = choice.delivery
        self._push(choice.pickup, _PICKUP, (job, origin))
        self._push(choice.delivery, _DELIVERY, (job, choice.machine))

    # --- main loop --------------------------------------------------------------
    def advance(self, policy: Policy) -> None:
        """Simulate to the end with ``policy`` (raises SimulationDeadlock); builds no schedule."""
        while True:
            while self._events and self._events[0][0] == self.now:
                _, kind, _, payload = heapq.heappop(self._events)
                self._handle(kind, payload)
            self._start_waiting_jobs()
            options = self.candidates()
            while options:
                choice = policy(self, options)
                if choice is None:
                    break
                if choice not in options:
                    raise ValueError('Policy returned a decision that is not a current candidate')
                self.apply(choice)
                self._start_waiting_jobs()
                options = self.candidates()
            if all(self.done):
                return
            if not self._events:
                raise SimulationDeadlock(f'Deadlock at time {self.now}: jobs {sorted(self.awaiting)} cannot move')
            self.now = self._events[0][0]

    def run(self, policy: Policy) -> LogisticsSchedule:
        """Simulate to the end with ``policy``; return the checker-accepted schedule."""
        self.advance(policy)
        production = ScheduleResult.from_records(self.records, instance=self.instance.production)
        schedule = LogisticsSchedule(production, tuple(self.transports),
                                     logistics_makespan(production, self.transports, self.instance))
        return require_feasible(schedule, self.instance, source='Simulator')


def simulate(instance: LogisticsInstance, policy: Policy) -> LogisticsSchedule:
    """Run one simulation of ``instance`` under ``policy``."""
    return LogisticsSimulator(instance).run(policy)


def _eft_key(c: Candidate) -> tuple:
    return (c.finish, c.pickup, c.job, c.machine, -1 if c.vehicle is None else c.vehicle)


def _unreleased(sim: LogisticsSimulator, job: int) -> bool:
    """Still waiting at L/U for its first trip (no decision taken yet)."""
    return sim.next_op[job] == 0 and job in sim.awaiting


def _rollout_flush(sim: LogisticsSimulator, options: list[Candidate]) -> Candidate | None:
    """Finish the jobs in the shop before releasing another one (a completion certificate, not a good schedule)."""
    released = [c for c in options if not _unreleased(sim, c.job)]
    if released:
        return min(released, key=_eft_key)
    in_shop = any(not sim.done[j] and not _unreleased(sim, j) for j in range(len(sim.done)))
    return None if in_shop else min(options, key=_eft_key)


def is_safe(sim: LogisticsSimulator, choice: Candidate) -> bool:
    """True if the conservative rollout finishes every job after ``choice`` (proof that it is not doomed)."""
    twin = sim.clone()
    twin.apply(choice)
    try:
        twin.advance(_rollout_flush)
    except SimulationDeadlock:
        return False
    return True


def avoid_deadlock(policy: Policy) -> Policy:
    """Wrap ``policy``: skip decisions after which the rollout deadlocks; wait if none is safe.

    With unlimited station capacity nothing can deadlock (a waiting job can
    always be carried away once a vehicle is free), so no check is made.
    """
    def guarded(sim: LogisticsSimulator, options: list[Candidate]) -> Candidate | None:
        if all(capacity is None for capacity in sim.instance.buffer_capacity):
            return policy(sim, options)
        remaining = list(options)
        while remaining:
            choice = policy(sim, remaining)
            if choice is None:
                return None
            if is_safe(sim, choice):
                return choice
            remaining.remove(choice)
        return None
    return guarded
