"""G1 acceptance is production legality AND mandatory maintenance AND exact T."""

from dataclasses import dataclass

from src.graduation._production import production_issues
from src.graduation.data import ParallelMaintenanceInstance
from src.graduation.metrics import calculate_total_tardiness
from src.graduation.result import MaintenanceRecord, MaintenanceScheduleResult


@dataclass(frozen=True)
class MaintenanceViolation:
    code: str
    message: str


def check_parallel_maintenance_feasibility(
    result: MaintenanceScheduleResult, data: ParallelMaintenanceInstance, *, mode: str
) -> tuple[bool, list[MaintenanceViolation]]:
    """Check without repairing records or filling reported metrics.

    Intervals are half-open: touching boundaries are legal. Maintenance on
    different machines may run concurrently because G1 has no shared crew.
    Invalid mode/fixed-start configuration raises ValueError; invalid schedule
    data returns diagnostics and can never be accepted.
    """
    if mode not in ('fixed', 'joint'):
        raise ValueError('mode must be fixed or joint')
    if not isinstance(data, ParallelMaintenanceInstance):
        raise ValueError('Expected a ParallelMaintenanceInstance')
    if mode == 'fixed' and any(item.fixed_start is None for item in data.maintenance):
        raise ValueError('fixed mode requires fixed_start for every machine')
    if not isinstance(result, MaintenanceScheduleResult):
        return False, [MaintenanceViolation('INVALID_RESULT', 'Expected a MaintenanceScheduleResult')]

    production_errors = production_issues(data, result)
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
            reject('MAINTENANCE_DURATION_MISMATCH', f'Machine {machine} maintenance duration must equal its requirement and end-start')
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
