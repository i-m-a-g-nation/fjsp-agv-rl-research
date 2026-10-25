"""Immutable G1 inputs: identical machines, release zero and mandatory maintenance."""

from __future__ import annotations

from dataclasses import dataclass

from src.data.instance import FJSPInstance


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}; booleans are not accepted')


@dataclass(frozen=True)
class ProductionTask:
    job_id: int
    processing_time: int
    due_date: int

    def __post_init__(self):
        _integer(self.job_id, 'job_id')
        _integer(self.processing_time, 'processing_time', 1)
        _integer(self.due_date, 'due_date')


@dataclass(frozen=True)
class MaintenanceRequirement:
    machine_id: int
    duration: int
    window_start: int
    window_end: int
    fixed_start: int | None = None

    def __post_init__(self):
        _integer(self.machine_id, 'machine_id')
        _integer(self.duration, 'duration', 1)
        _integer(self.window_start, 'window_start')
        _integer(self.window_end, 'window_end')
        if self.window_end - self.window_start < self.duration:
            raise ValueError('The complete mandatory maintenance must fit inside its window')
        if self.fixed_start is not None:
            _integer(self.fixed_start, 'fixed_start')
            if not self.window_start <= self.fixed_start <= self.window_end - self.duration:
                raise ValueError('fixed_start must fit the complete maintenance inside its window')


@dataclass(frozen=True)
class ParallelMaintenanceInstance:
    tasks: tuple[ProductionTask, ...]
    num_machines: int
    maintenance: tuple[MaintenanceRequirement, ...]

    def __post_init__(self):
        _integer(self.num_machines, 'num_machines', 1)
        try:
            tasks, maintenance = tuple(self.tasks), tuple(self.maintenance)
        except TypeError as exc:
            raise ValueError('tasks and maintenance must be sequences of typed inputs') from exc
        if not tasks or any(not isinstance(task, ProductionTask) for task in tasks):
            raise ValueError('At least one typed production task is required')
        if any(not isinstance(item, MaintenanceRequirement) for item in maintenance):
            raise ValueError('maintenance entries must be typed requirements')
        if sorted(task.job_id for task in tasks) != list(range(len(tasks))):
            raise ValueError('Task IDs must be unique and cover 0..n-1')
        if sorted(item.machine_id for item in maintenance) != list(range(self.num_machines)):
            raise ValueError('Every machine, including idle machines, needs exactly one maintenance requirement')
        object.__setattr__(self, 'tasks', tuple(sorted(tasks, key=lambda task: task.job_id)))
        object.__setattr__(self, 'maintenance', tuple(sorted(maintenance, key=lambda item: item.machine_id)))


def to_fjsp_instance(data: ParallelMaintenanceInstance) -> FJSPInstance:
    """Return a fresh production-only instance; maintenance is never a fake job."""
    if not isinstance(data, ParallelMaintenanceInstance):
        raise ValueError('Expected a ParallelMaintenanceInstance')
    jobs = [[[(machine, task.processing_time) for machine in range(data.num_machines)]] for task in data.tasks]
    return FJSPInstance.from_jobs_array(jobs, num_machines=data.num_machines)
