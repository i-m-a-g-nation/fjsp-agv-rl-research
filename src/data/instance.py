from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


MachineOption = Tuple[int, int]


@dataclass(frozen=True)
class Operation:
    op_id: int
    machine_options: Tuple[MachineOption, ...]


@dataclass(frozen=True)
class Job:
    job_id: int
    operations: Tuple[Operation, ...]

    @property
    def num_ops(self) -> int:
        return len(self.operations)


@dataclass
class FJSPInstance:
    num_jobs: int
    num_machines: int
    jobs: List[Job] = field(default_factory=list)

    @property
    def total_ops(self) -> int:
        return sum(job.num_ops for job in self.jobs)

    @classmethod
    def from_jobs_array(
        cls,
        jobs_array: List[List[List[MachineOption]]],
        num_machines: int | None = None,
    ) -> FJSPInstance:
        num_jobs = len(jobs_array)
        if num_machines is None:
            machine_ids: set[int] = set()
            for job_ops in jobs_array:
                for op_options in job_ops:
                    for m_id, _ in op_options:
                        machine_ids.add(m_id)
            num_machines = max(machine_ids) + 1 if machine_ids else 0

        jobs: list[Job] = []
        for j_idx, job_ops in enumerate(jobs_array):
            ops: list[Operation] = []
            for o_idx, op_options in enumerate(job_ops):
                ops.append(Operation(
                    op_id=o_idx,
                    machine_options=tuple((m_id, pt) for m_id, pt in op_options),
                ))
            jobs.append(Job(job_id=j_idx, operations=tuple(ops)))

        return cls(num_jobs=num_jobs, num_machines=num_machines, jobs=jobs)

    def get_op_options(self, job_id: int, op_id: int) -> Tuple[MachineOption, ...]:
        return self.jobs[job_id].operations[op_id].machine_options

    def get_processing_time(self, job_id: int, op_id: int, machine_id: int) -> int:
        for m_id, pt in self.get_op_options(job_id, op_id):
            if m_id == machine_id:
                return pt
        raise ValueError(f"Machine {machine_id} not in options for Job {job_id} Op {op_id}")

    def is_machine_eligible(self, job_id: int, op_id: int, machine_id: int) -> bool:
        return any(m_id == machine_id for m_id, _ in self.get_op_options(job_id, op_id))


def create_toy_instance() -> FJSPInstance:
    jobs_array: List[List[List[MachineOption]]] = [
        [
            [(0, 3), (1, 5)],
            [(1, 4), (2, 6)],
        ],
        [
            [(0, 2), (2, 4)],
            [(1, 3)],
        ],
        [
            [(0, 5)],
            [(1, 3), (2, 2)],
            [(0, 1), (1, 2)],
        ],
    ]
    return FJSPInstance.from_jobs_array(jobs_array)
