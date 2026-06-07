from __future__ import annotations

from dataclasses import dataclass

from src.data.instance import MachineOption


@dataclass(frozen=True)
class DynamicEvent:
    """Base class for a Phase 2A dynamic scheduling event."""

    time: int

    def __post_init__(self) -> None:
        if self.time < 0:
            raise ValueError("event time must be non-negative")


@dataclass(frozen=True)
class MachineBreakdown(DynamicEvent):
    """A machine cannot start new operations until repair_time."""

    machine_id: int
    repair_time: int

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.machine_id < 0:
            raise ValueError("machine_id must be non-negative")
        if self.repair_time < self.time:
            raise ValueError("repair_time must be greater than or equal to time")


@dataclass(frozen=True)
class MachineRepair(DynamicEvent):
    """A machine is available again from this event time."""

    machine_id: int

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.machine_id < 0:
            raise ValueError("machine_id must be non-negative")


@dataclass(frozen=True)
class JobArrival(DynamicEvent):
    """A new job arrives with an ordered list of operation options."""

    operations: tuple[tuple[MachineOption, ...], ...]

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.operations:
            raise ValueError("arriving job must contain at least one operation")
        for op_options in self.operations:
            if not op_options:
                raise ValueError("arriving operation must have machine options")
            for machine_id, processing_time in op_options:
                if machine_id < 0:
                    raise ValueError("machine_id must be non-negative")
                if processing_time <= 0:
                    raise ValueError("processing_time must be positive")


@dataclass(frozen=True)
class ProcessingTimeChange(DynamicEvent):
    """Update one future operation-machine processing time."""

    job_id: int
    op_id: int
    machine_id: int
    new_processing_time: int

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.job_id < 0 or self.op_id < 0 or self.machine_id < 0:
            raise ValueError("job_id, op_id, and machine_id must be non-negative")
        if self.new_processing_time <= 0:
            raise ValueError("new_processing_time must be positive")
