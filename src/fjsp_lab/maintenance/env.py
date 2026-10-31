"""Finite schedule-construction environment (MDP) for rules and learned policies.

State: per-machine tail clock, which jobs are scheduled and, per machine, the
next maintenance window still to be done. Actions for an instance with n jobs
and m machines (no size cap):

* ``job * m + machine`` appends a job at that machine's tail. While the
  machine still has a pending window it is legal only if the job ends by
  that window's latest maintenance start (fixed: f_ik; joint: U_ik - q_ik);
* ``n * m + machine`` appends the machine's next pending maintenance
  (fixed: at f_ik; joint: at max(tail, L_ik)).

Jobs never run into a pending window, so a pending maintenance is always
legal and no state is a dead end. Starting maintenance as early as possible
loses nothing for total tardiness (a regular objective). Each step's reward
is -(tardiness of the job just placed) / 100, so the return is -T/100. An
episode has n + (number of windows) steps; the terminal plan is built once,
checked by the feasibility checker and only then returned.
"""

from __future__ import annotations

from dataclasses import dataclass

from fjsp_lab.maintenance.cpsat import numeric_domain_ok
from fjsp_lab.maintenance.feasibility import build_plan, require_feasible, validate_problem
from fjsp_lab.maintenance.instance import ParallelMaintenanceInstance
from fjsp_lab.maintenance.schedule import MaintenanceScheduleResult

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
        if not numeric_domain_ok(data):
            raise ValueError('Instance exceeds the supported numeric domain')
        self.data, self.mode = data, mode
        self.num_jobs, self.num_machines = len(data.tasks), data.num_machines
        self.maintenance_offset = self.num_jobs * self.num_machines
        self.total_steps = self.num_jobs + data.num_windows
        self.reset()

    def reset(self) -> None:
        m = self.num_machines
        self._status, self._steps, self._tardiness = 'ACTIVE', 0, 0
        self._scheduled = [False] * self.num_jobs
        self._next_window = [0] * m
        self._tails = [0] * m
        self._jobs: list[tuple[int, int, int]] = []
        self._maintenance: list[tuple[int, int, int]] = []
        self._result: MaintenanceScheduleResult | None = None
        self._legal: list[int] | None = None

    # --- state ------------------------------------------------------------------
    @property
    def machine_tails(self) -> tuple[int, ...]:
        return tuple(self._tails)

    @property
    def scheduled(self) -> tuple[bool, ...]:
        return tuple(self._scheduled)

    @property
    def maintained(self) -> tuple[bool, ...]:
        """True for machines with no maintenance window left to do."""
        return tuple(k == len(w) for k, w in zip(self._next_window, self.data.windows))

    @property
    def done(self) -> bool:
        return self._status != 'ACTIVE'

    def pending_window(self, machine: int):
        """The machine's next maintenance window still to be done, or None."""
        windows = self.data.windows[machine]
        k = self._next_window[machine]
        return windows[k] if k < len(windows) else None

    def remaining_windows(self, machine: int) -> int:
        return len(self.data.windows[machine]) - self._next_window[machine]

    def job_limit(self, machine: int) -> float:
        """Latest end of a job appended now on ``machine`` (inf when no window is pending)."""
        item = self.pending_window(machine)
        if item is None:
            return float('inf')
        return item.fixed_start if self.mode == 'fixed' else item.window_end - item.duration

    def maintenance_start(self, machine: int) -> int:
        item = self.pending_window(machine)
        return item.fixed_start if self.mode == 'fixed' else max(self._tails[machine], item.window_start)

    # --- actions ----------------------------------------------------------------
    def is_maintenance(self, action: int) -> bool:
        return action >= self.maintenance_offset

    def machine_of(self, action: int) -> int:
        return action - self.maintenance_offset if action >= self.maintenance_offset else action % self.num_machines

    def job_of(self, action: int) -> int:
        return action // self.num_machines

    def legal_actions(self) -> list[int]:
        """Legal actions in increasing order (cached until the next step)."""
        if self._status != 'ACTIVE':
            return []
        if self._legal is None:
            m = self.num_machines
            limits = [self.job_limit(machine) for machine in range(m)]
            legal = []
            for task in self.data.tasks:
                if self._scheduled[task.job_id]:
                    continue
                for machine in range(m):
                    if self._tails[machine] + task.processing_time <= limits[machine]:
                        legal.append(task.job_id * m + machine)
            for machine in range(m):
                item = self.pending_window(machine)
                if item is not None:
                    start = self.maintenance_start(machine)
                    if self._tails[machine] <= start and start + item.duration <= item.window_end:
                        legal.append(self.maintenance_offset + machine)
            if not legal:
                self._status = 'FAILED'
                raise EpisodeInvariantError('Active nonterminal state has no legal action')
            self._legal = legal
        return list(self._legal)

    def step(self, action: int) -> Step:
        if self._status != 'ACTIVE':
            raise RuntimeError('Episode ended; reset before another action')
        if type(action) is not int or action not in self.legal_actions():
            raise ValueError('Action is noninteger, out of range or masked')
        tardiness = 0
        machine = self.machine_of(action)
        if not self.is_maintenance(action):
            job = self.job_of(action)
            task = self.data.tasks[job]
            start = self._tails[machine]
            self._jobs.append((job, machine, start))
            self._tails[machine] = start + task.processing_time
            self._scheduled[job] = True
            tardiness = max(0, self._tails[machine] - task.due_date)
            self._tardiness += tardiness
        else:
            k = self._next_window[machine]
            start = self.maintenance_start(machine)
            self._maintenance.append((machine, k, start))
            self._tails[machine] = start + self.data.windows[machine][k].duration
            self._next_window[machine] = k + 1
        self._steps += 1
        self._legal = None
        if self._steps == self.total_steps:
            self._finish()
        return Step(-tardiness / REWARD_SCALE, self._status == 'TERMINATED', self._result)

    def _finish(self) -> None:
        try:
            if not all(self._scheduled) or not all(self.maintained):
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
    n, m = len(data.tasks), data.num_machines
    events = [(r.start, 1, r.job_id * m + r.machine_id) for r in result.records]
    events += [(r.start, 0, n * m + r.machine_id) for r in result.maintenance_records]
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
