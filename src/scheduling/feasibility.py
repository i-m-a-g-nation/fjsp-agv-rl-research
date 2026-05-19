from __future__ import annotations

from typing import List

from src.data.instance import FJSPInstance
from src.scheduling.encoding import ScheduleRecord, ScheduleResult


class Violation:
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"Violation({self.code}: {self.message})"


def _record_is_ident_valid(rec, instance: FJSPInstance, violations: list[Violation]) -> bool:
    # 校验 job_id / op_id 是否在实例范围内，越界则记录违规并返回 False
    valid = True
    if rec.job_id < 0 or rec.job_id >= instance.num_jobs:
        violations.append(Violation(
            "INVALID_JOB_ID",
            f"Job ID {rec.job_id} out of range [0, {instance.num_jobs - 1}]",
        ))
        valid = False
    elif not (0 <= rec.op_id < instance.jobs[rec.job_id].num_ops):
        violations.append(Violation(
            "INVALID_OP_ID",
            f"Job {rec.job_id} Op ID {rec.op_id} out of range "
            f"[0, {instance.jobs[rec.job_id].num_ops - 1}]",
        ))
        valid = False
    return valid


def _validate_record_values(rec, violations: list[Violation]) -> None:
    # 时间合法性：start 非负、processing_time 正数、end >= start、时间一致性
    if rec.start < 0:
        violations.append(Violation(
            "INVALID_TIME",
            f"Job {rec.job_id} Op {rec.op_id}: start={rec.start} is negative",
        ))
    if rec.processing_time <= 0:
        violations.append(Violation(
            "INVALID_TIME",
            f"Job {rec.job_id} Op {rec.op_id}: processing_time={rec.processing_time} <= 0",
        ))
    if rec.end < rec.start:
        violations.append(Violation(
            "INVALID_TIME",
            f"Job {rec.job_id} Op {rec.op_id}: end={rec.end} < start={rec.start}",
        ))
    if rec.end - rec.start != rec.processing_time:
        violations.append(Violation(
            "PROCESSING_TIME_MISMATCH",
            f"Job {rec.job_id} Op {rec.op_id}: end-start={rec.end - rec.start} "
            f"!= processing_time={rec.processing_time}",
        ))


def _validate_record_machine(rec, instance: FJSPInstance, violations: list[Violation]) -> None:
    # 机器合法性：machine_id 范围、是否属于该工序可选机器、processing_time 是否匹配实例
    if rec.machine_id < 0 or rec.machine_id >= instance.num_machines:
        violations.append(Violation(
            "INVALID_MACHINE_ID",
            f"Job {rec.job_id} Op {rec.op_id}: Machine {rec.machine_id}"
            f" out of range [0, {instance.num_machines - 1}]",
        ))
        return

    if not (0 <= rec.job_id < instance.num_jobs):
        return
    if not (0 <= rec.op_id < instance.jobs[rec.job_id].num_ops):
        return

    eligible = instance.is_machine_eligible(rec.job_id, rec.op_id, rec.machine_id)
    if not eligible:
        violations.append(Violation(
            "MACHINE_INELIGIBLE",
            f"Job {rec.job_id} Op {rec.op_id}: Machine {rec.machine_id} "
            f"not in eligible set",
        ))
    else:
        expected_pt = instance.get_processing_time(rec.job_id, rec.op_id, rec.machine_id)
        if rec.processing_time != expected_pt:
            violations.append(Violation(
                "PT_INSTANCE_MISMATCH",
                f"Job {rec.job_id} Op {rec.op_id} on Machine {rec.machine_id}: "
                f"recorded pt={rec.processing_time} != instance pt={expected_pt}",
            ))


def check_feasibility(result: ScheduleResult) -> tuple[bool, list[Violation]]:
    violations: list[Violation] = []
    instance = result.instance

    if instance is None:
        violations.append(Violation("NO_INSTANCE", "ScheduleResult has no instance reference"))
        return False, violations

    if not result.records:
        violations.append(Violation("NO_RECORDS", "ScheduleResult has no records"))
        return False, violations

    # 逐条记录：时间合法性 + 标识合法性 + 机器合法性
    for rec in result.records:
        _validate_record_values(rec, violations)
        _record_is_ident_valid(rec, instance, violations)
        _validate_record_machine(rec, instance, violations)

    expected_ops = instance.total_ops
    actual_ops = len(result.records)
    if actual_ops != expected_ops:
        violations.append(Violation(
            "OP_COUNT_MISMATCH",
            f"Expected {expected_ops} operations, got {actual_ops}",
        ))

    # 约束1：每道工序恰好出现一次（无重复、无遗漏）
    ops_scheduled: set[tuple[int, int]] = set()
    for rec in result.records:
        key = (rec.job_id, rec.op_id)
        if key in ops_scheduled:
            violations.append(Violation(
                "DUPLICATE_OP",
                f"Job {rec.job_id} Op {rec.op_id} scheduled more than once",
            ))
        ops_scheduled.add(key)

    for j_id in range(instance.num_jobs):
        for o_id in range(instance.jobs[j_id].num_ops):
            if (j_id, o_id) not in ops_scheduled:
                violations.append(Violation(
                    "MISSING_OP",
                    f"Job {j_id} Op {o_id} not scheduled",
                ))

    # 约束2：同一工件内工序顺序满足先后约束（op_i.end <= op_{i+1}.start）
    job_ops: dict[int, list[ScheduleRecord]] = {}
    for rec in result.records:
        job_ops.setdefault(rec.job_id, []).append(rec)

    for j_id, ops in job_ops.items():
        ops_sorted = sorted(ops, key=lambda r: r.op_id)
        for i in range(len(ops_sorted) - 1):
            prev_op = ops_sorted[i]
            next_op = ops_sorted[i + 1]
            if prev_op.op_id + 1 != next_op.op_id:
                violations.append(Violation(
                    "OP_SEQUENCE_GAP",
                    f"Job {j_id}: Op {prev_op.op_id} -> Op {next_op.op_id} has gap in sequence",
                ))
            if prev_op.end > next_op.start:
                violations.append(Violation(
                    "PRECEDENCE_VIOLATION",
                    f"Job {j_id}: Op {prev_op.op_id} ends at {prev_op.end} "
                    f"but Op {next_op.op_id} starts at {next_op.start}",
                ))

    # 约束3：同一机器上的工序无时间重叠
    machine_ops: dict[int, list[ScheduleRecord]] = {}
    for rec in result.records:
        machine_ops.setdefault(rec.machine_id, []).append(rec)

    for m_id, ops in machine_ops.items():
        ops_sorted = sorted(ops, key=lambda r: r.start)
        for i in range(len(ops_sorted) - 1):
            prev_op = ops_sorted[i]
            next_op = ops_sorted[i + 1]
            if prev_op.end > next_op.start:
                violations.append(Violation(
                    "MACHINE_OVERLAP",
                    f"Machine {m_id}: Op (J{prev_op.job_id} O{prev_op.op_id}) "
                    f"ends at {prev_op.end} overlaps with "
                    f"Op (J{next_op.job_id} O{next_op.op_id}) starts at {next_op.start}",
                ))

    # 约束4：makespan 等于所有工序 end 的最大值
    computed_makespan = max(r.end for r in result.records) if result.records else 0
    if result.makespan != computed_makespan:
        violations.append(Violation(
            "MAKESPAN_MISMATCH",
            f"Result makespan={result.makespan} != computed={computed_makespan}",
        ))

    return len(violations) == 0, violations
