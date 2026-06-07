from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.dynamic.state import DynamicFJSPState
from src.scheduling.encoding import ScheduleRecord


@dataclass(frozen=True)
class RemainingOperation:
    """One operation that still needs scheduling after a dynamic snapshot."""

    job_id: int
    op_id: int
    release_time: int
    machine_options: tuple[tuple[int, int], ...]


def remaining_operations_from_frozen(
    state: DynamicFJSPState,
    frozen_records: Iterable[ScheduleRecord] = (),
) -> list[RemainingOperation]:
    """Return remaining operations implied by frozen route prefixes."""

    frozen_by_job: dict[int, set[int]] = {job.job_id: set() for job in state.instance.jobs}
    for record in frozen_records:
        if record.job_id < 0 or record.job_id >= state.instance.num_jobs:
            raise ValueError("frozen record job_id is out of range")
        if record.op_id < 0 or record.op_id >= state.instance.jobs[record.job_id].num_ops:
            raise ValueError("frozen record op_id is out of range")
        frozen_by_job[record.job_id].add(record.op_id)

    remaining: list[RemainingOperation] = []
    for job_id in sorted(state.released_job_ids or frozenset()):
        scheduled_ops = frozen_by_job[job_id]
        if scheduled_ops:
            expected_prefix = set(range(max(scheduled_ops) + 1))
            if scheduled_ops != expected_prefix:
                raise ValueError(
                    f"frozen records for job {job_id} must form a route prefix"
                )
            next_op_id = max(scheduled_ops) + 1
        else:
            next_op_id = 0

        release_time = (state.job_release_times or ())[job_id]
        for operation in state.instance.jobs[job_id].operations[next_op_id:]:
            remaining.append(
                RemainingOperation(
                    job_id=job_id,
                    op_id=operation.op_id,
                    release_time=release_time,
                    machine_options=operation.machine_options,
                )
            )
    return remaining
