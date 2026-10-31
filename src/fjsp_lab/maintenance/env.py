"""Finite schedule-construction environment (MDP) for rules and learned policies.

State: per-machine tail clock, which jobs are scheduled, which machines are
maintained. Actions (fixed layout of 100 for n <= 24, m <= 4):

* ``job * 4 + machine`` appends a job at that machine's tail. On a machine
  not yet maintained it is legal only if the job still ends by the latest
  maintenance start (fixed: f_i; joint: U_i - q_i);
* ``96 + machine`` appends that machine's maintenance (fixed: at f_i;
  joint: at max(tail, L_i)), legal while it still fits its window.

Each step's reward is -(tardiness of the job just placed) / 100, so the
return is -T/100. An episode has exactly n + m steps; the terminal plan is
built once, checked by the feasibility checker and only then returned.
"""

from __future__ import annotations

from dataclasses import dataclass

from fjsp_lab.maintenance.cpsat import numeric_domain_ok
from fjsp_lab.maintenance.feasibility import build_plan, require_feasible, validate_problem
from fjsp_lab.maintenance.instance import ParallelMaintenanceInstance
from fjsp_lab.maintenance.schedule import MaintenanceScheduleResult

MAX_TASKS = 24
MAX_MACHINES = 4
MAINTENANCE_OFFSET = MAX_TASKS * MAX_MACHINES
ACTION_COUNT = MAINTENANCE_OFFSET + MAX_MACHINES
REWARD_SCALE = 100


class EpisodeInvariantError(RuntimeError):
    """Construction broke an invariant; no accepted plan is available."""


@dataclass(frozen=True)
class Step:
    reward: float
    terminated: bool
    result: MaintenanceScheduleResult | None


class ParallelMaintenanceEnv:
    def __init__(self, data: ParallelMaintenanceInstance, *, mode: str):
        validate_problem(data, mode)
        if len(data.tasks) > MAX_TASKS or data.num_machines > MAX_MACHINES:
            raise ValueError(f'The environment supports at most {MAX_TASKS} tasks and {MAX_MACHINES} machines')
        if not numeric_domain_ok(data):
            raise ValueError('Instance exceeds the supported numeric domain')
        self.data, self.mode = data, mode
        # Latest end of a job that runs before maintenance on each machine.
        self._limit = [item.fixed_start if mode == 'fixed' else item.window_end - item.duration
                       for item in data.maintenance]
        self.reset()

    def reset(self) -> None:
        m = self.data.num_machines
        self._status, self._steps, self._tardiness = 'ACTIVE', 0, 0
        self._scheduled = [False] * len(self.data.tasks)
        self._maintained = [False] * m
        self._tails = [0] * m
        self._jobs: list[tuple[int, int, int]] = []
        self._maintenance: list[tuple[int, int]] = []
        self._result: MaintenanceScheduleResult | None = None
        self._legal: list[int] | None = None

    @property
    def machine_tails(self) -> tuple[int, ...]:
        return tuple(self._tails)

    @property
    def scheduled(self) -> tuple[bool, ...]:
        return tuple(self._scheduled)

    @property
    def maintained(self) -> tuple[bool, ...]:
        return tuple(self._maintained)

    @property
    def done(self) -> bool:
        return self._status != 'ACTIVE'

    def maintenance_start(self, machine: int) -> int:
        item = self.data.maintenance[machine]
        return item.fixed_start if self.mode == 'fixed' else max(self._tails[machine], item.window_start)

    def legal_actions(self) -> list[int]:
        """Legal actions in increasing order (cached until the next step)."""
        if self._status != 'ACTIVE':
            return []
        if self._legal is None:
            legal = []
            for task in self.data.tasks:
                if self._scheduled[task.job_id]:
                    continue
                for machine in range(self.data.num_machines):
                    if self._maintained[machine] or self._tails[machine] + task.processing_time <= self._limit[machine]:
                        legal.append(task.job_id * MAX_MACHINES + machine)
            for machine, item in enumerate(self.data.maintenance):
                if not self._maintained[machine]:
                    start = self.maintenance_start(machine)
                    if self._tails[machine] <= start and start + item.duration <= item.window_end:
                        legal.append(MAINTENANCE_OFFSET + machine)
            if not legal:
                self._status = 'FAILED'
                raise EpisodeInvariantError('Active nonterminal state has no legal action')
            self._legal = legal
        return list(self._legal)

    def action_masks(self) -> tuple[bool, ...]:
        mask = [False] * ACTION_COUNT
        for action in self.legal_actions():
            mask[action] = True
        return tuple(mask)

    def step(self, action: int) -> Step:
        if self._status != 'ACTIVE':
            raise RuntimeError('Episode ended; reset before another action')
        if type(action) is not int or action not in self.legal_actions():
            raise ValueError('Action is noninteger, out of range or masked')
        tardiness = 0
        if action < MAINTENANCE_OFFSET:
            job, machine = divmod(action, MAX_MACHINES)
            task = self.data.tasks[job]
            start = self._tails[machine]
            self._jobs.append((job, machine, start))
            self._tails[machine] = start + task.processing_time
            self._scheduled[job] = True
            tardiness = max(0, self._tails[machine] - task.due_date)
            self._tardiness += tardiness
        else:
            machine = action - MAINTENANCE_OFFSET
            start = self.maintenance_start(machine)
            self._maintenance.append((machine, start))
            self._tails[machine] = start + self.data.maintenance[machine].duration
            self._maintained[machine] = True
        self._steps += 1
        self._legal = None
        if self._steps == len(self.data.tasks) + self.data.num_machines:
            self._finish()
        return Step(-tardiness / REWARD_SCALE, self._status == 'TERMINATED', self._result)

    def _finish(self) -> None:
        try:
            if not all(self._scheduled) or not all(self._maintained):
                raise EpisodeInvariantError('Terminal object coverage mismatch')
            result = build_plan(self.data, self._jobs, self._maintenance)
            if result.total_tardiness != self._tardiness:
                raise EpisodeInvariantError('Reward accumulator differs from independent tardiness')
            self._result = require_feasible(result, self.data, mode=self.mode, source='Environment')
            self._status = 'TERMINATED'
        except Exception as exc:
            self._status, self._result = 'FAILED', None
            raise EpisodeInvariantError(f'Terminal construction rejected: {exc}') from exc


def actions_for_plan(result: MaintenanceScheduleResult, data: ParallelMaintenanceInstance, mode: str) -> list[int]:
    """Environment actions that rebuild a finished plan (e.g. a metaheuristic teacher).

    Jobs and maintenance are listed by start time (maintenance first on ties)
    and replayed; the replay must rebuild the same tardiness and placements.
    """
    events = [(r.start, 1, r.job_id * MAX_MACHINES + r.machine_id) for r in result.records]
    events += [(r.start, 0, MAINTENANCE_OFFSET + r.machine_id) for r in result.maintenance_records]
    actions = [action for _, _, action in sorted(events)]
    env = ParallelMaintenanceEnv(data, mode=mode)
    step = None
    for action in actions:
        if action not in env.legal_actions():
            raise ValueError(f'Plan action {action} is not legal during replay')
        step = env.step(action)
    if step is None or not step.terminated:
        raise ValueError('Plan actions do not finish the episode')
    rebuilt = step.result
    if (rebuilt.total_tardiness != result.total_tardiness
            or sorted((r.job_id, r.machine_id, r.start) for r in rebuilt.records)
            != sorted((r.job_id, r.machine_id, r.start) for r in result.records)):
        raise ValueError('Replayed plan differs from the source plan')
    return actions
