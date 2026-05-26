from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from src.data.instance import FJSPInstance


@dataclass
# 调度记录类
class ScheduleRecord:
    """表示一条工序调度记录.

    Attributes:
        job_id: 工件编号.
        op_id: 工序编号.
        machine_id: 机器编号.
        start: 工序开始时间.
        end: 工序结束时间.
        processing_time: 工序加工时间.

    Examples:
        ScheduleRecord(
            job_id=0,
            op_id=0,
            machine_id=0,
            start=0,
            end=3,
            processing_time=3,
        )
    """
    job_id: int
    op_id: int
    machine_id: int
    start: int
    end: int
    processing_time: int


@dataclass  # 与 frozen=True 的 Operation/Job 不同，ScheduleResult 是可变的（可追加记录）
# 调度结果类
class ScheduleResult:
    """表示一次解码或求解得到的调度结果.

    Attributes:
        records: 工序调度记录列表.
        makespan: 最大完工时间, 即所有工序结束时间的最大值.
        instance: 该调度结果对应的 FJSP 实例.
        solver_status: 求解器状态或算法状态.

    Methods:
        add_record: 添加一条工序调度记录.
        compute_makespan: 计算并更新最大完工时间.
        sorted_records: 按工件编号和工序编号返回调度记录.

    Notes:
        ScheduleResult 是可变对象, 可在解码或求解过程中持续追加记录.
    """
    records: List[ScheduleRecord] = field(default_factory=list)
    makespan: int = 0
    instance: FJSPInstance | None = None
    solver_status: str | None = None

    def add_record(self, job_id: int, op_id: int, machine_id: int,
                   start: int, processing_time: int) -> ScheduleRecord:
        """添加一条工序调度记录.

        Args:
            job_id: 工件编号.
            op_id: 工序编号.
            machine_id: 机器编号.
            start: 工序开始时间.
            processing_time: 工序加工时间.

        Returns:
            新增的 ScheduleRecord.
        """
        rec = ScheduleRecord(
            job_id=job_id,
            op_id=op_id,
            machine_id=machine_id,
            start=start,
            end=start + processing_time,
            processing_time=processing_time,
        )
        self.records.append(rec)
        return rec

    def compute_makespan(self) -> int:
        """计算并更新最大完工时间.

        Returns:
            当前调度结果的最大完工时间. 若没有调度记录, 返回 0.
        """
        if not self.records:
            self.makespan = 0
            return 0
        self.makespan = max(r.end for r in self.records)
        return self.makespan

    def sorted_records(self) -> List[ScheduleRecord]:
        """按工件路线顺序返回调度记录.

        Returns:
            按 (job_id, op_id) 排序后的调度记录列表.

        Notes:
            该排序用于查看每个工件内部的工序路线, 不表示真实加工时间顺序.
            若要查看机器加工顺序, 应按 (machine_id, start) 排序.
        """
        return sorted(self.records, key=lambda r: (r.job_id, r.op_id))
