from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

# MachineOption: 表示一个可选加工机器, 格式为 (machine_id, processing_time).
MachineOption = Tuple[int, int]

#  工序类
@dataclass(frozen=True)
class Operation:
    """表示工件中的一道工序.

    Attributes:
        op_id: 工序在所属工件内的局部编号.
        machine_options: 该工序的可选加工机器集合, 每个元素为 (machine_id, processing_time).

    Examples:
        Operation(op_id=0, machine_options=((0, 3), (1, 5)))
    """
    op_id: int
    machine_options: Tuple[MachineOption, ...]

# 工件类
@dataclass(frozen=True)
class Job:
    """表示一个工件及其有序工序集合.

    Attributes:
        job_id: 工件编号.
        operations: 该工件的有序工序集合.

    Properties:
        num_ops: 该工件包含的工序数量.

    Examples:
        Job(
            job_id=0,
            operations=(
                Operation(0, ((0, 3), (1, 5))),
                Operation(1, ((1, 4), (2, 6))),
            ),
        )
    """
    job_id: int
    operations: Tuple[Operation, ...]

    @property
    def num_ops(self) -> int:
        return len(self.operations)

# 柔性作业车间案例类
@dataclass
class FJSPInstance:
    """表示一个柔性作业车间调度问题实例.

    Attributes:
        num_jobs: 工件数量.
        num_machines: 机器数量.
        jobs: 所有工件的列表.

    Methods:
        from_jobs_array: 从嵌套列表构造 FJSPInstance.
        get_op_options: 获取某道工序的可选机器集合.
        get_processing_time: 获取某道工序在指定机器上的加工时间.
        is_machine_eligible: 判断指定机器是否可加工某道工序.

    Notes:
        机器编号默认从 0 开始, 即 0, 1, ..., num_machines - 1.
        工序编号 op_id 只在所属工件内部有效, 唯一标识一道工序应使用 (job_id, op_id).
    """
    num_jobs: int
    num_machines: int
    jobs: List[Job] = field(default_factory=list)

    @property
    def total_ops(self) -> int:
        return sum(job.num_ops for job in self.jobs)

    @classmethod
    def from_jobs_array(
        cls,
        jobs_array: List[List[List[MachineOption]]], 
        num_machines: int | None = None,
    ) -> FJSPInstance:
        """从嵌套列表构造 FJSPInstance.

        Args:
            jobs_array: FJSP 原始数据, 结构为 jobs_array[job_id][op_id] = [(machine_id, processing_time), ...].
            num_machines: 机器数量. 若为 None, 则根据出现过的最大机器编号自动推断.

        Returns:
            由 jobs_array 构造得到的 FJSPInstance.

        Examples:
            FJSPInstance.from_jobs_array([
                [
                    [(0, 3), (1, 5)],
                    [(1, 4), (2, 6)],
                ],
            ])
        """
        num_jobs = len(jobs_array)
        if num_machines is None:
            machine_ids: set[int] = set()
            for job_ops in jobs_array:
                for op_options in job_ops:
                    for m_id, _ in op_options:
                        machine_ids.add(m_id)
            num_machines = max(machine_ids) + 1 if machine_ids else 0

        jobs: list[Job] = []
        for j_idx, job_ops in enumerate(jobs_array):
            ops: list[Operation] = []
            for o_idx, op_options in enumerate(job_ops):
                ops.append(Operation(
                    op_id=o_idx,
                    machine_options=tuple((m_id, pt) for m_id, pt in op_options),
                ))
            jobs.append(Job(job_id=j_idx, operations=tuple(ops)))

        return cls(num_jobs=num_jobs, num_machines=num_machines, jobs=jobs)

    def get_op_options(self, job_id: int, op_id: int) -> Tuple[MachineOption, ...]:
        """返回指定工序的可选加工机器集合.

        Args:
            job_id: 工件编号.
            op_id: 工序编号.

        Returns:
            可选机器集合, 每个元素为 (machine_id, processing_time).
        """
        return self.jobs[job_id].operations[op_id].machine_options
    
    def get_processing_time(self, job_id: int, op_id: int, machine_id: int) -> int:
        """返回指定工序在指定机器上的加工时间.

        Args:
            job_id: 工件编号.
            op_id: 工序编号.
            machine_id: 机器编号.

        Returns:
            指定工序在指定机器上的加工时间.

        Raises:
            ValueError: 当该机器不能加工该工序时抛出.
        """
        for m_id, pt in self.get_op_options(job_id, op_id):
            if m_id == machine_id:
                return pt
        raise ValueError(f"Machine {machine_id} not in options for Job {job_id} Op {op_id}")
    
    def is_machine_eligible(self, job_id: int, op_id: int, machine_id: int) -> bool:
        """判断指定机器是否可加工指定工序.

        Args:
            job_id: 工件编号.
            op_id: 工序编号.
            machine_id: 机器编号.

        Returns:
            若机器可加工该工序, 返回 True, 否则返回 False.
        """
        return any(m_id == machine_id for m_id, _ in self.get_op_options(job_id, op_id))


def create_toy_instance() -> FJSPInstance:
    """创建一个用于测试和调试的小规模 FJSP 实例.

    Returns:
        一个包含 3 个工件和 3 台机器的 FJSPInstance.

    Examples:
        instance = create_toy_instance()
        instance.total_ops
    """
    jobs_array: List[List[List[MachineOption]]] = [
        [
            [(0, 3), (1, 5)], 
            [(1, 4), (2, 6)],
        ],
        [
            [(0, 2), (2, 4)],
            [(1, 3)],
        ],
        [
            [(0, 5)],
            [(1, 3), (2, 2)],
            [(0, 1), (1, 2)],
        ],
    ]
    return FJSPInstance.from_jobs_array(jobs_array)
