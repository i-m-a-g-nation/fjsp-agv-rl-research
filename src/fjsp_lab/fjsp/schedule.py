"""Unified schedule record/result shared by every FJSP and maintenance algorithm.

Both types are immutable. A solver collects its records, builds the result
once with ``ScheduleResult.from_records`` and attaches solver metadata with
``dataclasses.replace``; nothing can change a result after the checker has
accepted it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, TypeVar

from fjsp_lab.fjsp.instance import FJSPInstance

ResultT = TypeVar("ResultT", bound="ScheduleResult")


@dataclass(frozen=True)
class ScheduleRecord:
    """One scheduled operation record."""

    job_id: int
    op_id: int
    machine_id: int
    start: int
    end: int
    processing_time: int

    @classmethod
    def placed(cls, job_id: int, op_id: int, machine_id: int, start: int, processing_time: int) -> ScheduleRecord:
        """Record of an operation started at ``start``; end is stored explicitly as start + processing_time."""

        return cls(job_id, op_id, machine_id, start, start + processing_time, processing_time)


@dataclass(frozen=True)
class ScheduleResult:
    """Immutable schedule built by decoders or solvers."""

    # records preserve the order in which the decoder or solver produced them.
    # Use sorted_records() when job-route order is needed for display or checks.
    # A list passed in is copied into a tuple; other types are kept as given so
    # the feasibility checker can still reject malformed results.
    records: tuple[ScheduleRecord, ...] = ()
    makespan: int = 0
    instance: FJSPInstance | None = None
    solver_status: str | None = None
    solver_objective_bound: float | None = None
    solver_gap: float | None = None
    solver_wall_time: float | None = None
    solver_config: dict | None = None

    def __post_init__(self) -> None:
        if isinstance(self.records, list):
            object.__setattr__(self, "records", tuple(self.records))

    @classmethod
    def from_records(cls: type[ResultT], records: Iterable[ScheduleRecord], **fields: object) -> ResultT:
        """Build a result whose makespan is the maximum record end (0 without records).

        An empty result is not a feasible schedule; feasibility.py rejects it.
        """

        records = tuple(records)
        makespan = max((r.end for r in records), default=0)
        return cls(records=records, makespan=makespan, **fields)

    def sorted_records(self) -> List[ScheduleRecord]:
        """Return records sorted by job route order."""

        return sorted(self.records, key=lambda r: (r.job_id, r.op_id))
