"""Feasibility checker of the maintenance model (the "G1 checker").

A plan is accepted only if all of the following hold:

1. its production part passes the unchanged static FJSP checker against the
   production-only instance ``to_fjsp_instance(data)`` (every job once, on a
   machine, non-overlapping, correct durations, correct makespan);
2. every machine has exactly one maintenance record with the required
   duration, completely inside its window, at ``fixed_start`` in fixed mode,
   and not overlapping any job on that machine (intervals are half-open);
3. the reported ``total_tardiness`` equals an independent recomputation.

Nothing is repaired or filled in; invalid plans yield violations.
"""

from __future__ import annotations

from dataclasses import dataclass

from fjsp_lab.fjsp.feasibility import check_feasibility
from fjsp_lab.fjsp.instance import FJSPInstance
from fjsp_lab.fjsp.schedule import ScheduleRecord, ScheduleResult
from fjsp_lab.maintenance.instance import ParallelMaintenanceInstance, to_fjsp_instance
from fjsp_lab.maintenance.schedule import MaintenanceRecord, MaintenanceScheduleResult

MODES = ('fixed', 'joint')


@dataclass(frozen=True)
class MaintenanceViolation:
    code: str
    message: str


class InfeasiblePlanError(RuntimeError):
    """An algorithm produced a plan that the checker rejected."""


def _production_issues(data: ParallelMaintenanceInstance, result: ScheduleResult) -> list[tuple[str, str]]:
    if not isinstance(data, ParallelMaintenanceInstance):
        return [('INVALID_INSTANCE_DATA', 'Expected typed maintenance instance data')]
    if not isinstance(result, ScheduleResult):
        return [('BASE_SCHEDULE_INVALID', 'Expected a ScheduleResult')]
    try:
        if not isinstance(result.instance, FJSPInstance) or result.instance != to_fjsp_instance(data):
            return [('INSTANCE_MISMATCH', 'Production instance does not match the target data')]
        if type(result.makespan) is not int or result.makespan < 0:
            return [('BASE_SCHEDULE_INVALID', 'Production makespan must be a nonnegative integer')]
        if not isinstance(result.records, (tuple, list)):
            return [('BASE_SCHEDULE_INVALID', 'Production records must be a sequence')]
        fields = ('job_id', 'op_id', 'machine_id', 'start', 'end', 'processing_time')
        for index, record in enumerate(result.records):
            if not isinstance(record, ScheduleRecord) or any(type(getattr(record, name, None)) is not int
                                                             for name in fields):
                return [('BASE_SCHEDULE_INVALID', f'Production record {index} has malformed or noninteger fields')]
        passed, issues = check_feasibility(result)
        if not passed:
            codes = ', '.join(issue.code for issue in issues[:20])
            return [('BASE_SCHEDULE_INVALID', f'Static checker rejected production: {codes}')]
    except Exception as exc:  # malformed objects must be rejected, never accepted
        return [('BASE_SCHEDULE_INVALID', f'Production validation failed: {type(exc).__name__}: {str(exc)[:300]}')]
    return []


def calculate_total_tardiness(data: ParallelMaintenanceInstance, result: ScheduleResult) -> int:
    """Sum of max(0, C_j - d_j) over a production-valid plan; raises otherwise."""
    issues = _production_issues(data, result)
    if issues:
        raise ValueError('; '.join(f'{code}: {message}' for code, message in issues))
    completion = {record.job_id: record.end for record in result.records}
    return sum(max(0, completion[task.job_id] - task.due_date) for task in data.tasks)


def check_parallel_maintenance_feasibility(
    result: MaintenanceScheduleResult, data: ParallelMaintenanceInstance, *, mode: str
) -> tuple[bool, list[MaintenanceViolation]]:
    """Return (accepted, violations). Invalid mode or fixed-start data raises ValueError."""
    if mode not in MODES:
        raise ValueError('mode must be fixed or joint')
    if not isinstance(data, ParallelMaintenanceInstance):
        raise ValueError('Expected a ParallelMaintenanceInstance')
    if mode == 'fixed' and any(item.fixed_start is None for item in data.maintenance):
        raise ValueError('fixed mode requires fixed_start for every machine')
    if not isinstance(result, MaintenanceScheduleResult):
        return False, [MaintenanceViolation('INVALID_RESULT', 'Expected a MaintenanceScheduleResult')]

    production_errors = _production_issues(data, result)
    issues = [MaintenanceViolation(code, message) for code, message in production_errors]

    def reject(code, message):
        issues.append(MaintenanceViolation(code, message))

    records = result.maintenance_records
    if not isinstance(records, (list, tuple)):
        reject('INVALID_MAINTENANCE_TIME', 'Maintenance records must be a sequence of MaintenanceRecord')
        records = ()
    counts = [0] * data.num_machines
    for index, record in enumerate(records):
        if not isinstance(record, MaintenanceRecord):
            reject('INVALID_MAINTENANCE_TIME', f'Maintenance record {index} has the wrong shape')
            continue
        machine = record.machine_id
        if type(machine) is not int or not 0 <= machine < data.num_machines:
            reject('INVALID_MAINTENANCE_MACHINE', f'Maintenance record {index} has an invalid machine ID')
            continue
        counts[machine] += 1
        times = (record.start, record.end, record.duration)
        if (any(type(value) is not int for value in times) or record.start < 0
                or record.duration <= 0 or record.end <= record.start):
            reject('INVALID_MAINTENANCE_TIME', f'Machine {machine} needs integer start >= 0, end > start and duration > 0')
            continue
        requirement = data.maintenance[machine]
        if record.duration != requirement.duration or record.end - record.start != requirement.duration:
            reject('MAINTENANCE_DURATION_MISMATCH',
                   f'Machine {machine} maintenance duration must equal its requirement and end-start')
        if record.start < requirement.window_start or record.end > requirement.window_end:
            reject('MAINTENANCE_OUTSIDE_WINDOW', f'Machine {machine} complete maintenance interval must fit its window')
        if mode == 'fixed' and record.start != requirement.fixed_start:
            reject('FIXED_START_MISMATCH', f'Machine {machine} maintenance must start at fixed_start')
        if not production_errors:
            for operation in result.records:
                if (operation.machine_id == machine and operation.start < record.end
                        and record.start < operation.end):
                    reject('MAINTENANCE_PRODUCTION_OVERLAP', f'Machine {machine} maintenance overlaps job {operation.job_id}')
    for machine, count in enumerate(counts):
        if count == 0:
            reject('MISSING_MAINTENANCE', f'Machine {machine} needs one mandatory maintenance, including idle machines')
        elif count > 1:
            reject('DUPLICATE_MAINTENANCE', f'Machine {machine} has {count} maintenance records; exactly one is required')
    reported = result.total_tardiness
    if type(reported) is not int or reported < 0:
        reject('TOTAL_TARDINESS_MISMATCH', 'Reported total_tardiness must be a nonnegative integer')
    elif not production_errors and reported != calculate_total_tardiness(data, result):
        reject('TOTAL_TARDINESS_MISMATCH', 'Reported total_tardiness differs from independent recomputation')
    return not issues, issues


def require_feasible(result: MaintenanceScheduleResult, data: ParallelMaintenanceInstance, *, mode: str,
                     source: str) -> MaintenanceScheduleResult:
    """Return ``result`` if the checker accepts it, otherwise raise InfeasiblePlanError."""
    accepted, issues = check_parallel_maintenance_feasibility(result, data, mode=mode)
    if not accepted:
        raise InfeasiblePlanError(f'{source} produced a plan the checker rejected: {issues}')
    return result


def validate_problem(data: ParallelMaintenanceInstance, mode: str) -> None:
    """Shared argument check for every algorithm entry point."""
    if not isinstance(data, ParallelMaintenanceInstance) or mode not in MODES:
        raise ValueError('Expected typed maintenance data and mode fixed or joint')
    if mode == 'fixed' and any(item.fixed_start is None for item in data.maintenance):
        raise ValueError('fixed mode requires fixed_start for every machine')


def build_plan(data: ParallelMaintenanceInstance, jobs, maintenance_starts) -> MaintenanceScheduleResult:
    """Assemble a plan from (job, machine, start) and (machine, start) placements.

    Fills makespan and total tardiness; the caller still has to run the checker.
    """
    result = MaintenanceScheduleResult(instance=to_fjsp_instance(data))
    for job, machine, start in jobs:
        result.add_record(job, 0, machine, start, data.tasks[job].processing_time)
    result.maintenance_records = [
        MaintenanceRecord(machine, start, start + data.maintenance[machine].duration,
                          data.maintenance[machine].duration)
        for machine, start in sorted(maintenance_starts)]
    result.compute_makespan()
    result.total_tardiness = calculate_total_tardiness(data, result)
    return result
