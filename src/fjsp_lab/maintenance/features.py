"""Per-action features shared by the learned policies.

Each legal action gets one feature row, so one network scores every action
regardless of task indices or instance size. Times are divided by the base
load S = ceil(sum p / m) and processing times by their mean. EDD, MDD and
ATC keys are expressible from these rows. Maintenance features refer to the
machine's next pending window. Rows are computed with NumPy over all
candidates at once (an n=100, m=8 state has up to 800 job actions).
"""

from __future__ import annotations

import math
import statistics

import numpy as np

from fjsp_lab.maintenance.env import ParallelMaintenanceEnv

FEATURE_NAMES = (
    'is_task', 'p_over_mean', 'slack_to_start', 'immediate_tardiness', 'mdd_key',
    'atc_index', 'machine_delay', 'maintenance_pending', 'room_before_maintenance',
    'is_maintenance', 'joint_mode', 'tasks_remaining', 'work_per_machine',
    'due_rank', 'processing_rank', 'maintenance_idle', 'maintenance_slack',
    'maintenance_delay', 'maintenance_before_next_task',
)
FEATURE_COUNT = len(FEATURE_NAMES)
CLIP = 5.0


def action_candidates(env: ParallelMaintenanceEnv) -> tuple[list[int], np.ndarray]:
    """Return the legal actions and their float64 feature rows (same order)."""
    data, mode = env.data, env.mode
    legal = env.legal_actions()
    if not legal:
        raise ValueError('No legal action to featurize')
    m = data.num_machines
    tails = np.array(env.machine_tails, dtype=np.int64)
    p_all = np.array([task.processing_time for task in data.tasks], dtype=np.int64)
    d_all = np.array([task.due_date for task in data.tasks], dtype=np.int64)
    scale = (int(p_all.sum()) + m - 1) // m
    pbar = statistics.fmean(task.processing_time for task in data.tasks)
    remaining = ~np.array(env.scheduled)
    dues, times = np.sort(d_all[remaining]), np.sort(p_all[remaining])
    rank_span = max(1, int(remaining.sum()) - 1)
    pending = ~np.array(env.maintained)
    limit = np.array([env.job_limit(i) if pending[i] else 0 for i in range(m)], dtype=np.int64)
    min_tail = int(tails.min())

    actions = np.array(legal, dtype=np.int64)
    is_job = actions < env.maintenance_offset
    jobs, job_machines = actions[is_job] // m, actions[is_job] % m
    maintenance_machines = actions[~is_job] - env.maintenance_offset
    next_task_start = int(tails[job_machines].min()) if len(job_machines) else min_tail

    rows = np.zeros((len(legal), FEATURE_COUNT))
    rows[:, 10] = 1.0 if mode == 'joint' else 0.0
    rows[:, 11] = remaining.sum() / len(data.tasks)
    rows[:, 12] = p_all[remaining].sum() / m / scale

    t, p, d = tails[job_machines], p_all[jobs], d_all[jobs]
    x = rows[is_job]
    x[:, 0] = 1.0
    x[:, 1] = p / pbar
    x[:, 2] = (d - t) / scale
    x[:, 3] = np.maximum(0, t + p - d) / scale
    x[:, 4] = (np.maximum(d, t + p) - t) / scale
    x[:, 5] = np.fromiter((math.exp(v) for v in (-np.maximum(0, d - p - t) / pbar)), float, len(jobs)) * pbar / p
    x[:, 6] = (t - min_tail) / scale
    machine_pending = pending[job_machines]
    x[:, 7] = machine_pending.astype(float)
    x[:, 8] = np.where(machine_pending, (limit[job_machines] - t - p) / scale, 0.0)
    x[:, 13] = np.searchsorted(dues, d, side='left') / rank_span
    x[:, 14] = np.searchsorted(times, p, side='left') / rank_span
    rows[is_job] = x

    if len(maintenance_machines):
        y = rows[~is_job]
        t = tails[maintenance_machines]
        start = np.array([env.maintenance_start(int(i)) for i in maintenance_machines], dtype=np.int64)
        y[:, 9] = 1.0
        y[:, 15] = (start - t) / scale
        y[:, 16] = (limit[maintenance_machines] - t) / scale
        y[:, 17] = (start - min_tail) / scale
        y[:, 18] = (start < next_task_start).astype(float)
        rows[~is_job] = y
    np.clip(rows, -CLIP, CLIP, out=rows)
    return legal, rows
