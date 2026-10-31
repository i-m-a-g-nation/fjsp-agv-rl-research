"""Freeze completed and in-process records at a rescheduling time."""

from __future__ import annotations

from dataclasses import replace

from fjsp_lab.fjsp.schedule import ScheduleRecord, ScheduleResult


def frozen_records_at_time(
    schedule: ScheduleResult,
    current_time: int,
    include_in_process: bool = True,
) -> list[ScheduleRecord]:
    """Return records that should be fixed at a rescheduling time.

    Completed operations always freeze. In-process operations also freeze by
    default because Phase 2A does not model interruption or preemption.
    """

    if current_time < 0:
        raise ValueError("current_time must be non-negative")

    frozen = []
    for record in schedule.records:
        is_completed = record.end <= current_time
        is_in_process = record.start < current_time < record.end
        if is_completed or (include_in_process and is_in_process):
            frozen.append(replace(record))
    return sorted(frozen, key=lambda r: (r.job_id, r.op_id))
