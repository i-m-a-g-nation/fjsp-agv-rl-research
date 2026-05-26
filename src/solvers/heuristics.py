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
    # This is the key difference from the simple job-order baselines below.
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


def fifo_solve(instance: FJSPInstance) -> ScheduleResult:
    """Simple baseline: job order plus first eligible machine."""

    from src.scheduling.decoding import decode_schedule
    from src.scheduling.feasibility import check_feasibility

    assignment: List[Tuple[int, int, int]] = []
    # This legacy baseline intentionally ignores ready queues. It is useful as
    # a simple comparison point, not as a strict FIFO dispatching rule.
    for job_id in range(instance.num_jobs):
        for op_id in range(instance.jobs[job_id].num_ops):
            first_machine, _ = instance.jobs[job_id].operations[op_id].machine_options[0]
            assignment.append((job_id, op_id, first_machine))

    result = decode_schedule(assignment, instance)
    feasible, violations = check_feasibility(result)
    if not feasible:
        raise RuntimeError(f"fifo_solve produced infeasible schedule: {violations}")

    result.compute_makespan()
    return result


def spt_solve(instance: FJSPInstance) -> ScheduleResult:
    """Simple baseline: job order plus shortest processing-time machine."""

    from src.scheduling.decoding import decode_schedule
    from src.scheduling.feasibility import check_feasibility

    assignment: List[Tuple[int, int, int]] = []
    # Legacy SPT chooses the shortest machine for each operation, while keeping
    # the fixed job/order traversal.
    for job_id in range(instance.num_jobs):
        for op_id in range(instance.jobs[job_id].num_ops):
            options = instance.jobs[job_id].operations[op_id].machine_options
            best_machine, _ = min(options, key=lambda x: x[1])
            assignment.append((job_id, op_id, best_machine))

    result = decode_schedule(assignment, instance)
    feasible, violations = check_feasibility(result)
    if not feasible:
        raise RuntimeError(f"spt_solve produced infeasible schedule: {violations}")

    result.compute_makespan()
    return result


def earliest_finish_time_solve(instance: FJSPInstance) -> ScheduleResult:
    """Greedy earliest-finish-time baseline over ready operations."""

    from src.scheduling.decoding import decode_schedule
    from src.scheduling.feasibility import check_feasibility

    assignment: List[Tuple[int, int, int]] = []
    job_next_start: Dict[int, int] = {j: 0 for j in range(instance.num_jobs)}
    machine_available: Dict[int, int] = {m: 0 for m in range(instance.num_machines)}
    job_next_op: Dict[int, int] = {j: 0 for j in range(instance.num_jobs)}

    unscheduled = sum(job.num_ops for job in instance.jobs)

    while unscheduled > 0:
        best_job = -1
        best_op = -1
        best_machine = -1
        best_finish = float("inf")

        for job_id in range(instance.num_jobs):
            op_id = job_next_op[job_id]
            if op_id >= instance.jobs[job_id].num_ops:
                continue

            ready_time = job_next_start[job_id]

            # Evaluate all eligible machines for each ready operation and pick
            # the operation-machine pair with the earliest tentative finish.
            for m_id, pt in instance.jobs[job_id].operations[op_id].machine_options:
                start = max(ready_time, machine_available[m_id])
                finish = start + pt
                if finish < best_finish:
                    best_finish = finish
                    best_job = job_id
                    best_op = op_id
                    best_machine = m_id

        if best_job == -1:
            break

        pt = instance.get_processing_time(best_job, best_op, best_machine)
        start = max(job_next_start[best_job], machine_available[best_machine])
        assignment.append((best_job, best_op, best_machine))
        job_next_start[best_job] = start + pt
        machine_available[best_machine] = start + pt
        job_next_op[best_job] = best_op + 1
        unscheduled -= 1

    result = decode_schedule(assignment, instance)
    feasible, violations = check_feasibility(result)
    if not feasible:
        raise RuntimeError(f"earliest_finish_time_solve produced infeasible schedule: {violations}")

    result.compute_makespan()
    return result


def random_solve(instance: FJSPInstance, seed: int = 42) -> ScheduleResult:
    """Simple baseline: job order plus random eligible machine."""

    from src.scheduling.decoding import decode_schedule
    from src.scheduling.feasibility import check_feasibility

    rng = random.Random(seed)
    assignment: List[Tuple[int, int, int]] = []
    # The seed makes the baseline reproducible for experiments.
    for job_id in range(instance.num_jobs):
        for op_id in range(instance.jobs[job_id].num_ops):
            options = instance.jobs[job_id].operations[op_id].machine_options
            m_id, _pt = rng.choice(options)
            assignment.append((job_id, op_id, m_id))

    result = decode_schedule(assignment, instance)
    feasible, violations = check_feasibility(result)
    if not feasible:
        raise RuntimeError(f"random_solve produced infeasible schedule: {violations}")

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
