from __future__ import annotations

from typing import Tuple

from ortools.sat.python import cp_model

from src.data.instance import FJSPInstance
from src.scheduling.encoding import ScheduleRecord, ScheduleResult
from src.scheduling.feasibility import check_feasibility


class OrtoolsSolverError(Exception):
    """表示 OR-Tools 求解过程中出现的异常.

    Notes:
        当 CP-SAT 返回不可行状态, 非预期状态, 或提取结果失败时抛出.
    """
    pass


def _compute_horizon(instance: FJSPInstance) -> int:
    """计算 CP-SAT 模型的时间上界.

    Args:
        instance: 待求解的 FJSP 问题实例.

    Returns:
        一个保守的时间上界 horizon.

    Notes:
        当前实现将每道工序的最大可选加工时间求和.
        该值通常不是最紧上界, 但可作为所有 start/end/makespan 变量的取值范围.
    """
    total = 0
    for job in instance.jobs:
        for op in job.operations:
            total += max(pt for _m, pt in op.machine_options)
    return total


def ortools_solve(
    instance: FJSPInstance,
    time_limit: float = 60.0,
    num_workers: int = 0,
) -> ScheduleResult:
    """使用 OR-Tools CP-SAT 求解 FJSP 实例.

    Args:
        instance: 待求解的 FJSP 问题实例.
        time_limit: CP-SAT 求解时间上限, 单位为秒.
        num_workers: 并行搜索线程数. 若为 0, 使用 OR-Tools 默认设置.

    Returns:
        CP-SAT 生成的调度结果.

    Raises:
        OrtoolsSolverError: 当模型不可行, 求解状态异常, 或结果提取失败时抛出.

    Notes:
        该模型为每个 (job_id, op_id, machine_id) 组合创建可选区间变量.
        presence=True 表示该工序选择该机器加工.
        ExactlyOne 约束保证每道工序恰好选择一台机器.
        Precedence 约束保证同一工件内部工序按顺序加工.
        NoOverlap 约束保证同一机器上的工序不重叠.
        目标函数为最小化 makespan.
    """
    model = cp_model.CpModel()
    horizon = _compute_horizon(instance)

    start_vars: dict[Tuple[int, int, int], cp_model.IntVar] = {}
    end_vars: dict[Tuple[int, int, int], cp_model.IntVar] = {}
    interval_vars: dict[Tuple[int, int, int], cp_model.IntervalVar] = {}
    presence_vars: dict[Tuple[int, int, int], cp_model.IntVar] = {}

    # 为每个 (工序, 机器) 组合创建可选区间变量
    # presence=True 表示该工序在该机器上加工，否则区间不生效
    for j_id, job in enumerate(instance.jobs):
        for o_id, op in enumerate(job.operations):
            for m_id, pt in op.machine_options:
                suffix = f"j{j_id}_o{o_id}_m{m_id}"
                start = model.NewIntVar(0, horizon, f"start_{suffix}")
                end = model.NewIntVar(0, horizon, f"end_{suffix}")
                presence = model.NewBoolVar(f"presence_{suffix}")
                interval = model.NewOptionalIntervalVar(
                    start, pt, end, presence, f"interval_{suffix}",
                )
                start_vars[(j_id, o_id, m_id)] = start
                end_vars[(j_id, o_id, m_id)] = end
                interval_vars[(j_id, o_id, m_id)] = interval
                presence_vars[(j_id, o_id, m_id)] = presence

    # ExactlyOne 约束：每道工序恰好选择一个机器
    for j_id, job in enumerate(instance.jobs):
        for o_id, op in enumerate(job.operations):
            machine_presences = [
                presence_vars[(j_id, o_id, m_id)]
                for m_id, _pt in op.machine_options
            ]
            model.AddExactlyOne(machine_presences)

        # Precedence 约束：同一工件相邻工序，前序完成 <= 后序开始（仅当两者均被选中时生效）
        for o_id in range(job.num_ops - 1):
            cur_machines = job.operations[o_id].machine_options
            next_machines = job.operations[o_id + 1].machine_options
            for m_cur, _ptc in cur_machines:
                for m_next, _ptn in next_machines:
                    p_cur = presence_vars[(j_id, o_id, m_cur)]
                    p_next = presence_vars[(j_id, o_id + 1, m_next)]
                    end_cur = end_vars[(j_id, o_id, m_cur)]
                    start_next = start_vars[(j_id, o_id + 1, m_next)]
                    model.Add(end_cur <= start_next).OnlyEnforceIf([p_cur, p_next])

    # NoOverlap 约束：同一机器上的所有区间不重叠（仅 presence=True 的区间生效）
    for m_id in range(instance.num_machines):
        machine_intervals: list[cp_model.IntervalVar] = []
        for j_id, job in enumerate(instance.jobs):
            for o_id, op in enumerate(job.operations):
                for op_m_id, _pt in op.machine_options:
                    if op_m_id == m_id:
                        machine_intervals.append(
                            interval_vars[(j_id, o_id, m_id)]
                        )
        if machine_intervals:
            model.AddNoOverlap(machine_intervals)

    # 目标变量：makespan >= 所有末道工序的 end（取最大值）
    makespan_var = model.NewIntVar(0, horizon, "makespan")
    for j_id, job in enumerate(instance.jobs):
        last_o = job.num_ops - 1
        for m_id, _pt in job.operations[last_o].machine_options:
            model.Add(makespan_var >= end_vars[(j_id, last_o, m_id)]).OnlyEnforceIf(
                presence_vars[(j_id, last_o, m_id)]
            )

    model.Minimize(makespan_var)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    if num_workers > 0:
        solver.parameters.num_search_workers = num_workers
    solver.parameters.log_search_progress = False

    status = solver.Solve(model)
    status_name = solver.StatusName(status)

    if status == cp_model.INFEASIBLE:
        raise OrtoolsSolverError("CP-SAT returned INFEASIBLE")

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        result = _extract_result(instance, solver, start_vars, end_vars, presence_vars, status_name)
        return result

    raise OrtoolsSolverError(f"CP-SAT returned unexpected status: {status_name}")


def _extract_result(
    instance: FJSPInstance,
    solver: cp_model.CpSolver,
    start_vars: dict,
    end_vars: dict,
    presence_vars: dict,
    status_name: str,
) -> ScheduleResult:
    """从 CP-SAT 求解结果中提取 ScheduleResult.

    Args:
        instance: 已求解的 FJSP 问题实例.
        solver: 已完成求解的 CP-SAT 求解器.
        start_vars: 工序-机器组合对应的开始时间变量.
        end_vars: 工序-机器组合对应的结束时间变量.
        presence_vars: 工序-机器组合对应的选择变量.
        status_name: CP-SAT 返回的求解状态名称.

    Returns:
        从 CP-SAT 解中提取得到的调度结果.

    Raises:
        OrtoolsSolverError: 当某道工序未被分配机器, 时间不一致, 或结果不可行时抛出.

    Notes:
        该函数遍历每道工序的所有可选机器.
        若某个 presence 变量取值为 1, 则说明该工序选择该机器加工.
        提取完成后会调用 check_feasibility 进行可行性复查.
    """
    solver_status = "OPTIMAL" if status_name == "OPTIMAL" else "FEASIBLE"
    result = ScheduleResult(instance=instance, solver_status=solver_status)

    for j_id, job in enumerate(instance.jobs):
        for o_id, op in enumerate(job.operations):
            assigned = False
            for m_id, pt in op.machine_options:
                if solver.Value(presence_vars[(j_id, o_id, m_id)]) == 1:
                    start_val = solver.Value(start_vars[(j_id, o_id, m_id)])
                    end_val = solver.Value(end_vars[(j_id, o_id, m_id)])
                    if end_val != start_val + pt:
                        raise OrtoolsSolverError(
                            f"Job {j_id} Op {o_id} Machine {m_id}: "
                            f"end={end_val} != start={start_val} + pt={pt}"
                        )
                    result.add_record(j_id, o_id, m_id, start=start_val, processing_time=pt)
                    assigned = True
                    break
            if not assigned:
                raise OrtoolsSolverError(
                    f"Job {j_id} Op {o_id}: no machine assigned by solver"
                )

    result.compute_makespan()

    feasible, violations = check_feasibility(result)
    if not feasible:
        raise OrtoolsSolverError(
            f"CP-SAT ({solver_status}) produced infeasible schedule: {violations}"
        )

    return result
