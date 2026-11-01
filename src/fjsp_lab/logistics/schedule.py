"""Logistics schedule: the unified production ScheduleResult plus AGV transport records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from fjsp_lab.fjsp.schedule import ScheduleResult


@dataclass(frozen=True)
class TransportRecord:
    job_id: int
    leg: int            # operation the job is carried to; number of operations = trip back to L/U
    vehicle: int
    origin: int         # location: machine id, or the L/U station (= number of machines)
    destination: int
    dispatch: int       # vehicle leaves its previous position empty; reserves a place at the destination
    pickup: int         # loaded trip starts; the job leaves the origin
    delivery: int       # job arrives at the destination


@dataclass(frozen=True)
class LogisticsSchedule:
    production: ScheduleResult
    transports: tuple[TransportRecord, ...] = ()
    makespan: int = 0
    solver_status: str | None = None
    solver_objective_bound: float | None = None
    solver_wall_time: float | None = None

    def __post_init__(self) -> None:
        if isinstance(self.transports, list):
            object.__setattr__(self, 'transports', tuple(self.transports))


def required_transports(machines: Sequence[int], lu: int, return_to_lu: bool) -> list[tuple[int, int, int]]:
    """(leg, origin, destination) of every trip a job needs, given the machine of each of its operations.

    Consecutive operations on the same machine need no trip (the job stays).
    """
    trips, previous = [], lu
    for op, machine in enumerate(machines):
        if machine != previous:
            trips.append((op, previous, machine))
        previous = machine
    if return_to_lu:
        trips.append((len(machines), previous, lu))
    return trips
