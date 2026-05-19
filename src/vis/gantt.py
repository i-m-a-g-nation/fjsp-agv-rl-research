from __future__ import annotations

import matplotlib
matplotlib.use("Agg")  # 非交互 backend，避免 Windows 下 savefig 崩溃

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from typing import Dict, List
from pathlib import Path

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
    fig, ax = plt.subplots(figsize=(12, max(4, len(set(r.machine_id for r in result.records)) * 0.8)))

    # 按机器编号分配行号，同一机器的所有工序在同一行
    machines = sorted(set(r.machine_id for r in result.records))
    machine_to_row = {m: i for i, m in enumerate(machines)}

    # 每个工件分配固定颜色，循环使用调色板
    job_colors: Dict[int, str] = {}
    for r in result.records:
        if r.job_id not in job_colors:
            job_colors[r.job_id] = COLORS[r.job_id % len(COLORS)]

    for r in result.records:
        color = job_colors[r.job_id]
        y = machine_to_row[r.machine_id]
        ax.barh(
            y, r.end - r.start, left=r.start, height=0.6,
            color=color, edgecolor="black", linewidth=0.5,
        )
        ax.text(
            r.start + (r.end - r.start) / 2, y,
            f"J{r.job_id}O{r.op_id}",
            ha="center", va="center", fontsize=8, fontweight="bold",
        )

    ax.set_yticks(list(machine_to_row.values()))
    ax.set_yticklabels([f"M{m}" for m in machines])
    ax.set_xlabel("Time")
    ax.set_ylabel("Machine")
    ax.set_title(title)
    ax.grid(axis="x", linestyle="--", alpha=0.5)
    ax.set_ylim(-0.6, len(machines) - 0.4)
    ax.invert_yaxis()  # 机器0在最上方，符合调度图惯例

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
