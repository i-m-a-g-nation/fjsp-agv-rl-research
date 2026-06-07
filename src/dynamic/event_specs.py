from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from src.dynamic.events import (
    DynamicEvent,
    JobArrival,
    MachineBreakdown,
    MachineRepair,
    ProcessingTimeChange,
)


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


def _required_str(spec: Mapping[str, Any], key: str) -> str:
    value = spec.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"event spec field {key!r} must be a non-empty string")
    return value


def _required_int(spec: Mapping[str, Any], key: str) -> int:
    value = spec.get(key)
    if not isinstance(value, int):
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
                or not isinstance(option[0], int)
                or not isinstance(option[1], int)
            ):
                raise ValueError(
                    "machine options must be [machine_id, processing_time] pairs"
                )
            parsed_options.append((option[0], option[1]))
        operations.append(tuple(parsed_options))
    return tuple(operations)
