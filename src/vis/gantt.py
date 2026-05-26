from __future__ import annotations

from pathlib import Path
from typing import Dict

import matplotlib
matplotlib.use("Agg")

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

from src.scheduling.encoding import ScheduleResult


COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


def plot_gantt(
    result: ScheduleResult,
    title: str = "FJSP Schedule Gantt Chart",
    save_path: str | Path | None = None,
) -> None:
    machines = sorted(set(r.machine_id for r in result.records))
    fig_height = max(4, len(machines) * 0.8)
    fig, ax = plt.subplots(figsize=(12, fig_height))

    machine_to_row = {m: i for i, m in enumerate(machines)}

    job_colors: Dict[int, str] = {}
    for record in result.records:
        if record.job_id not in job_colors:
            job_colors[record.job_id] = COLORS[record.job_id % len(COLORS)]

    for record in result.records:
        color = job_colors[record.job_id]
        y = machine_to_row[record.machine_id]
        ax.barh(
            y,
            record.end - record.start,
            left=record.start,
            height=0.6,
            color=color,
            edgecolor="black",
            linewidth=0.5,
        )
        ax.text(
            record.start + (record.end - record.start) / 2,
            y,
            f"J{record.job_id}O{record.op_id}",
            ha="center",
            va="center",
            fontsize=8,
            fontweight="bold",
        )

    ax.set_yticks(list(machine_to_row.values()))
    ax.set_yticklabels([f"M{m}" for m in machines])
    ax.set_xlabel("Time")
    ax.set_ylabel("Machine")
    ax.set_title(title)
    ax.grid(axis="x", linestyle="--", alpha=0.5)
    ax.set_ylim(-0.6, len(machines) - 0.4)
    ax.invert_yaxis()

    if result.instance is not None:
        legend_patches = [
            mpatches.Patch(color=COLORS[j % len(COLORS)], label=f"Job {j}")
            for j in range(result.instance.num_jobs)
        ]
        ax.legend(handles=legend_patches, loc="upper right", fontsize=8)

    plt.tight_layout()

    if save_path:
        fig.savefig(str(save_path), dpi=150, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()
