"""Gantt charts of maintenance plans: jobs, maintenance blocks and their windows.

Each machine is one row. Light bands are the allowed maintenance windows,
hatched blocks the scheduled maintenance, and job bars are blue when the job
finishes by its due date and red when it is tardy. Plans are checked before
drawing; an infeasible plan is never plotted.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use('Agg')

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

from fjsp_lab.maintenance.feasibility import require_feasible
from fjsp_lab.maintenance.instance import ParallelMaintenanceInstance
from fjsp_lab.maintenance.schedule import MaintenanceScheduleResult

ON_TIME, TARDY, MAINTENANCE, WINDOW = '#4c72b0', '#c44e52', '#555555', '#e8e8e8'


def draw_plan(ax, result: MaintenanceScheduleResult, data: ParallelMaintenanceInstance, *, mode: str,
              title: str = '', horizon: float | None = None, labels: bool | None = None) -> None:
    """Draw one checker-accepted plan on a matplotlib axis."""
    require_feasible(result, data, mode=mode, source='Gantt input')
    horizon = horizon or max(result.makespan, max(m.end for m in result.maintenance_records))
    labels = len(data.tasks) <= 30 if labels is None else labels
    m = data.num_machines
    for machine, windows in enumerate(data.windows):
        y = m - 1 - machine
        for item in windows:
            ax.barh(y, item.window_end - item.window_start, left=item.window_start, height=0.9,
                    color=WINDOW, edgecolor='none', zorder=0)
    for record in result.maintenance_records:
        ax.barh(m - 1 - record.machine_id, record.duration, left=record.start, height=0.6, color='white',
                edgecolor=MAINTENANCE, hatch='///', linewidth=1.0, zorder=2)
    for record in result.records:
        task = data.tasks[record.job_id]
        color = TARDY if record.end > task.due_date else ON_TIME
        ax.barh(m - 1 - record.machine_id, record.processing_time, left=record.start, height=0.6, color=color,
                edgecolor='white', linewidth=0.6, zorder=3)
        if labels and record.processing_time >= horizon / 60:
            ax.text(record.start + record.processing_time / 2, m - 1 - record.machine_id, str(record.job_id),
                    ha='center', va='center', fontsize=7, color='white', zorder=4)
    ax.set_yticks(range(m))
    ax.set_yticklabels([f'M{machine}' for machine in reversed(range(m))])
    ax.set_xlim(0, horizon * 1.01)
    ax.set_title(f'{title}  (total tardiness {result.total_tardiness})', fontsize=10)
    ax.grid(axis='x', linestyle=':', alpha=0.5)


def plot_fixed_vs_joint(data: ParallelMaintenanceInstance, fixed: MaintenanceScheduleResult,
                        joint: MaintenanceScheduleResult, path: str | Path, *, title: str = '') -> None:
    """Two stacked Gantt charts on a common time axis, saved to ``path`` (PNG or PDF)."""
    horizon = max(plan.makespan for plan in (fixed, joint))
    horizon = max([horizon] + [m.window_end for m in data.maintenance if m.window_start < horizon])
    fig, axes = plt.subplots(2, 1, figsize=(12, 1.2 + 0.55 * data.num_machines * 2 + 1), sharex=True)
    draw_plan(axes[0], fixed, data, mode='fixed', title='Fixed maintenance', horizon=horizon)
    draw_plan(axes[1], joint, data, mode='joint', title='Joint optimisation', horizon=horizon)
    axes[1].set_xlabel('time')
    handles = [mpatches.Patch(color=ON_TIME, label='job on time'), mpatches.Patch(color=TARDY, label='job tardy'),
               mpatches.Patch(facecolor='white', edgecolor=MAINTENANCE, hatch='///', label='maintenance'),
               mpatches.Patch(color=WINDOW, label='maintenance window')]
    if title:
        fig.suptitle(title, fontsize=11)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.legend(handles=handles, loc='lower center', ncol=4, fontsize=9, frameon=False)
    fig.savefig(path, dpi=200, bbox_inches='tight')
    plt.close(fig)
