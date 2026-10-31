"""Immutable static FJSP instance: jobs[job_id][op_id] = ((machine_id, time), ...)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

# A feasible machine option for one operation.
# All internal algorithms assume machine_id is already normalized to 0-based.
MachineOption = Tuple[int, int]


def _require_integer(value: object, name: str, *, positive: bool = False) -> None:
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer (bool is not allowed)")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    if not positive and value < 0:
        raise ValueError(f"{name} must be non-negative")


def _as_tuple(value: object, name: str) -> tuple:
    if type(value) not in (list, tuple):
        raise ValueError(f"{name} must be a list or tuple")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class Operation:
    """One ordered operation inside a job."""

    op_id: int
    machine_options: Tuple[MachineOption, ...]

    def __post_init__(self) -> None:
        options = _as_tuple(self.machine_options, "machine options")
        frozen_options = tuple(_as_tuple(option, "machine option") for option in options)
        object.__setattr__(self, "machine_options", frozen_options)
        _validate_operation(self)


@dataclass(frozen=True, slots=True)
class Job:
    """A job with an ordered sequence of operations."""

    job_id: int
    operations: Tuple[Operation, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "operations", _as_tuple(self.operations, "operations"))
        _validate_job(self)

    @property
    def num_ops(self) -> int:
        return len(self.operations)


@dataclass(frozen=True, slots=True)
class FJSPInstance:
    """Static flexible job shop instance.

    Machine ids are expected to be 0-based:
    0, 1, ..., num_machines - 1.
    """

    num_jobs: int
    num_machines: int
    jobs: Tuple[Job, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "jobs", _as_tuple(self.jobs, "jobs"))
        validate_instance(self)

    @property
    def total_ops(self) -> int:
        return sum(job.num_ops for job in self.jobs)

    @classmethod
    def from_jobs_array(
        cls,
        jobs_array: Sequence[Sequence[Sequence[MachineOption]]],
        num_machines: int | None = None,
    ) -> FJSPInstance:
        """Build an instance from jobs_array[job_id][op_id] options."""

        jobs_array = _as_tuple(jobs_array, "jobs_array")
        if not jobs_array:
            raise ValueError("FJSP instance must contain at least one job")
        if num_machines is not None:
            _require_integer(num_machines, "num_machines", positive=True)

        # Freeze jobs and operations so solver code cannot accidentally mutate
        # the instance data while building a schedule.
        jobs: list[Job] = []
        for j_idx, job_ops in enumerate(jobs_array):
            job_ops = _as_tuple(job_ops, f"job {j_idx} operations")
            ops = tuple(
                Operation(op_id=o_idx, machine_options=op_options)
                for o_idx, op_options in enumerate(job_ops)
            )
            jobs.append(Job(job_id=j_idx, operations=ops))

        if num_machines is None:
            num_machines = 1 + max(
                m_id
                for job in jobs
                for operation in job.operations
                for m_id, _ in operation.machine_options
            )

        return cls(num_jobs=len(jobs), num_machines=num_machines, jobs=tuple(jobs))

    def get_op_options(self, job_id: int, op_id: int) -> Tuple[MachineOption, ...]:
        """Return all eligible machine options for one operation."""
        _require_integer(job_id, "job_id")
        _require_integer(op_id, "op_id")
        if job_id >= self.num_jobs or op_id >= self.jobs[job_id].num_ops:
            raise ValueError("job_id or op_id is outside the instance")
        return self.jobs[job_id].operations[op_id].machine_options

    def get_processing_time(self, job_id: int, op_id: int, machine_id: int) -> int:
        """Return processing time for an operation on a selected machine."""

        _require_integer(machine_id, "machine_id")
        for m_id, pt in self.get_op_options(job_id, op_id):
            if m_id == machine_id:
                return pt
        raise ValueError(f"Machine {machine_id} not in options for Job {job_id} Op {op_id}")

    def is_machine_eligible(self, job_id: int, op_id: int, machine_id: int) -> bool:
        """Return whether a machine can process the selected operation."""

        _require_integer(machine_id, "machine_id")
        return any(m_id == machine_id for m_id, _ in self.get_op_options(job_id, op_id))


def _validate_operation(operation: Operation) -> None:
    if not isinstance(operation, Operation):
        raise ValueError("operations must contain Operation objects")
    _require_integer(getattr(operation, "op_id", None), "op_id")
    options = getattr(operation, "machine_options", None)
    if type(options) is not tuple:
        raise ValueError("machine options must be an immutable tuple")
    if not options:
        raise ValueError(f"operation {operation.op_id} must have machine options")
    seen: set[int] = set()
    for option in options:
        if type(option) is not tuple or len(option) != 2:
            raise ValueError("machine option must be an immutable (machine_id, processing_time) pair")
        machine_id, processing_time = option
        _require_integer(machine_id, "machine_id")
        _require_integer(processing_time, "processing_time", positive=True)
        if machine_id in seen:
            raise ValueError(f"operation {operation.op_id} has duplicate machine id {machine_id}")
        seen.add(machine_id)


def _validate_job(job: Job) -> None:
    if not isinstance(job, Job):
        raise ValueError("jobs must contain Job objects")
    _require_integer(getattr(job, "job_id", None), "job_id")
    operations = getattr(job, "operations", None)
    if type(operations) is not tuple:
        raise ValueError("operations must be an immutable tuple")
    if not operations:
        raise ValueError(f"job {job.job_id} must contain at least one operation")
    for op_id, operation in enumerate(operations):
        _validate_operation(operation)
        if operation.op_id != op_id:
            raise ValueError(f"job {job.job_id} op_id must match its position {op_id}")


def validate_instance(instance: FJSPInstance) -> None:
    """Recheck the complete immutable instance contract without modifying input.

    Raises ValueError for invalid data or structure, including objects forged
    without constructors or changed through low-level attribute access.
    """

    if not isinstance(instance, FJSPInstance):
        raise ValueError("instance must be an FJSPInstance")
    _require_integer(getattr(instance, "num_jobs", None), "num_jobs", positive=True)
    _require_integer(getattr(instance, "num_machines", None), "num_machines", positive=True)
    jobs = getattr(instance, "jobs", None)
    if type(jobs) is not tuple:
        raise ValueError("jobs must be an immutable tuple")
    if not jobs:
        raise ValueError("FJSP instance must contain at least one job")
    if instance.num_jobs != len(jobs):
        raise ValueError("num_jobs must match the number of jobs")
    for job_id, job in enumerate(jobs):
        _validate_job(job)
        if job.job_id != job_id:
            raise ValueError(f"job_id must match its position {job_id}")
        for operation in job.operations:
            for machine_id, _ in operation.machine_options:
                if machine_id >= instance.num_machines:
                    raise ValueError(
                        f"machine_id {machine_id} exceeds num_machines {instance.num_machines}"
                    )


def create_toy_instance() -> FJSPInstance:
    """Create a small 3-job, 3-machine instance for tests and examples."""

    # This fixture is intentionally tiny but still flexible: several operations
    # have more than one eligible machine, so heuristics can make real choices.
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
