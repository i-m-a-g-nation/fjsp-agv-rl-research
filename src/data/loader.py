from __future__ import annotations

from typing import List, Tuple
from dataclasses import dataclass

from src.data.instance import FJSPInstance, MachineOption


@dataclass
class ParsedInstance:
    num_jobs: int
    num_machines: int
    mean_machines_per_op: float
    jobs: List[List[List[MachineOption]]]


def parse_brandimarte_line(line: str) -> Tuple[List[List[MachineOption]], int, int]:
    parts = line.strip().split()
    if not parts:
        raise ValueError("Empty line")

    num_jobs = int(parts[0])
    num_machines = int(parts[1])
    mean_machines = float(parts[2])
    idx = 3

    jobs: List[List[List[MachineOption]]] = []
    for _ in range(num_jobs):
        operations: List[List[MachineOption]] = []
        num_ops = int(parts[idx])
        idx += 1
        for _ in range(num_ops):
            num_options = int(parts[idx])
            idx += 1
            options: List[MachineOption] = []
            for _ in range(num_options):
                m_id = int(parts[idx])
                pt = int(parts[idx + 1])
                options.append((m_id, pt))
                idx += 2
            operations.append(options)
        jobs.append(operations)

    return jobs, num_machines, int(mean_machines * 10) / 10


def load_benchmark_instance(text: str) -> FJSPInstance:
    lines = text.strip().split("\n")
    lines = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    single_line = " ".join(lines)

    jobs_list, num_machines, _mean = parse_brandimarte_line(single_line)

    instance = FJSPInstance.from_jobs_array(jobs_list, num_machines)
    return instance


TOY_INSTANCES: dict[str, str] = {
    "toy_3x3": (
        "3 3 2.0\n"
        "2 2 0 3 1 5 2 1 4 2 6\n"
        "2 2 0 2 2 4 1 1 3\n"
        "3 1 0 5 2 1 3 2 2 2 0 1 1 2\n"
    ),
}
