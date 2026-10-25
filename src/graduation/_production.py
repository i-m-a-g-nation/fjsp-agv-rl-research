"""Shared strict production boundary before the unchanged FJSP checker."""

from src.data.instance import FJSPInstance
from src.graduation.data import ParallelMaintenanceInstance, to_fjsp_instance
from src.scheduling.encoding import ScheduleRecord, ScheduleResult
from src.scheduling.feasibility import check_feasibility


def production_issues(data, result) -> list[tuple[str, str]]:
    if not isinstance(data, ParallelMaintenanceInstance):
        return [('INVALID_INSTANCE_DATA', 'Expected typed G1 instance data')]
    if not isinstance(result, ScheduleResult):
        return [('BASE_SCHEDULE_INVALID', 'Expected a ScheduleResult')]
    try:
        if not isinstance(result.instance, FJSPInstance) or result.instance != to_fjsp_instance(data):
            return [('INSTANCE_MISMATCH', 'Production instance does not match the target G1 data')]
        if type(result.makespan) is not int or result.makespan < 0:
            return [('BASE_SCHEDULE_INVALID', 'Production makespan must be a nonnegative integer')]
        if not isinstance(result.records, (tuple, list)):
            return [('BASE_SCHEDULE_INVALID', 'Production records must be a sequence')]
        fields = ('job_id', 'op_id', 'machine_id', 'start', 'end', 'processing_time')
        for index, record in enumerate(result.records):
            if not isinstance(record, ScheduleRecord) or any(type(getattr(record, name, None)) is not int for name in fields):
                return [('BASE_SCHEDULE_INVALID', f'Production record {index} has malformed or noninteger fields')]
        passed, issues = check_feasibility(result)
        if not passed:
            codes = ', '.join(issue.code for issue in issues[:20])
            return [('BASE_SCHEDULE_INVALID', f'Static checker rejected production: {codes}')]
    except Exception as exc:
        return [('BASE_SCHEDULE_INVALID', f'Production validation failed: {type(exc).__name__}: {str(exc)[:300]}')]
    return []
