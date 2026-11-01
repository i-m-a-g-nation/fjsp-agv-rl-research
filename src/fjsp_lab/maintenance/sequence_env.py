"""Construction MDP over the metaheuristic token decoder (used by RL on large instances).

Role: the MDP of the thesis main method (attention policy, kind ``'sequence'``).
Unlike ``env.ParallelMaintenanceEnv`` the machine is chosen by the decoder's
earliest-completion rule, so whether this space always contains an optimum is
not proven; it has only been checked exhaustively on tiny instances.

An episode builds a token sequence for ``TokenDecoder`` one token at a time:

* a job token places the job on the machine where it completes earliest;
  pending maintenance that the job would run into is inserted first (the
  decoder's rule);
* a maintenance token is offered only for each machine's next pending window
  and schedules it now (fixed: at f_ik; joint: at max(tail, L_ik)).

When every job is placed the episode ends and the remaining windows are
maintained in order. Each step has at most n + m candidates, so the policy
scales to n=100, m=8. The final plan is rebuilt by the decoder from the full
sequence, must reproduce the accumulated tardiness and pass the checker.
Teacher trajectories are metaheuristic sequences (``teacher_actions``).
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import statistics

import numpy as np

from fjsp_lab.maintenance.instance import ParallelMaintenanceInstance
from fjsp_lab.maintenance.metaheuristics import TokenDecoder
from fjsp_lab.maintenance.schedule import MaintenanceScheduleResult

SEQUENCE_FEATURE_NAMES = (
    'is_job', 'p_over_mean', 'slack_after', 'tardiness_if_now', 'mdd_key', 'atc_index', 'start_delay',
    'forces_maintenance', 'lost_time', 'due_rank', 'processing_rank',
    'is_maintenance', 'joint_mode', 'jobs_remaining', 'work_per_machine',
    'maintenance_idle', 'maintenance_slack', 'windows_left', 'machine_load', 'jobs_fitting_before',
)
SEQUENCE_FEATURE_COUNT = len(SEQUENCE_FEATURE_NAMES)
SEQUENCE_COLUMN = {name: index for index, name in enumerate(SEQUENCE_FEATURE_NAMES)}   # name -> column
CLIP = 5.0


def _padded(rows: list[list[int]], width: int) -> np.ndarray:
    """Rows of unequal length (one per machine) as an int64 matrix, padded with zeros to ``width``."""
    return np.array([row + [0] * (width - len(row)) for row in rows], dtype=np.int64)


class SequenceEpisodeError(RuntimeError):
    """The incremental episode disagrees with the decoder; no plan is returned."""


@dataclass(frozen=True)
class SequenceStep:
    terminated: bool
    result: MaintenanceScheduleResult | None


class SequenceEnv:
    """Token-by-token construction over ``TokenDecoder``, vectorized with NumPy.

    Array names follow the model notation: ``p``/``d`` processing times and
    due dates per job; per machine i and window k, ``q[i, k]`` duration,
    ``lo[i, k]`` window start L_ik, ``limit[i, k]`` latest end of a job run
    before that maintenance, ``fixed[i, k]`` the fixed start f_ik. Window
    matrices are zero-padded; ``counts[i]`` = K_i says how many are real.
    """

    def __init__(self, data: ParallelMaintenanceInstance, *, mode: str):
        self.decoder = TokenDecoder(data, mode)
        self.data = data
        self.mode = mode
        decoder = self.decoder
        self.n = decoder.n
        self.m = decoder.m
        self.p = np.array(decoder.p, dtype=np.int64)
        self.d = np.array(decoder.d, dtype=np.int64)
        self.counts = np.array([len(windows) for windows in decoder.q], dtype=np.int64)
        width = int(self.counts.max())
        self.q = _padded(decoder.q, width)
        self.limit = _padded(decoder.limit, width)
        self.lo = _padded(decoder.lo, width)
        self.fixed = _padded([[f if f is not None else 0 for f in row] for row in decoder.fixed_start], width)
        # Token of window 0 of each machine; window k of machine i is first_token[i] + k.
        self.first_token = np.concatenate(([0], np.cumsum(self.counts)[:-1])) + self.n
        self.scale = (int(self.p.sum()) + self.m - 1) // self.m       # base load S = ceil(sum p / m)
        self.pbar = statistics.fmean(decoder.p)
        self.reset()

    def reset(self) -> None:
        self.tails = np.zeros(self.m, dtype=np.int64)
        self.nxt = np.zeros(self.m, dtype=np.int64)
        self.unscheduled = np.ones(self.n, dtype=bool)
        self.sequence: list[int] = []
        self.total = 0
        self.result: MaintenanceScheduleResult | None = None

    @property
    def done(self) -> bool:
        return self.result is not None

    # --- decoder semantics, vectorized over jobs --------------------------------
    def _maintenance_start(self, machine, k, tail):
        return self.fixed[machine, k] if self.mode == 'fixed' else np.maximum(tail, self.lo[machine, k])

    def _placements(self, jobs: np.ndarray):
        """Start, machine and number of forced maintenances for each job if placed now."""
        p = self.p[jobs][:, None]                                    # [J, 1]
        machines = np.arange(self.m)[None, :]
        start = np.broadcast_to(self.tails, (len(jobs), self.m)).copy()
        k = np.broadcast_to(self.nxt, (len(jobs), self.m)).copy()
        for _ in range(int(self.counts.max())):
            pending = k < self.counts[None, :]
            kk = np.minimum(k, self.counts[None, :] - 1)
            forced = pending & (start + p > self.limit[machines, kk])
            if not forced.any():
                break
            begin = self._maintenance_start(machines, kk, start)
            start = np.where(forced, begin + self.q[machines, kk], start)
            k = k + forced
        finish = start + p
        best = finish.argmin(axis=1)                                 # first minimum = decoder tie-break
        rows = np.arange(len(jobs))
        return start[rows, best], best, (k - self.nxt[None, :])[rows, best]

    def legal_actions(self) -> list[int]:
        if self.done:
            return []
        jobs = np.flatnonzero(self.unscheduled)
        machines = np.flatnonzero(self.nxt < self.counts)
        return jobs.tolist() + (self.first_token[machines] + self.nxt[machines]).tolist()

    def step(self, token: int) -> SequenceStep:
        if self.done:
            raise RuntimeError('Episode ended; reset before another action')
        if type(token) is not int or token not in self.legal_actions():
            raise ValueError('Token is noninteger or not legal')
        self.sequence.append(token)
        if token < self.n:
            start, machine, forced = self._placements(np.array([token]))
            machine = int(machine[0])
            for _ in range(int(forced[0])):
                self._maintain(machine)
            end = int(start[0]) + int(self.p[token])
            self.tails[machine] = end
            self.unscheduled[token] = False
            self.total += max(0, end - int(self.d[token]))
        else:
            machine = int(np.searchsorted(self.first_token, token, side='right') - 1)
            self._maintain(machine)
        if not self.unscheduled.any():
            self._finish()
        return SequenceStep(self.done, self.result)

    def _maintain(self, machine: int) -> None:
        k = int(self.nxt[machine])
        start = int(self._maintenance_start(machine, k, self.tails[machine]))
        self.tails[machine] = start + int(self.q[machine, k])
        self.nxt[machine] = k + 1

    def _finish(self) -> None:
        listed = set(self.sequence)
        full = self.sequence + [t for t in range(self.n, self.decoder.size) if t not in listed]
        result = self.decoder.result(full)                           # decodes again and runs the checker
        if result.total_tardiness != self.total:
            raise SequenceEpisodeError('Incremental tardiness differs from the decoder')
        self.result = result

    # --- features ---------------------------------------------------------------
    def candidates(self) -> tuple[list[int], np.ndarray]:
        """Legal tokens and their feature rows (same order)."""
        legal = self.legal_actions()
        jobs = np.flatnonzero(self.unscheduled)
        machines = np.flatnonzero(self.nxt < self.counts)
        rows = np.zeros((len(legal), SEQUENCE_FEATURE_COUNT))
        remaining_p = self.p[jobs]
        min_tail = int(self.tails.min())
        rows[:, SEQUENCE_COLUMN['joint_mode']] = 1.0 if self.mode == 'joint' else 0.0
        rows[:, SEQUENCE_COLUMN['jobs_remaining']] = len(jobs) / self.n
        rows[:, SEQUENCE_COLUMN['work_per_machine']] = remaining_p.sum() / self.m / self.scale
        if len(jobs):
            start, machine, forced = self._placements(jobs)
            p, d = remaining_p, self.d[jobs]
            finish = start + p
            x = rows[:len(jobs)]
            x[:, SEQUENCE_COLUMN['is_job']] = 1.0
            x[:, SEQUENCE_COLUMN['p_over_mean']] = p / self.pbar
            x[:, SEQUENCE_COLUMN['slack_after']] = (d - finish) / self.scale
            x[:, SEQUENCE_COLUMN['tardiness_if_now']] = np.maximum(0, finish - d) / self.scale
            x[:, SEQUENCE_COLUMN['mdd_key']] = (np.maximum(d, finish) - min_tail) / self.scale
            x[:, SEQUENCE_COLUMN['atc_index']] = np.fromiter((math.exp(v) for v in (-np.maximum(0, d - finish) / self.pbar)), float,
                                  len(jobs)) * self.pbar / p
            x[:, SEQUENCE_COLUMN['start_delay']] = (start - min_tail) / self.scale
            x[:, SEQUENCE_COLUMN['forces_maintenance']] = (forced > 0).astype(float)
            x[:, SEQUENCE_COLUMN['lost_time']] = (start - self.tails[machine]) / self.scale
            span = max(1, len(jobs) - 1)
            x[:, SEQUENCE_COLUMN['due_rank']] = np.searchsorted(np.sort(d), d, side='left') / span
            x[:, SEQUENCE_COLUMN['processing_rank']] = np.searchsorted(np.sort(p), p, side='left') / span
        if len(machines):
            k = self.nxt[machines]
            tails = self.tails[machines]
            begin = self._maintenance_start(machines, k, tails)
            y = rows[len(jobs):]
            y[:, SEQUENCE_COLUMN['is_maintenance']] = 1.0
            y[:, SEQUENCE_COLUMN['maintenance_idle']] = (begin - tails) / self.scale
            y[:, SEQUENCE_COLUMN['maintenance_slack']] = (self.limit[machines, k] - tails) / self.scale
            y[:, SEQUENCE_COLUMN['windows_left']] = (self.counts[machines] - k) / self.counts.max()
            y[:, SEQUENCE_COLUMN['machine_load']] = (tails - min_tail) / self.scale
            if len(jobs):
                fits = tails[:, None] + remaining_p[None, :] <= self.limit[machines, k][:, None]
                y[:, SEQUENCE_COLUMN['jobs_fitting_before']] = fits.mean(axis=1)
        np.clip(rows, -CLIP, CLIP, out=rows)
        return legal, rows


def teacher_actions(sequence: list[int], data: ParallelMaintenanceInstance, mode: str) -> list[int]:
    """Episode tokens that follow a decoder sequence (e.g. the IGA best); replay must match it."""
    env = SequenceEnv(data, mode=mode)
    actions = []
    for token in sequence:
        if env.done:
            break
        if token >= env.n:
            machine = int(np.searchsorted(env.first_token, token, side='right') - 1)
            window = token - int(env.first_token[machine])
            while not env.done and env.nxt[machine] <= window:
                next_token = int(env.first_token[machine] + env.nxt[machine])
                actions.append(next_token)
                env.step(next_token)
            continue
        actions.append(token)
        env.step(token)
    if not env.done:
        raise ValueError('Sequence does not place every job')
    if env.result.total_tardiness != env.decoder.decode(list(sequence)):
        raise ValueError('Replayed episode differs from the decoded sequence')
    return actions
