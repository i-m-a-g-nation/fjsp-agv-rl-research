"""Phase 2A protocol: one seeded perturbation of a FIFO initial schedule.

A protocol JSON names benchmark instances, event types, rules, seeds and
timing repetitions. ``build_case`` derives one dynamic case per
(instance, event type, seed): the FIFO schedule, a single event at about
one third of its makespan, the frozen records and the post-event state.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PureWindowsPath
import random
import re

from fjsp_lab.dynamic.events import event_from_spec
from fjsp_lab.dynamic.reschedule import reschedule_from_state
from fjsp_lab.dynamic.snapshot import frozen_records_at_time
from fjsp_lab.dynamic.state import DynamicFJSPState
from fjsp_lab.fjsp.instance import FJSPInstance
from fjsp_lab.fjsp.schedule import ScheduleRecord, ScheduleResult

EVENT_TYPES = ("machine_breakdown", "job_arrival", "processing_time_change")
RULES = ("fifo", "spt", "eft")
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class Protocol:
    protocol_id: str
    instances: tuple[tuple[str, str], ...]   # (id, project-relative path)
    event_types: tuple[str, ...]
    rules: tuple[str, ...]
    seeds: tuple[int, ...]
    timing_repetitions: int

    @property
    def expected_runs(self) -> int:
        return (len(self.instances) * len(self.event_types) * len(self.seeds)
                * len(self.rules) * self.timing_repetitions)


def _unique(values, name: str) -> tuple:
    values = tuple(values)
    if not values or len(set(values)) != len(values):
        raise ValueError(f"protocol {name} must be a non-empty list of unique values")
    return values


def parse_protocol(raw: bytes) -> Protocol:
    """Validate a protocol JSON strictly; unknown keys and bad values raise ValueError."""

    value = json.loads(raw)
    keys = {"schema_version", "protocol_id", "phase", "instances", "event_types", "rules",
            "seeds", "timing_repetitions"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"protocol must contain exactly {sorted(keys)}")
    if value["schema_version"] != 1 or value["phase"] != "Phase 2A":
        raise ValueError("unsupported protocol schema or phase")
    if not isinstance(value["protocol_id"], str) or not _IDENTIFIER.match(value["protocol_id"]):
        raise ValueError("protocol_id must be a short lowercase identifier")
    instances = []
    for item in value["instances"]:
        if not isinstance(item, dict) or set(item) != {"id", "path"}:
            raise ValueError("each instance needs exactly id and path")
        if not isinstance(item["id"], str) or not _IDENTIFIER.match(item["id"]):
            raise ValueError("instance id must be a short lowercase identifier")
        path = item["path"]
        if (not isinstance(path, str) or not path or Path(path).is_absolute() or PureWindowsPath(path).drive
                or "\\" in path or ".." in Path(path).parts):
            raise ValueError("instance paths must be portable project-relative paths")
        instances.append((item["id"], path))
    _unique([i for i, _ in instances], "instance ids")
    _unique([p for _, p in instances], "instance paths")
    event_types = _unique(value["event_types"], "event_types")
    rules = _unique(value["rules"], "rules")
    seeds = _unique(value["seeds"], "seeds")
    if not set(event_types) <= set(EVENT_TYPES) or not set(rules) <= set(RULES):
        raise ValueError("unsupported event type or rule")
    if any(type(seed) is not int or not 0 <= seed < 2**32 for seed in seeds):
        raise ValueError("seeds must be integers in [0, 2**32)")
    repetitions = value["timing_repetitions"]
    if type(repetitions) is not int or not 1 <= repetitions <= 10:
        raise ValueError("timing_repetitions must be an integer in 1..10")
    return Protocol(value["protocol_id"], tuple(instances), event_types, rules, seeds, repetitions)


@dataclass(frozen=True)
class DynamicCase:
    initial: ScheduleResult
    state: DynamicFJSPState
    frozen: tuple[ScheduleRecord, ...]
    event_spec: dict


def build_case(instance: FJSPInstance, event_type: str, seed: int) -> DynamicCase:
    """Derive one reproducible single-event case from the FIFO initial schedule."""

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
