from __future__ import annotations

import random
from typing import Dict, List, Tuple

from src.data.instance import FJSPInstance
from src.scheduling.encoding import ScheduleResult


def fifo_solve(instance: FJSPInstance) -> ScheduleResult:
    """使用 FIFO 规则构造一个基础调度结果.

    Args:
        instance: 待求解的 FJSP 问题实例.

    Returns:
        由 FIFO 规则生成的可行调度结果.

    Raises:
        RuntimeError: 当生成的调度结果不可行时抛出.

    Notes:
        该规则按工件编号和工序编号顺序生成 assignment.
        每道工序始终选择第一个可选机器, 不比较加工时间.
    """
    # FIFO：每道工序始终选择第一个可选机器（不比较加工时间）
    assignment: List[Tuple[int, int, int]] = []
    for job_id in range(instance.num_jobs):
        for op_id in range(instance.jobs[job_id].num_ops):
            first_machine, _ = instance.jobs[job_id].operations[op_id].machine_options[0]
            assignment.append((job_id, op_id, first_machine))

    from src.scheduling.decoding import decode_schedule
    result = decode_schedule(assignment, instance)

    from src.scheduling.feasibility import check_feasibility
    feasible, violations = check_feasibility(result)
    if not feasible:
        raise RuntimeError(f"fifo_solve produced infeasible schedule: {violations}")

    result.compute_makespan()
    return result


def spt_solve(instance: FJSPInstance) -> ScheduleResult:
    """使用 SPT 规则构造一个基础调度结果.

    Args:
        instance: 待求解的 FJSP 问题实例.

    Returns:
        由 SPT 规则生成的可行调度结果.

    Raises:
        RuntimeError: 当生成的调度结果不可行时抛出.

    Notes:
        SPT 表示 shortest processing time.
        该规则按工件编号和工序编号顺序生成 assignment.
        每道工序选择加工时间最短的可选机器.
    """
    # SPT：每道工序选择加工时间最短的机器
    from src.scheduling.decoding import decode_schedule

    assignment: List[Tuple[int, int, int]] = []
    for job_id in range(instance.num_jobs):
        for op_id in range(instance.jobs[job_id].num_ops):
            options = instance.jobs[job_id].operations[op_id].machine_options
            best_machine, _ = min(options, key=lambda x: x[1])
            assignment.append((job_id, op_id, best_machine))

    result = decode_schedule(assignment, instance)

    from src.scheduling.feasibility import check_feasibility
    feasible, violations = check_feasibility(result)
    if not feasible:
        raise RuntimeError(f"spt_solve produced infeasible schedule: {violations}")

    result.compute_makespan()
    return result


def earliest_finish_time_solve(instance: FJSPInstance) -> ScheduleResult:
    """使用最早完工时间贪心规则构造调度结果.

    Args:
        instance: 待求解的 FJSP 问题实例.

    Returns:
        由最早完工时间规则生成的可行调度结果.

    Raises:
        RuntimeError: 当生成的调度结果不可行时抛出.

    Notes:
        每轮只考虑每个工件当前待调度的下一道工序.
        在所有候选 (job_id, op_id, machine_id) 组合中,
        选择预计完成时间最早的组合加入 assignment.
    """
    # 贪心：每次选择所有待调度工序中最早能完成的 (job, op, machine) 组合
    from src.scheduling.decoding import decode_schedule

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

    from src.scheduling.feasibility import check_feasibility
    feasible, violations = check_feasibility(result)
    if not feasible:
        raise RuntimeError(f"earliest_finish_time_solve produced infeasible schedule: {violations}")

    result.compute_makespan()
    return result


def random_solve(instance: FJSPInstance, seed: int = 42) -> ScheduleResult:
    """使用随机机器选择规则构造调度结果.

    Args:
        instance: 待求解的 FJSP 问题实例.
        seed: 随机种子, 用于保证结果可复现.

    Returns:
        由随机规则生成的可行调度结果.

    Raises:
        RuntimeError: 当生成的调度结果不可行时抛出.

    Notes:
        该规则按工件编号和工序编号顺序生成 assignment.
        每道工序从其可选机器集合中随机选择一台机器.
    """
    # Random：每道工序随机选择一个可选机器，种子保证可复现
    rng = random.Random(seed)

    from src.scheduling.decoding import decode_schedule

    assignment: List[Tuple[int, int, int]] = []
    for job_id in range(instance.num_jobs):
        for op_id in range(instance.jobs[job_id].num_ops):
            options = instance.jobs[job_id].operations[op_id].machine_options
            m_id, _pt = rng.choice(options)
            assignment.append((job_id, op_id, m_id))

    result = decode_schedule(assignment, instance)

    from src.scheduling.feasibility import check_feasibility
    feasible, violations = check_feasibility(result)
    if not feasible:
        raise RuntimeError(f"random_solve produced infeasible schedule: {violations}")

    result.compute_makespan()
    return result
