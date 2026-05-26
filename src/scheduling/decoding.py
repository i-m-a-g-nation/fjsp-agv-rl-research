from __future__ import annotations

from typing import List, Tuple, Dict
from dataclasses import dataclass

from src.data.instance import FJSPInstance
from src.scheduling.encoding import ScheduleRecord, ScheduleResult


def decode_schedule(
    assignment: List[Tuple[int, int, int]],
    instance: FJSPInstance,
) -> ScheduleResult:
    """将工序-机器分配序列解码为具体调度结果.

    Args:
        assignment: 工序分配序列, 每个元素为 (job_id, op_id, machine_id).
        instance: 待解码的 FJSP 问题实例.

    Returns:
        包含调度记录和最大完工时间的 ScheduleResult.

    Notes:
        该函数采用半主动解码方式.
        解码时按 assignment 给定顺序逐个放置工序.
        每道工序被安排在满足工件前序约束和机器可用约束的最早开始时间.

        当前实现默认 assignment 中同一工件的工序顺序已经合法.
        若 assignment 中出现 Op 1 早于 Op 0 的情况, 该函数不会主动检查.
    """
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
