"""Per-action features shared by the learned policies.

Each legal action gets one feature row, so one small network scores every
action regardless of task indices or instance size. Times are divided by
the base load S = ceil(sum p / m) and processing times by their mean.
EDD, MDD and ATC keys are expressible from these rows.
"""

from __future__ import annotations

import math
import statistics

import numpy as np

from fjsp_lab.maintenance.env import MAINTENANCE_OFFSET, MAX_MACHINES, ParallelMaintenanceEnv

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
    data, mode, tails = env.data, env.mode, env.machine_tails
    legal = env.legal_actions()
    if not legal:
        raise ValueError('No legal action to featurize')
    m = data.num_machines
    scale = (sum(task.processing_time for task in data.tasks) + m - 1) // m
    pbar = statistics.fmean(task.processing_time for task in data.tasks)
    scheduled, maintained = env.scheduled, env.maintained
    remaining = [task for task in data.tasks if not scheduled[task.job_id]]
    dues = sorted(task.due_date for task in remaining)
    times = sorted(task.processing_time for task in remaining)
    rank_span = max(1, len(remaining) - 1)
    production_tails = [tails[a % MAX_MACHINES] for a in legal if a < MAINTENANCE_OFFSET]
    next_task_start = min(production_tails) if production_tails else min(tails)
    shared = (1.0 if mode == 'joint' else 0.0, len(remaining) / len(data.tasks),
              sum(task.processing_time for task in remaining) / m / scale)
    rows = np.zeros((len(legal), FEATURE_COUNT))
    for k, action in enumerate(legal):
        x = rows[k]
        x[10:13] = shared
        if action < MAINTENANCE_OFFSET:
            job, machine = divmod(action, MAX_MACHINES)
            task, t = data.tasks[job], tails[machine]
            p, d = task.processing_time, task.due_date
            item = data.maintenance[machine]
            boundary = item.fixed_start if mode == 'fixed' else item.window_end - item.duration
            x[0] = 1.0
            x[1] = p / pbar
            x[2] = (d - t) / scale
            x[3] = max(0, t + p - d) / scale
            x[4] = (max(d, t + p) - t) / scale
            x[5] = math.exp(-max(0, d - p - t) / pbar) * pbar / p
            x[6] = (t - min(tails)) / scale
            x[7] = 0.0 if maintained[machine] else 1.0
            x[8] = 0.0 if maintained[machine] else (boundary - t - p) / scale
            x[13] = dues.index(d) / rank_span
            x[14] = times.index(p) / rank_span
        else:
            machine = action - MAINTENANCE_OFFSET
            item, t = data.maintenance[machine], tails[machine]
            start = env.maintenance_start(machine)
            latest = item.fixed_start if mode == 'fixed' else item.window_end - item.duration
            x[9] = 1.0
            x[15] = (start - t) / scale
            x[16] = (latest - t) / scale
            x[17] = (start - min(tails)) / scale
            x[18] = 1.0 if start < next_task_start else 0.0
    np.clip(rows, -CLIP, CLIP, out=rows)
    return legal, rows
