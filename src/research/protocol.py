"""Protocol validation and independent seeded perturbation snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
import random
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.data.instance import FJSPInstance
from src.dynamic import DynamicFJSPState, frozen_records_at_time, reschedule_from_state
from src.dynamic.event_specs import event_from_spec
from src.scheduling.encoding import ScheduleRecord, ScheduleResult

Identifier = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]
Seed = Annotated[int, Field(strict=True, ge=0, le=4294967295)]
EventType = Literal["machine_breakdown", "job_arrival", "processing_time_change"]


class InstanceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Identifier
    path: str = Field(min_length=1)


class Protocol(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Annotated[int, Field(strict=True, ge=1, le=1)]
    protocol_id: Identifier
    phase: Literal["Phase 2A"]
    instances: tuple[InstanceSpec, ...] = Field(min_length=1, max_length=30)
    event_types: tuple[EventType, ...] = Field(min_length=1, max_length=3)
    rules: tuple[Literal["fifo", "spt", "eft"], ...] = Field(min_length=1, max_length=3)
    seeds: tuple[Seed, ...] = Field(min_length=1, max_length=10)
    timing_repetitions: Annotated[int, Field(strict=True, ge=1, le=10)]

    @model_validator(mode="after")
    def unique_entries(self):
        values = [self.event_types, self.rules, self.seeds,
                  [item.id for item in self.instances], [item.path for item in self.instances]]
        if any(len(set(items)) != len(items) for items in values):
            raise ValueError("Protocol entries must be unique")
        return self

    @property
    def expected_runs(self) -> int:
        return len(self.instances) * len(self.event_types) * len(self.seeds) * len(self.rules) * self.timing_repetitions


def instance_path(project_root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or PureWindowsPath(relative).drive or "\\" in relative or ".." in path.parts:
        raise ValueError("Instance paths must be portable project-relative paths")
    resolved = (project_root / path).resolve()
    if not resolved.is_relative_to(project_root.resolve()):
        raise ValueError("Instance path escapes project root")
    return resolved


def load_protocol(path: Path, project_root: Path) -> Protocol:
    protocol = Protocol.model_validate_json(Path(path).read_bytes())
    resolved = [instance_path(project_root, item.path) for item in protocol.instances]
    if len(set(resolved)) != len(resolved):
        raise ValueError("Instance paths alias the same file")
    return protocol


@dataclass(frozen=True)
class DynamicCase:
    initial: ScheduleResult
    state: DynamicFJSPState
    frozen: tuple[ScheduleRecord, ...]
    event_spec: dict


def build_case(instance: FJSPInstance, event_type: EventType, seed: int) -> DynamicCase:
    initial = reschedule_from_state(DynamicFJSPState.from_instance(instance), rule="fifo")
    time = max(1, initial.makespan // 3)
    future = sorted((r for r in initial.records if r.start >= time), key=lambda r: (r.job_id, r.op_id))
    rng = random.Random(seed)
    spec = {"type": event_type, "time": time}
    if event_type == "machine_breakdown":
        if not future:
            raise ValueError("No future operation is available for the breakdown case")
        machine = rng.choice(sorted({r.machine_id for r in future}))
        running = [r.end for r in initial.records if r.machine_id == machine and r.start < time < r.end]
        time = max([time, *running])
        duration = rng.randint(max(1, initial.makespan // 10), max(1, initial.makespan // 3))
        spec.update(time=time, machine_id=machine, repair_time=time + duration)
    elif event_type == "job_arrival":
        job = rng.choice(instance.jobs)
        spec["operations"] = [[list(option) for option in operation.machine_options] for operation in job.operations]
    elif event_type == "processing_time_change":
        if not future:
            raise ValueError("No unstarted operation is available for a duration change")
        record = rng.choice(future)
        spec.update(job_id=record.job_id, op_id=record.op_id, machine_id=record.machine_id,
                    new_processing_time=max(record.processing_time + 1, (3 * record.processing_time + 1) // 2))
    else:
        raise ValueError(f"Unsupported protocol event: {event_type}")
    frozen = tuple(frozen_records_at_time(initial, time))
    state = DynamicFJSPState.from_instance(instance, current_time=time).apply_event(event_from_spec(spec))
    return DynamicCase(initial, state, frozen, spec)
