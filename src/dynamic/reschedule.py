from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Literal

from src.scheduling.encoding import ScheduleRecord, ScheduleResult
from src.scheduling.feasibility import check_feasibility
from src.dynamic.state import DynamicFJSPState

RescheduleRule = Literal["fifo", "spt", "eft"]
_Candidate = tuple[int, int, int, int, int, int, int]


def reschedule_from_state(
    state: DynamicFJSPState,
    frozen_records: Iterable[ScheduleRecord] = (),
    rule: RescheduleRule = "eft",
) -> ScheduleResult:
    """Freeze known records and dispatch all remaining operations.

    The returned schedule is a full `ScheduleResult` over the state's current
    instance, so the Phase 1 feasibility checker remains the final legality
    gate. Phase 2A treats frozen records as immutable facts and only delays
    future starts after dynamic machine unavailability.
    """

    frozen = [replace(record) for record in frozen_records]
    _validate_released_jobs(state)
    _validate_frozen_records(state, frozen)

    instance = state.instance
    result = ScheduleResult(instance=instance)
    result.records.extend(sorted(frozen, key=lambda r: (r.start, r.machine_id, r.job_id, r.op_id)))

    job_next_op = {job.job_id: 0 for job in instance.jobs}
    job_ready_time = {job.job_id: state.current_time for job in instance.jobs}
    machine_ready_time = {
        machine_id: max(state.current_time, unavailable_until)
        for machine_id, unavailable_until in enumerate(state.machine_unavailable_until or ())
    }

    for record in sorted(frozen, key=lambda r: (r.job_id, r.op_id)):
        job_next_op[record.job_id] = max(job_next_op[record.job_id], record.op_id + 1)
        job_ready_time[record.job_id] = max(job_ready_time[record.job_id], record.end)
        machine_ready_time[record.machine_id] = max(
            machine_ready_time[record.machine_id],
            record.end,
        )

    while any(
        job_next_op[job_id] < instance.jobs[job_id].num_ops
        for job_id in state.released_job_ids or frozenset()
    ):
        candidates: list[_Candidate] = []
        for job_id in sorted(state.released_job_ids or frozenset()):
            op_id = job_next_op[job_id]
            if op_id >= instance.jobs[job_id].num_ops:
                continue
            for machine_id, processing_time in instance.get_op_options(job_id, op_id):
                ready_time = job_ready_time[job_id]
                start = max(ready_time, machine_ready_time[machine_id])
                finish = start + processing_time
                candidates.append(
                    (
                        job_id,
                        op_id,
                        machine_id,
                        ready_time,
                        start,
                        finish,
                        processing_time,
                    )
                )

        if not candidates:
            raise RuntimeError("no rescheduling candidates are available")

        selected = _select_candidate(candidates, rule)
        job_id, op_id, machine_id, _ready_time, start, finish, processing_time = selected
        result.add_record(job_id, op_id, machine_id, start, processing_time)
        job_next_op[job_id] += 1
        job_ready_time[job_id] = finish
        machine_ready_time[machine_id] = finish

    result.compute_makespan()
    feasible, violations = check_feasibility(result)
    if not feasible:
        raise RuntimeError(f"dynamic reschedule produced infeasible schedule: {violations}")
    return result


def _select_candidate(candidates: list[_Candidate], rule: RescheduleRule) -> _Candidate:
    if rule == "fifo":
        ready_time, job_id, op_id = min((c[3], c[0], c[1]) for c in candidates)
        op_candidates = [
            c for c in candidates
            if (c[3], c[0], c[1]) == (ready_time, job_id, op_id)
        ]
        return min(op_candidates, key=lambda c: (c[5], c[6], c[2]))
    if rule == "spt":
        return min(candidates, key=lambda c: (c[6], c[5], c[0], c[1], c[2]))
    if rule == "eft":
        return min(candidates, key=lambda c: (c[5], c[6], c[0], c[1], c[2]))
    raise ValueError(f"unsupported reschedule rule: {rule}")


def _validate_released_jobs(state: DynamicFJSPState) -> None:
    unreleased = set(range(state.instance.num_jobs)) - set(state.released_job_ids or ())
    if unreleased:
        raise ValueError(
            "reschedule_from_state requires all jobs in the current instance "
            f"to be released; unreleased jobs: {sorted(unreleased)}"
        )


def _validate_frozen_records(
    state: DynamicFJSPState,
    frozen_records: list[ScheduleRecord],
) -> None:
    instance = state.instance
    seen: set[tuple[int, int]] = set()
    by_job: dict[int, set[int]] = {job.job_id: set() for job in instance.jobs}
    for record in frozen_records:
        if record.job_id < 0 or record.job_id >= instance.num_jobs:
            raise ValueError("frozen record job_id is out of range")
        if record.op_id < 0 or record.op_id >= instance.jobs[record.job_id].num_ops:
            raise ValueError("frozen record op_id is out of range")
        if record.machine_id < 0 or record.machine_id >= instance.num_machines:
            raise ValueError("frozen record machine_id is out of range")
        key = (record.job_id, record.op_id)
        if key in seen:
            raise ValueError("frozen records contain a duplicate operation")
        seen.add(key)
        by_job[record.job_id].add(record.op_id)

    for job_id, scheduled_ops in by_job.items():
        if not scheduled_ops:
            continue
        expected_prefix = set(range(max(scheduled_ops) + 1))
        if scheduled_ops != expected_prefix:
            raise ValueError(
                f"frozen records for job {job_id} must form a route prefix"
            )
