"""Immutable inputs of the graduation model.

n single-operation jobs on m identical machines, all released at time 0.
Machine i has K_i >= 1 preventive-maintenance windows [L_ik, U_ik)
(disjoint, ordered in time; K_i may differ between machines). Every window,
on idle machines too, needs exactly one maintenance of duration q_ik lying
completely inside it. In fixed mode each maintenance starts at its
``fixed_start``; in joint mode the scheduler chooses the start. The
objective is total tardiness. K_i = 1 for all machines is the original model.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from fjsp_lab.fjsp.instance import FJSPInstance


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
        if sorted({item.machine_id for item in maintenance}) != list(range(self.num_machines)):
            raise ValueError('Every machine, including idle machines, needs at least one maintenance window')
        maintenance = tuple(sorted(maintenance, key=lambda item: (item.machine_id, item.window_start)))
        windows = tuple(tuple(item for item in maintenance if item.machine_id == machine)
                        for machine in range(self.num_machines))
        for machine_windows in windows:
            for earlier, later in zip(machine_windows, machine_windows[1:]):
                if earlier.window_end > later.window_start:
                    raise ValueError(f'Maintenance windows of machine {earlier.machine_id} must not overlap')
        object.__setattr__(self, 'tasks', tuple(sorted(tasks, key=lambda task: task.job_id)))
        object.__setattr__(self, 'maintenance', maintenance)
        object.__setattr__(self, '_windows', windows)

    @property
    def num_tasks(self) -> int:
        return len(self.tasks)

    @property
    def windows(self) -> tuple[tuple[MaintenanceRequirement, ...], ...]:
        """windows[machine][k]: the k-th maintenance window of a machine, in time order."""
        return self._windows

    @property
    def num_windows(self) -> int:
        return len(self.maintenance)

    def to_record(self) -> dict:
        """Compact JSON-ready form (lists of field values)."""
        return {'tasks': [[t.job_id, t.processing_time, t.due_date] for t in self.tasks],
                'num_machines': self.num_machines,
                'maintenance': [[m.machine_id, m.duration, m.window_start, m.window_end, m.fixed_start]
                                for m in self.maintenance]}

    @classmethod
    def from_record(cls, record: dict) -> 'ParallelMaintenanceInstance':
        return cls(tuple(ProductionTask(*row) for row in record['tasks']), record['num_machines'],
                   tuple(MaintenanceRequirement(*row) for row in record['maintenance']))


def to_fjsp_instance(data: ParallelMaintenanceInstance) -> FJSPInstance:
    """The production-only instance (maintenance is never a fake job).

    FJSPInstance is immutable, so the instance is built once per (processing
    times, machine count) and shared.
    """
    if not isinstance(data, ParallelMaintenanceInstance):
        raise ValueError('Expected a ParallelMaintenanceInstance')
    return _production_instance(tuple(task.processing_time for task in data.tasks), data.num_machines)


@lru_cache(maxsize=4096)
def _production_instance(processing_times: tuple[int, ...], num_machines: int) -> FJSPInstance:
    jobs = [[[(machine, p) for machine in range(num_machines)]] for p in processing_times]
    return FJSPInstance.from_jobs_array(jobs, num_machines=num_machines)
