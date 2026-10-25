"""Finite no-training schedule-construction core, independent of Gym/PPO."""

from copy import deepcopy
from dataclasses import dataclass

from src.graduation.data import ParallelMaintenanceInstance, to_fjsp_instance
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.metrics import calculate_total_tardiness
from src.graduation.result import MaintenanceRecord, MaintenanceScheduleResult

MAX_TASKS = 24
MAX_MACHINES = 4
ACTION_COUNT = 100
MAINTENANCE_OFFSET = 96
REWARD_SCALE = 100


class EpisodeInvariantError(RuntimeError):
    """Construction failed an invariant; no accepted plan is available."""


@dataclass(frozen=True)
class ConstructionObservation:
    mode: str
    status: str
    steps: int
    scale: int
    task_features: tuple[tuple[float, ...], ...]
    machine_features: tuple[tuple[float, ...], ...]
    task_presence: tuple[bool, ...]
    machine_presence: tuple[bool, ...]
    action_mask: tuple[bool, ...]


@dataclass(frozen=True)
class ConstructionStep:
    observation: ConstructionObservation
    reward: float
    terminated: bool
    truncated: bool
    result: MaintenanceScheduleResult | None


class ParallelMaintenanceEnv:
    """Append tasks/mandatory maintenance using integer, earliest-start clocks.

    Only successful, G1-validated termination exposes a detached result. This
    core has no stochastic policy, trainer, Gym adapter or optimizer call.
    """

    def __init__(self, data: ParallelMaintenanceInstance, *, mode: str):
        if not isinstance(data, ParallelMaintenanceInstance) or mode not in ('fixed', 'joint'):
            raise ValueError('Expected typed G1 data and fixed/joint mode')
        n, m = len(data.tasks), data.num_machines
        if n > MAX_TASKS or m > MAX_MACHINES:
            raise ValueError('R1 supports at most 24 tasks and 4 machines; inputs are never cropped')
        if mode == 'fixed' and any(item.fixed_start is None for item in data.maintenance):
            raise ValueError('fixed mode requires every fixed_start')
        horizon = max(item.window_end for item in data.maintenance) + sum(task.processing_time for task in data.tasks)
        if max(horizon*(4*n*m + 4*m + 4*n + 1), max(task.due_date for task in data.tasks)) > 2**50:
            raise ValueError('Instance exceeds the G2/R1 numeric domain')
        self._data, self._mode = data, mode
        self._scale = (sum(task.processing_time for task in data.tasks) + m - 1) // m
        self.reset()

    @property
    def data(self):
        return self._data

    @property
    def mode(self):
        return self._mode

    def reset(self) -> ConstructionObservation:
        self._status, self._steps, self._tardiness = 'ACTIVE', 0, 0
        self._scheduled = [False] * len(self.data.tasks)
        self._maintained = [False] * self.data.num_machines
        self._tails = [0] * self.data.num_machines
        self._draft = MaintenanceScheduleResult(instance=to_fjsp_instance(self.data))
        self._accepted_result = None
        return self.observe()

    def action_masks(self) -> tuple[bool, ...]:
        mask = [False] * ACTION_COUNT
        if self._status != 'ACTIVE':
            return tuple(mask)
        for machine, requirement in enumerate(self.data.maintenance):
            tail = self._tails[machine]
            boundary = requirement.fixed_start if self.mode == 'fixed' else requirement.window_end - requirement.duration
            if not self._maintained[machine]:
                start = requirement.fixed_start if self.mode == 'fixed' else max(tail, requirement.window_start)
                mask[MAINTENANCE_OFFSET + machine] = tail <= start and start + requirement.duration <= requirement.window_end
            for task in self.data.tasks:
                if not self._scheduled[task.job_id] and (self._maintained[machine] or tail + task.processing_time <= boundary):
                    mask[task.job_id * MAX_MACHINES + machine] = True
        if not any(mask):
            self._status, self._accepted_result = 'FAILED', None
            raise EpisodeInvariantError('Active nonterminal state has no legal action')
        return tuple(mask)

    def observe(self) -> ConstructionObservation:
        tasks = [(task.processing_time/self._scale, task.due_date/self._scale, float(self._scheduled[task.job_id]))
                 for task in self.data.tasks]
        tasks += [(0.0, 0.0, 0.0)] * (MAX_TASKS-len(tasks))
        machines = []
        for machine, item in enumerate(self.data.maintenance):
            machines.append((self._tails[machine]/self._scale, item.duration/self._scale,
                item.window_start/self._scale, item.window_end/self._scale,
                item.fixed_start/self._scale if item.fixed_start is not None else -1.0,
                float(self._maintained[machine]), float(item.fixed_start is not None)))
        machines += [(0.0,)*7] * (MAX_MACHINES-len(machines))
        return ConstructionObservation(self.mode, self._status, self._steps, self._scale, tuple(tasks), tuple(machines),
            tuple(j < len(self.data.tasks) for j in range(MAX_TASKS)),
            tuple(i < self.data.num_machines for i in range(MAX_MACHINES)), self.action_masks())

    def step(self, action: int) -> ConstructionStep:
        if self._status != 'ACTIVE':
            raise RuntimeError('Episode ended; reset before another action')
        if type(action) is not int or not 0 <= action < ACTION_COUNT or not self.action_masks()[action]:
            raise ValueError('Action is noninteger, out of range, padded, duplicate or masked')
        tardiness = 0
        if action < MAINTENANCE_OFFSET:
            job, machine = divmod(action, MAX_MACHINES)
            task = self.data.tasks[job]
            record = self._draft.add_record(job, 0, machine, self._tails[machine], task.processing_time)
            self._tails[machine] = record.end
            self._scheduled[job] = True
            tardiness = max(0, record.end - task.due_date)
            self._tardiness += tardiness
        else:
            machine = action - MAINTENANCE_OFFSET
            item = self.data.maintenance[machine]
            start = item.fixed_start if self.mode == 'fixed' else max(self._tails[machine], item.window_start)
            end = start + item.duration
            self._draft.maintenance_records.append(MaintenanceRecord(machine, start, end, item.duration))
            self._tails[machine], self._maintained[machine] = end, True
        self._steps += 1
        if self._steps == len(self.data.tasks) + self.data.num_machines:
            try:
                if not all(self._scheduled) or not all(self._maintained):
                    raise EpisodeInvariantError('Terminal object coverage mismatch')
                self._draft.compute_makespan()
                self._draft.total_tardiness = calculate_total_tardiness(self.data, self._draft)
                if self._draft.total_tardiness != self._tardiness:
                    raise EpisodeInvariantError('Reward accumulator differs from independent tardiness')
                accepted, issues = check_parallel_maintenance_feasibility(self._draft, self.data, mode=self.mode)
                if not accepted:
                    raise EpisodeInvariantError(f'G1 rejected terminal plan: {issues}')
                self._accepted_result = deepcopy(self._draft)
                self._status = 'TERMINATED'
            except Exception as exc:
                self._status, self._accepted_result = 'FAILED', None
                raise EpisodeInvariantError(f'Terminal construction rejected: {exc}') from exc
        terminated = self._status == 'TERMINATED'
        return ConstructionStep(self.observe(), -tardiness/REWARD_SCALE, terminated, False,
                                self.get_result() if terminated else None)

    def truncate(self) -> ConstructionStep:
        if self._status != 'ACTIVE':
            raise RuntimeError('Only an active episode can be truncated')
        self._status, self._accepted_result = 'TRUNCATED', None
        return ConstructionStep(self.observe(), 0.0, False, True, None)

    def get_result(self) -> MaintenanceScheduleResult:
        if self._status != 'TERMINATED' or self._accepted_result is None:
            raise RuntimeError('No accepted terminal result; partial/failed/truncated plans cannot be returned')
        return deepcopy(self._accepted_result)
