"""Phase 2A dynamic events and their JSON event-spec format."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from fjsp_lab.fjsp.instance import MachineOption


def _require_int(value: object, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer (bool is not allowed)")


@dataclass(frozen=True)
class DynamicEvent:
    """Base class for a Phase 2A dynamic scheduling event."""

    time: int

    def __post_init__(self) -> None:
        _require_int(self.time, "event time")


@dataclass(frozen=True)
class MachineBreakdown(DynamicEvent):
    """A machine cannot start new operations until repair_time."""

    machine_id: int
    repair_time: int

    def __post_init__(self) -> None:
        super().__post_init__()
        _require_int(self.machine_id, "machine_id")
        _require_int(self.repair_time, "repair_time")
        if self.repair_time < self.time:
            raise ValueError("repair_time must be greater than or equal to time")


@dataclass(frozen=True)
class MachineRepair(DynamicEvent):
    """A machine is available again from this event time."""

    machine_id: int

    def __post_init__(self) -> None:
        super().__post_init__()
        _require_int(self.machine_id, "machine_id")


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
                _require_int(machine_id, "machine_id")
                _require_int(processing_time, "processing_time")
                if processing_time == 0:
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
        for name in ("job_id", "op_id", "machine_id", "new_processing_time"):
            _require_int(getattr(self, name), name)
        if self.new_processing_time == 0:
            raise ValueError("new_processing_time must be positive")

def event_from_spec(spec: Mapping[str, Any]) -> DynamicEvent:
    """Build one dynamic event from a structured dictionary."""

    event_type = _required_str(spec, "type")
    time = _required_int(spec, "time")

    if event_type == "machine_breakdown":
        return MachineBreakdown(
            time=time,
            machine_id=_required_int(spec, "machine_id"),
            repair_time=_required_int(spec, "repair_time"),
        )
    if event_type == "machine_repair":
        return MachineRepair(
            time=time,
            machine_id=_required_int(spec, "machine_id"),
        )
    if event_type == "job_arrival":
        return JobArrival(
            time=time,
            operations=_parse_job_operations(spec.get("operations")),
        )
    if event_type == "processing_time_change":
        return ProcessingTimeChange(
            time=time,
            job_id=_required_int(spec, "job_id"),
            op_id=_required_int(spec, "op_id"),
            machine_id=_required_int(spec, "machine_id"),
            new_processing_time=_required_int(spec, "new_processing_time"),
        )
    raise ValueError(f"unsupported dynamic event type: {event_type}")


def events_from_specs(specs: Iterable[Mapping[str, Any]]) -> list[DynamicEvent]:
    """Build a list of dynamic events from structured dictionaries."""

    return [event_from_spec(spec) for spec in specs]


def load_event_specs_json(path: str | Path) -> list[DynamicEvent]:
    """Load a UTF-8 JSON array of dynamic event specs."""

    with Path(path).open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, list):
        raise ValueError("dynamic event JSON must contain a list of event specs")
    for item in payload:
        if not isinstance(item, Mapping):
            raise ValueError("dynamic event JSON entries must be objects")
    return events_from_specs(payload)


def _required_str(spec: Mapping[str, Any], key: str) -> str:
    value = spec.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"event spec field {key!r} must be a non-empty string")
    return value


def _required_int(spec: Mapping[str, Any], key: str) -> int:
    value = spec.get(key)
    if type(value) is not int:
        raise ValueError(f"event spec field {key!r} must be an integer")
    return value


def _parse_job_operations(value: Any) -> tuple[tuple[tuple[int, int], ...], ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("job_arrival operations must be a non-empty list")

    operations: list[tuple[tuple[int, int], ...]] = []
    for op_options in value:
        if not isinstance(op_options, list) or not op_options:
            raise ValueError("each arriving operation must have machine options")
        parsed_options = []
        for option in op_options:
            if (
                not isinstance(option, (list, tuple))
                or len(option) != 2
                or type(option[0]) is not int
                or type(option[1]) is not int
            ):
                raise ValueError(
                    "machine options must be [machine_id, processing_time] pairs"
                )
            parsed_options.append((option[0], option[1]))
        operations.append(tuple(parsed_options))
    return tuple(operations)
