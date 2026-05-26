from __future__ import annotations

from typing import Dict, List, Tuple

from src.data.instance import FJSPInstance
from src.scheduling.encoding import ScheduleResult


def decode_schedule(
    assignment: List[Tuple[int, int, int]],
    instance: FJSPInstance,
) -> ScheduleResult:
    """Decode an operation-machine assignment into a semi-active schedule.

    The assignment order decides which operation is placed next. Each operation
    is placed at the earliest time that satisfies the job precedence state and
    the selected machine's availability.
    """

    result = ScheduleResult(instance=instance)

    job_next_start: Dict[int, int] = {j: 0 for j in range(instance.num_jobs)}
    machine_next_available: Dict[int, int] = {m: 0 for m in range(instance.num_machines)}

    for job_id, op_id, machine_id in assignment:
        pt = instance.get_processing_time(job_id, op_id, machine_id)

        start = max(job_next_start[job_id], machine_next_available[machine_id])
        end = start + pt

        result.add_record(job_id, op_id, machine_id, start, pt)

        job_next_start[job_id] = end
        machine_next_available[machine_id] = end

    result.compute_makespan()
    return result
