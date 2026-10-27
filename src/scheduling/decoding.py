from __future__ import annotations

from typing import Dict, List, Tuple

from src.data.instance import FJSPInstance, validate_instance
from src.scheduling.encoding import ScheduleResult


def decode_schedule(
    assignment: List[Tuple[int, int, int]],
    instance: FJSPInstance,
) -> ScheduleResult:
    """Decode an operation-machine assignment into a semi-active schedule.

    The complete assignment must contain every operation exactly once, in each
    job's route order, with integer identifiers and eligible machines. Invalid
    input raises TypeError or ValueError before any schedule is constructed.
    The assignment order decides which operation is placed next; placement is
    at the earliest time allowed by the job and machine availability.
    """

    validate_instance(instance)
    if not isinstance(assignment, (list, tuple)):
        raise TypeError("assignment must be a list or tuple of operation-machine triples")
    if len(assignment) != instance.total_ops:
        raise ValueError(f"assignment must contain exactly {instance.total_ops} operations")

    next_op = [0] * instance.num_jobs
    for index, row in enumerate(assignment):
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            raise ValueError(f"assignment row {index} must contain (job_id, op_id, machine_id)")
        for field, value in zip(("job_id", "op_id", "machine_id"), row):
            if type(value) is not int:
                raise TypeError(f"assignment row {index}: {field} must be a Python int (not bool)")
        job_id, op_id, machine_id = row
        if not 0 <= job_id < instance.num_jobs:
            raise ValueError(f"assignment row {index}: job_id is out of range")
        if not 0 <= op_id < instance.jobs[job_id].num_ops:
            raise ValueError(f"assignment row {index}: op_id is out of range")
        if not 0 <= machine_id < instance.num_machines:
            raise ValueError(f"assignment row {index}: machine_id is out of range")
        if op_id != next_op[job_id]:
            raise ValueError(f"assignment row {index}: duplicate or out-of-order operation for job {job_id}")
        if not instance.is_machine_eligible(job_id, op_id, machine_id):
            raise ValueError(f"assignment row {index}: machine {machine_id} is ineligible")
        next_op[job_id] += 1

    result = ScheduleResult(instance=instance)

    # job_next_start stores the finish time of the latest scheduled operation
    # for each job, enforcing route precedence during placement.
    job_next_start: Dict[int, int] = {j: 0 for j in range(instance.num_jobs)}

    # machine_next_available stores the earliest time each machine can accept
    # another operation, enforcing the single-capacity machine constraint.
    machine_next_available: Dict[int, int] = {m: 0 for m in range(instance.num_machines)}

    for job_id, op_id, machine_id in assignment:
        pt = instance.get_processing_time(job_id, op_id, machine_id)

        # Semi-active decoding places each selected operation as early as
        # possible without changing the given assignment order.
        start = max(job_next_start[job_id], machine_next_available[machine_id])
        end = start + pt

        result.add_record(job_id, op_id, machine_id, start, pt)

        # Advance both resources touched by this operation.
        job_next_start[job_id] = end
        machine_next_available[machine_id] = end

    result.compute_makespan()
    return result
