from __future__ import annotations

from typing import List, Tuple, Dict
from dataclasses import dataclass

from src.data.instance import FJSPInstance
from src.scheduling.encoding import ScheduleRecord, ScheduleResult


def decode_schedule(
    assignment: List[Tuple[int, int, int]],
    instance: FJSPInstance,
) -> ScheduleResult:
    # 半主动解码：按 assignment 顺序逐个放置工序，取最早可行开始时间
    result = ScheduleResult(instance=instance)

    job_next_start: Dict[int, int] = {j: 0 for j in range(instance.num_jobs)}
    machine_next_available: Dict[int, int] = {m: 0 for m in range(instance.num_machines)}

    for job_id, op_id, machine_id in assignment:
        pt = instance.get_processing_time(job_id, op_id, machine_id)

        # 最早可行开始时间 = max(工件前序工序完成时间, 机器空闲时间)
        start = max(job_next_start[job_id], machine_next_available[machine_id])
        end = start + pt

        result.add_record(job_id, op_id, machine_id, start, pt)

        job_next_start[job_id] = end
        machine_next_available[machine_id] = end

    result.compute_makespan()
    return result
