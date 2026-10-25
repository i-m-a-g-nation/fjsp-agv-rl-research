from __future__ import annotations

import random
from typing import Dict, List, Tuple

from src.data.instance import FJSPInstance
from src.scheduling.encoding import ScheduleResult

__all__ = [
    "fifo_solve",
    "spt_solve",
    "earliest_finish_time_solve",
    "earliest_available_machine_solve",
    "random_solve",
]


def _decode_and_validate(
    assignment: List[Tuple[int, int, int]],
    instance: FJSPInstance,
    solver_name: str,
) -> ScheduleResult:
    """Decode an assignment and enforce the common feasibility contract."""

    from src.scheduling.decoding import decode_schedule
    from src.scheduling.feasibility import check_feasibility

    result = decode_schedule(assignment, instance)
    feasible, violations = check_feasibility(result)
    if not feasible:
        raise RuntimeError(f"{solver_name} produced infeasible schedule: {violations}")

    result.compute_makespan()
    return result


def fifo_solve(instance: FJSPInstance) -> ScheduleResult:
    """Simple baseline: job order plus first eligible machine."""

    assignment: List[Tuple[int, int, int]] = []
    # This legacy baseline intentionally ignores ready queues. It is useful as
    # a simple comparison point, not as a strict FIFO dispatching rule.
    for job_id in range(instance.num_jobs):
        for op_id in range(instance.jobs[job_id].num_ops):
            first_machine, _ = instance.jobs[job_id].operations[op_id].machine_options[0]
            assignment.append((job_id, op_id, first_machine))

    return _decode_and_validate(assignment, instance, "fifo_solve")


def spt_solve(instance: FJSPInstance) -> ScheduleResult:
    """Simple baseline: job order plus shortest processing-time machine."""

    assignment: List[Tuple[int, int, int]] = []
    # Legacy SPT chooses the shortest machine for each operation, while keeping
    # the fixed job/order traversal.
    for job_id in range(instance.num_jobs):
        for op_id in range(instance.jobs[job_id].num_ops):
            options = instance.jobs[job_id].operations[op_id].machine_options
            best_machine, _ = min(options, key=lambda x: x[1])
            assignment.append((job_id, op_id, best_machine))

    return _decode_and_validate(assignment, instance, "spt_solve")


def earliest_available_machine_solve(instance: FJSPInstance) -> ScheduleResult:
    """FIFO-ready operation plus earliest feasible start/machine-ID EAM variant."""
    from src.solvers.dispatching import dispatch_eam_solve

    return dispatch_eam_solve(instance)


def earliest_finish_time_solve(instance: FJSPInstance) -> ScheduleResult:
    """Greedy earliest-finish-time baseline over ready operations."""

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

    return _decode_and_validate(assignment, instance, "earliest_finish_time_solve")


def random_solve(instance: FJSPInstance, seed: int = 42) -> ScheduleResult:
    """Simple baseline: job order plus random eligible machine."""

    rng = random.Random(seed)
    assignment: List[Tuple[int, int, int]] = []
    # The seed makes the baseline reproducible for experiments.
    for job_id in range(instance.num_jobs):
        for op_id in range(instance.jobs[job_id].num_ops):
            options = instance.jobs[job_id].operations[op_id].machine_options
            m_id, _pt = rng.choice(options)
            assignment.append((job_id, op_id, m_id))

    return _decode_and_validate(assignment, instance, "random_solve")
