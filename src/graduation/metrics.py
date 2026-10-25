"""Exact total tardiness; metric computation is not maintenance acceptance."""

from src.graduation._production import production_issues
from src.graduation.data import ParallelMaintenanceInstance
from src.scheduling.encoding import ScheduleResult


def calculate_total_tardiness(data: ParallelMaintenanceInstance, result: ScheduleResult) -> int:
    """Reject invalid production, then sum positive lateness without mutation.

    Maintenance legality is a separate conjunction checked by
    check_parallel_maintenance_feasibility; this function only computes the
    production metric against the supplied immutable task data.
    """
    issues = production_issues(data, result)
    if issues:
        raise ValueError('; '.join(f'{code}: {message}' for code, message in issues))
    completion = {record.job_id: record.end for record in result.records}
    return sum(max(0, completion[task.job_id] - task.due_date) for task in data.tasks)
