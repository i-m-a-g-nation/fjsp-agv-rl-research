from __future__ import annotations

import random
from typing import Callable, Dict, List, Tuple

from src.data.instance import FJSPInstance
from src.scheduling.encoding import ScheduleResult

# Candidate format:
# (job_id, op_id, machine_id, job_ready_time, start, finish, processing_time)
# start/finish are tentative values used only for selecting the next move.
# The final ScheduleResult is still built by decode_schedule for consistency.
_Candidate = Tuple[int, int, int, int, int, int, int]
_SelectFn = Callable[[List[_Candidate], FJSPInstance, random.Random | None], _Candidate]

__all__ = [
    "dispatch_fifo_solve",
    "dispatch_spt_solve",
    "dispatch_eam_solve",
    "dispatch_eft_solve",
    "dispatch_mwkr_solve",
    "dispatch_mopnr_solve",
    "dispatch_random_solve",
]


def _dispatch_solve(
    instance: FJSPInstance,
    select_fn: _SelectFn,
    rng: random.Random | None = None,
) -> ScheduleResult:
    """Shared strict dispatching-rule framework."""

    from src.scheduling.decoding import decode_schedule
    from src.scheduling.feasibility import check_feasibility

    job_ready_time: Dict[int, int] = {j: 0 for j in range(instance.num_jobs)}
    machine_ready_time: Dict[int, int] = {m: 0 for m in range(instance.num_machines)}
    job_next_op: Dict[int, int] = {j: 0 for j in range(instance.num_jobs)}
    assignment: List[Tuple[int, int, int]] = []

    # job_next_op makes only the next operation of each unfinished job ready.
    # This is the key difference from the simple job-order baselines.
    while any(
        job_next_op[j] < instance.jobs[j].num_ops
        for j in range(instance.num_jobs)
    ):
        candidates: List[_Candidate] = []
        for j_id in range(instance.num_jobs):
            o_id = job_next_op[j_id]
            if o_id >= instance.jobs[j_id].num_ops:
                continue
            for m_id, pt in instance.jobs[j_id].operations[o_id].machine_options:
                ready_time = job_ready_time[j_id]
                # A candidate can start only after both its job and machine are
                # ready, so finish time depends on the current partial schedule.
                start = max(ready_time, machine_ready_time[m_id])
                finish = start + pt
                candidates.append((j_id, o_id, m_id, ready_time, start, finish, pt))

        if not candidates:
            break

        selected = select_fn(candidates, instance, rng)
        j_id, o_id, m_id, _ready_time, _start, finish, _pt = selected
        assignment.append((j_id, o_id, m_id))

        # Update the partial schedule state before constructing candidates for
        # the next dispatching step.
        job_ready_time[j_id] = finish
        machine_ready_time[m_id] = finish
        job_next_op[j_id] += 1

    # Decode and re-check the final schedule so every solver has the same
    # output contract: never silently return an infeasible result.
    result = decode_schedule(assignment, instance)
    feasible, violations = check_feasibility(result)
    if not feasible:
        raise RuntimeError(f"dispatching rule produced infeasible schedule: {violations}")
    result.compute_makespan()
    return result


def dispatch_fifo_solve(instance: FJSPInstance) -> ScheduleResult:
    """Strict FIFO dispatching rule.

    Select the ready operation with the earliest ready time, using job and
    operation ids as deterministic tie-breakers. Then choose that operation's
    earliest-finish machine.
    """

    def _fifo_select(
        candidates: List[_Candidate],
        _inst: FJSPInstance,
        _rng: random.Random | None,
    ) -> _Candidate:
        # FIFO first decides which operation entered the ready set earliest.
        ready_time, job_id, op_id = min(
            (c[3], c[0], c[1])
            for c in candidates
        )
        op_candidates = [
            c for c in candidates
            if (c[3], c[0], c[1]) == (ready_time, job_id, op_id)
        ]
        # Once the operation is fixed, choose its best machine by finish time.
        return min(op_candidates, key=lambda c: (c[5], c[6], c[2]))

    return _dispatch_solve(instance, _fifo_select)


def dispatch_eam_solve(instance: FJSPInstance) -> ScheduleResult:
    """Project EAM variant: FIFO operation, then earliest feasible machine start.

    Select the operation by (ready_time, job_id, op_id), then its machine by
    (max(job_ready, machine_ready), machine_id). Processing time does not rank
    machines; tied feasible starts use machine ID even if raw idle times differ.
    """

    def _eam_select(candidates, _inst, _rng):
        operation = min((c[3], c[0], c[1]) for c in candidates)
        choices = [c for c in candidates if (c[3], c[0], c[1]) == operation]
        return min(choices, key=lambda c: (c[4], c[2]))

    return _dispatch_solve(instance, _eam_select)


def dispatch_spt_solve(instance: FJSPInstance) -> ScheduleResult:
    """Strict SPT rule over ready operation-machine pairs."""

    def _spt_select(
        candidates: List[_Candidate],
        _inst: FJSPInstance,
        _rng: random.Random | None,
    ) -> _Candidate:
        # SPT ranks pairs by processing time first; finish time is only a
        # deterministic tie-breaker.
        return min(candidates, key=lambda c: (c[6], c[5], c[0], c[1], c[2]))

    return _dispatch_solve(instance, _spt_select)


def dispatch_eft_solve(instance: FJSPInstance) -> ScheduleResult:
    """Strict earliest-finish-time rule over ready operation-machine pairs."""

    def _eft_select(
        candidates: List[_Candidate],
        _inst: FJSPInstance,
        _rng: random.Random | None,
    ) -> _Candidate:
        # EFT ranks pairs by the earliest completion implied by current machine
        # availability and job readiness.
        return min(candidates, key=lambda c: (c[5], c[6], c[0], c[1], c[2]))

    return _dispatch_solve(instance, _eft_select)


def _remaining_min_work(instance: FJSPInstance, job_id: int, op_id: int) -> int:
    """Return remaining route work using each operation's fastest machine."""

    remaining_work = 0
    for operation in instance.jobs[job_id].operations[op_id:]:
        remaining_work += min(pt for _m_id, pt in operation.machine_options)
    return remaining_work


def dispatch_mwkr_solve(instance: FJSPInstance) -> ScheduleResult:
    """Strict MWKR dispatching rule over ready operations.

    MWKR means most work remaining. For FJSP, remaining work is estimated as
    the sum of the minimum eligible processing time for the current and future
    operations in the same job. After the job/operation is selected, the machine
    tie-breaker chooses the earliest-finish machine.
    """

    def _mwkr_select(
        candidates: List[_Candidate],
        inst: FJSPInstance,
        _rng: random.Random | None,
    ) -> _Candidate:
        # Rank the ready operation by remaining job work first. The remaining
        # work estimate is independent of the candidate machine, so MWKR does
        # not accidentally prefer a slower machine just to inflate the score.
        best_work = max(
            _remaining_min_work(inst, c[0], c[1])
            for c in candidates
        )
        best_work_candidates = [
            c for c in candidates
            if _remaining_min_work(inst, c[0], c[1]) == best_work
        ]
        return min(best_work_candidates, key=lambda c: (c[5], c[6], c[0], c[1], c[2]))

    return _dispatch_solve(instance, _mwkr_select)


def dispatch_mopnr_solve(instance: FJSPInstance) -> ScheduleResult:
    """Strict MOPNR dispatching rule over ready operations.

    MOPNR means most operations remaining. Rank each ready job by the number of
    operations from its current operation through the end of its route. After
    the job/operation is selected, choose its earliest-finish eligible machine.
    """

    def _mopnr_select(
        candidates: List[_Candidate],
        inst: FJSPInstance,
        _rng: random.Random | None,
    ) -> _Candidate:
        best_count = max(
            inst.jobs[c[0]].num_ops - c[1]
            for c in candidates
        )
        best_count_candidates = [
            c for c in candidates
            if inst.jobs[c[0]].num_ops - c[1] == best_count
        ]
        return min(best_count_candidates, key=lambda c: (c[5], c[6], c[0], c[1], c[2]))

    return _dispatch_solve(instance, _mopnr_select)


def dispatch_random_solve(instance: FJSPInstance, seed: int = 42) -> ScheduleResult:
    """Strict random dispatching rule over ready operation-machine pairs."""

    rng = random.Random(seed)

    def _random_select(
        candidates: List[_Candidate],
        _inst: FJSPInstance,
        _rng: random.Random | None,
    ) -> _Candidate:
        if _rng is None:
            raise RuntimeError("dispatch_random_solve requires a random generator")
        # Random dispatching samples from valid ready pairs only.
        return _rng.choice(candidates)

    return _dispatch_solve(instance, _random_select, rng=rng)
