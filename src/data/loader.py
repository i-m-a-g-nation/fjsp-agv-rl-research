from __future__ import annotations

from typing import List, Tuple
from dataclasses import dataclass
from pathlib import Path

from src.data.instance import FJSPInstance, MachineOption


@dataclass
class ParsedInstance:
    num_jobs: int
    num_machines: int
    mean_machines_per_op: float
    jobs: List[List[List[MachineOption]]]


def _clean_benchmark_text(text: str) -> str:
    """Drop comments/blank lines and flatten benchmark text into token order."""

    lines = text.strip().splitlines()
    clean_lines = [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]
    return " ".join(clean_lines)


def _normalize_machine_options(
    jobs: List[List[List[MachineOption]]],
    num_machines: int,
    machine_index_base: int | str,
) -> List[List[List[MachineOption]]]:
    """Normalize benchmark machine ids to the internal 0-based convention."""

    machine_ids = [
        m_id
        for job_ops in jobs
        for op_options in job_ops
        for m_id, _pt in op_options
    ]

    if not machine_ids:
        raise ValueError("Benchmark instance contains no machine options")

    if machine_index_base == "auto":
        # Many FJSP datasets use 1-based machines, while local toy instances
        # use 0-based ids. The minimum id is enough for the supported formats.
        if min(machine_ids) == 0:
            offset = 0
        elif min(machine_ids) == 1:
            offset = 1
        else:
            raise ValueError(
                "Cannot infer machine index base: minimum machine id is "
                f"{min(machine_ids)}"
            )
    elif machine_index_base in (0, 1):
        offset = int(machine_index_base)
    else:
        raise ValueError("machine_index_base must be 0, 1, or 'auto'")

    normalized: List[List[List[MachineOption]]] = []
    for job_ops in jobs:
        normalized_ops: List[List[MachineOption]] = []
        for op_options in job_ops:
            normalized_options: List[MachineOption] = []
            for m_id, pt in op_options:
                normalized_id = m_id - offset
                if normalized_id < 0 or normalized_id >= num_machines:
                    raise ValueError(
                        f"Machine id {m_id} is outside valid range after "
                        f"normalization for {num_machines} machines"
                    )
                if pt <= 0:
                    raise ValueError(f"Processing time must be positive, got {pt}")
                normalized_options.append((normalized_id, pt))
            normalized_ops.append(normalized_options)
        normalized.append(normalized_ops)

    return normalized


def parse_brandimarte_line(
    line: str,
    machine_index_base: int | str = "auto",
) -> Tuple[List[List[MachineOption]], int, float]:
    """Parse one flattened Brandimarte/FJSPLib-style instance."""

    parts = line.strip().split()
    if not parts:
        raise ValueError("Empty line")

    if len(parts) < 3:
        raise ValueError("Benchmark header must contain jobs, machines, and mean machines")

    num_jobs = int(parts[0])
    num_machines = int(parts[1])
    mean_machines = float(parts[2])
    if num_jobs <= 0 or num_machines <= 0:
        raise ValueError("Number of jobs and machines must be positive")

    idx = 3

    jobs: List[List[List[MachineOption]]] = []
    for job_id in range(num_jobs):
        if idx >= len(parts):
            raise ValueError(f"Missing operation count for job {job_id}")
        operations: List[List[MachineOption]] = []
        num_ops = int(parts[idx])
        idx += 1
        if num_ops <= 0:
            raise ValueError(f"Job {job_id} must contain at least one operation")
        for op_id in range(num_ops):
            if idx >= len(parts):
                raise ValueError(f"Missing machine option count for job {job_id} op {op_id}")
            num_options = int(parts[idx])
            idx += 1
            if num_options <= 0:
                raise ValueError(f"Job {job_id} op {op_id} has no machine options")
            options: List[MachineOption] = []
            for _ in range(num_options):
                # Each option is stored as a machine-processing_time pair.
                if idx + 1 >= len(parts):
                    raise ValueError(f"Incomplete machine option for job {job_id} op {op_id}")
                m_id = int(parts[idx])
                pt = int(parts[idx + 1])
                options.append((m_id, pt))
                idx += 2
            operations.append(options)
        jobs.append(operations)

    if idx != len(parts):
        raise ValueError(f"Unexpected trailing tokens in benchmark instance: {parts[idx:]}")

    normalized_jobs = _normalize_machine_options(jobs, num_machines, machine_index_base)
    return normalized_jobs, num_machines, mean_machines


def parse_fjsplib_text(
    text: str,
    machine_index_base: int | str = "auto",
) -> ParsedInstance:
    """Parse a possibly multi-line benchmark text block."""

    single_line = _clean_benchmark_text(text)
    jobs_list, num_machines, mean = parse_brandimarte_line(
        single_line,
        machine_index_base=machine_index_base,
    )
    return ParsedInstance(
        num_jobs=len(jobs_list),
        num_machines=num_machines,
        mean_machines_per_op=mean,
        jobs=jobs_list,
    )


def load_benchmark_instance(
    text: str,
    machine_index_base: int | str = "auto",
) -> FJSPInstance:
    """Parse benchmark text and build the internal immutable instance model."""

    parsed = parse_fjsplib_text(text, machine_index_base=machine_index_base)
    return FJSPInstance.from_jobs_array(parsed.jobs, parsed.num_machines)


def load_benchmark_file(
    path: str | Path,
    machine_index_base: int | str = "auto",
    encoding: str = "utf-8",
) -> FJSPInstance:
    """Load a benchmark file with explicit encoding and parse it."""

    text = Path(path).read_text(encoding=encoding)
    return load_benchmark_instance(text, machine_index_base=machine_index_base)


TOY_INSTANCES: dict[str, str] = {
    "toy_3x3": (
        "3 3 2.0\n"
        "2 2 0 3 1 5 2 1 4 2 6\n"
        "2 2 0 2 2 4 1 1 3\n"
        "3 1 0 5 2 1 3 2 2 2 0 1 1 2\n"
    ),
}
