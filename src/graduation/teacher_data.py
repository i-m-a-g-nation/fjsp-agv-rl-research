"""Teacher trajectories and portable instance records for policy training.

A finished plan (for example an IGA result) is turned into the R1
environment's action sequence by listing jobs and maintenance in start-time
order (maintenance first on ties). Replaying that sequence in a fresh
environment must rebuild the same plan and tardiness; otherwise the plan is
rejected as a teacher. Instances are stored as plain dicts so a separate
environment (for example one with PyTorch) can rebuild them without the
instance generator.
"""

from __future__ import annotations

from src.graduation.data import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask
from src.graduation.result import MaintenanceScheduleResult
from src.graduation.rl_environment import MAINTENANCE_OFFSET, MAX_MACHINES, ParallelMaintenanceEnv


class TeacherReplayError(ValueError):
    """A plan cannot be reproduced by the construction environment."""


def instance_to_record(data: ParallelMaintenanceInstance) -> dict:
    return {'tasks': [[t.job_id, t.processing_time, t.due_date] for t in data.tasks],
            'num_machines': data.num_machines,
            'maintenance': [[m.machine_id, m.duration, m.window_start, m.window_end, m.fixed_start]
                            for m in data.maintenance]}


def record_to_instance(record: dict) -> ParallelMaintenanceInstance:
    return ParallelMaintenanceInstance(
        tuple(ProductionTask(*row) for row in record['tasks']), record['num_machines'],
        tuple(MaintenanceRequirement(*row) for row in record['maintenance']))


def plan_to_actions(result: MaintenanceScheduleResult, data: ParallelMaintenanceInstance, mode: str) -> list[int]:
    """Environment actions that rebuild ``result``; verified by replay."""
    events = [(r.start, 1, r.job_id * MAX_MACHINES + r.machine_id) for r in result.records]
    events += [(r.start, 0, MAINTENANCE_OFFSET + r.machine_id) for r in result.maintenance_records]
    actions = [action for _, _, action in sorted(events)]
    env = ParallelMaintenanceEnv(data, mode=mode)
    step = None
    for action in actions:
        if not env.action_masks()[action]:
            raise TeacherReplayError(f'Teacher action {action} is not legal during replay')
        step = env.step(action)
    if step is None or not step.terminated:
        raise TeacherReplayError('Teacher actions do not finish the episode')
    rebuilt = step.result
    if rebuilt.total_tardiness != result.total_tardiness:
        raise TeacherReplayError('Replay tardiness differs from the teacher plan')
    if sorted((r.job_id, r.machine_id, r.start) for r in rebuilt.records) != \
            sorted((r.job_id, r.machine_id, r.start) for r in result.records):
        raise TeacherReplayError('Replay production records differ from the teacher plan')
    return actions
