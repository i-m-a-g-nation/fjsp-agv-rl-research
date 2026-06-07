from __future__ import annotations

from dataclasses import dataclass

from src.data.instance import FJSPInstance, MachineOption
from src.dynamic.events import (
    DynamicEvent,
    JobArrival,
    MachineBreakdown,
    MachineRepair,
    ProcessingTimeChange,
)


@dataclass(frozen=True)
class DynamicFJSPState:
    """Minimal dynamic FJSP state for Phase 2A rescheduling."""

    instance: FJSPInstance
    current_time: int = 0
    released_job_ids: frozenset[int] | None = None
    job_release_times: tuple[int, ...] | None = None
    machine_unavailable_until: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if self.current_time < 0:
            raise ValueError("current_time must be non-negative")
        released = (
            frozenset(range(self.instance.num_jobs))
            if self.released_job_ids is None
            else self.released_job_ids
        )
        release_times = (
            tuple(0 for _ in range(self.instance.num_jobs))
            if self.job_release_times is None
            else self.job_release_times
        )
        unavailable = (
            tuple(0 for _ in range(self.instance.num_machines))
            if self.machine_unavailable_until is None
            else self.machine_unavailable_until
        )
        if any(job_id < 0 or job_id >= self.instance.num_jobs for job_id in released):
            raise ValueError("released_job_ids contains an invalid job id")
        if len(release_times) != self.instance.num_jobs:
            raise ValueError("job_release_times length must match num_jobs")
        if any(time < 0 for time in release_times):
            raise ValueError("job_release_times values must be non-negative")
        if any(release_times[job_id] > self.current_time for job_id in released):
            raise ValueError("released jobs cannot have release times in the future")
        if len(unavailable) != self.instance.num_machines:
            raise ValueError("machine_unavailable_until length must match num_machines")
        if any(time < 0 for time in unavailable):
            raise ValueError("machine_unavailable_until values must be non-negative")
        object.__setattr__(self, "released_job_ids", released)
        object.__setattr__(self, "job_release_times", release_times)
        object.__setattr__(self, "machine_unavailable_until", unavailable)

    @classmethod
    def from_instance(
        cls,
        instance: FJSPInstance,
        current_time: int = 0,
    ) -> DynamicFJSPState:
        """Create a dynamic state where all existing jobs are released."""

        return cls(instance=instance, current_time=current_time)

    def apply_event(self, event: DynamicEvent) -> DynamicFJSPState:
        """Return a new state after applying one event."""

        if event.time < self.current_time:
            raise ValueError("event time cannot be earlier than current_time")
        if isinstance(event, MachineBreakdown):
            self._validate_machine(event.machine_id)
            unavailable = list(self.machine_unavailable_until or ())
            unavailable[event.machine_id] = max(
                unavailable[event.machine_id],
                event.repair_time,
            )
            return self._replace(
                current_time=event.time,
                machine_unavailable_until=tuple(unavailable),
            )
        if isinstance(event, MachineRepair):
            self._validate_machine(event.machine_id)
            unavailable = list(self.machine_unavailable_until or ())
            unavailable[event.machine_id] = event.time
            return self._replace(
                current_time=event.time,
                machine_unavailable_until=tuple(unavailable),
            )
        if isinstance(event, JobArrival):
            return self._append_arriving_job(event)
        if isinstance(event, ProcessingTimeChange):
            return self._change_processing_time(event)
        raise TypeError(f"unsupported dynamic event: {type(event).__name__}")

    def _replace(
        self,
        *,
        instance: FJSPInstance | None = None,
        current_time: int | None = None,
        released_job_ids: frozenset[int] | None = None,
        job_release_times: tuple[int, ...] | None = None,
        machine_unavailable_until: tuple[int, ...] | None = None,
    ) -> DynamicFJSPState:
        return DynamicFJSPState(
            instance=self.instance if instance is None else instance,
            current_time=self.current_time if current_time is None else current_time,
            released_job_ids=(
                self.released_job_ids if released_job_ids is None else released_job_ids
            ),
            job_release_times=(
                self.job_release_times if job_release_times is None else job_release_times
            ),
            machine_unavailable_until=(
                self.machine_unavailable_until
                if machine_unavailable_until is None
                else machine_unavailable_until
            ),
        )

    def _append_arriving_job(self, event: JobArrival) -> DynamicFJSPState:
        for op_options in event.operations:
            for machine_id, _processing_time in op_options:
                self._validate_machine(machine_id)
        jobs_array = _jobs_array_from_instance(self.instance)
        jobs_array.append([list(op_options) for op_options in event.operations])
        new_instance = FJSPInstance.from_jobs_array(
            jobs_array,
            num_machines=self.instance.num_machines,
        )
        released = frozenset(set(self.released_job_ids or ()) | {new_instance.num_jobs - 1})
        release_times = tuple(self.job_release_times or ()) + (event.time,)
        return self._replace(
            instance=new_instance,
            current_time=event.time,
            released_job_ids=released,
            job_release_times=release_times,
        )

    def _change_processing_time(
        self,
        event: ProcessingTimeChange,
    ) -> DynamicFJSPState:
        if event.job_id >= self.instance.num_jobs:
            raise ValueError("job_id is out of range")
        if event.op_id >= self.instance.jobs[event.job_id].num_ops:
            raise ValueError("op_id is out of range")
        self._validate_machine(event.machine_id)

        jobs_array = _jobs_array_from_instance(self.instance)
        options = jobs_array[event.job_id][event.op_id]
        for idx, (machine_id, _processing_time) in enumerate(options):
            if machine_id == event.machine_id:
                options[idx] = (machine_id, event.new_processing_time)
                new_instance = FJSPInstance.from_jobs_array(
                    jobs_array,
                    num_machines=self.instance.num_machines,
                )
                return self._replace(instance=new_instance, current_time=event.time)
        raise ValueError("machine_id is not eligible for the selected operation")

    def _validate_machine(self, machine_id: int) -> None:
        if machine_id < 0 or machine_id >= self.instance.num_machines:
            raise ValueError("machine_id is out of range")


def _jobs_array_from_instance(
    instance: FJSPInstance,
) -> list[list[list[MachineOption]]]:
    """Return a mutable jobs-array copy of an instance."""

    return [
        [list(operation.machine_options) for operation in job.operations]
        for job in instance.jobs
    ]
