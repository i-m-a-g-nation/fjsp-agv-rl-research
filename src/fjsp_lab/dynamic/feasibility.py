"""Dynamic checks on top of the static checker: frozen records, releases, downtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from fjsp_lab.dynamic.state import DynamicFJSPState
from fjsp_lab.fjsp.schedule import ScheduleRecord, ScheduleResult


@dataclass(frozen=True)
class DynamicViolation:
    """One dynamic-layer feasibility violation."""

    code: str
    message: str


def check_dynamic_feasibility(
    result: ScheduleResult,
    state: DynamicFJSPState,
    frozen_records: Iterable[ScheduleRecord] = (),
) -> tuple[bool, list[DynamicViolation]]:
    """Check Phase 2A constraints not covered by the static checker."""

    violations: list[DynamicViolation] = []
    frozen_by_key = {
        (record.job_id, record.op_id): record
        for record in frozen_records
    }

    _check_frozen_records(result, frozen_by_key, violations)
    _check_job_release_times(result, state, violations)
    _check_machine_unavailability(result, state, frozen_by_key, violations)
    return not violations, violations


def _check_frozen_records(
    result: ScheduleResult,
    frozen_by_key: dict[tuple[int, int], ScheduleRecord],
    violations: list[DynamicViolation],
) -> None:
    records_by_key = {
        (record.job_id, record.op_id): record
        for record in result.records
    }
    for key, frozen in frozen_by_key.items():
        record = records_by_key.get(key)
        if record is None:
            violations.append(DynamicViolation(
                code="FROZEN_RECORD_MISSING",
                message=f"Frozen operation {key} is missing from the result",
            ))
            continue
        if (
            record.machine_id != frozen.machine_id
            or record.start != frozen.start
            or record.end != frozen.end
            or record.processing_time != frozen.processing_time
        ):
            violations.append(DynamicViolation(
                code="FROZEN_RECORD_CHANGED",
                message=f"Frozen operation {key} was changed by rescheduling",
            ))


def _check_job_release_times(
    result: ScheduleResult,
    state: DynamicFJSPState,
    violations: list[DynamicViolation],
) -> None:
    release_times = state.job_release_times or ()
    for record in result.records:
        release_time = release_times[record.job_id]
        if record.start < release_time:
            violations.append(DynamicViolation(
                code="JOB_BEFORE_RELEASE",
                message=(
                    f"Job {record.job_id} operation {record.op_id} starts at "
                    f"{record.start}, before release time {release_time}"
                ),
            ))


def _check_machine_unavailability(
    result: ScheduleResult,
    state: DynamicFJSPState,
    frozen_by_key: dict[tuple[int, int], ScheduleRecord],
    violations: list[DynamicViolation],
) -> None:
    unavailable_until = state.machine_unavailable_until or ()
    for record in result.records:
        if (record.job_id, record.op_id) in frozen_by_key:
            continue
        blocked_until = unavailable_until[record.machine_id]
        if state.current_time <= record.start < blocked_until:
            violations.append(DynamicViolation(
                code="MACHINE_UNAVAILABLE",
                message=(
                    f"Machine {record.machine_id} starts job {record.job_id} "
                    f"operation {record.op_id} at {record.start}, before "
                    f"available time {blocked_until}"
                ),
            ))
