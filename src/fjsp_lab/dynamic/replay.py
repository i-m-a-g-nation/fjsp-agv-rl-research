"""Sequential event replay using the existing non-preemptive Phase 2A model."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import groupby
from typing import Iterable

from fjsp_lab.fjsp.instance import FJSPInstance
from fjsp_lab.dynamic.events import DynamicEvent, JobArrival, MachineBreakdown, MachineRepair, ProcessingTimeChange
from fjsp_lab.dynamic.feasibility import check_dynamic_feasibility
from fjsp_lab.dynamic.reschedule import RescheduleRule, reschedule_from_state
from fjsp_lab.dynamic.snapshot import frozen_records_at_time
from fjsp_lab.dynamic.state import DynamicFJSPState
from fjsp_lab.fjsp.schedule import ScheduleRecord, ScheduleResult
from fjsp_lab.fjsp.feasibility import check_feasibility


@dataclass(frozen=True)
class ReplayStep:
    time: int
    events: tuple[DynamicEvent, ...]
    state: DynamicFJSPState
    frozen_records: tuple[ScheduleRecord, ...]
    result: ScheduleResult


@dataclass(frozen=True)
class ReplayEpisode:
    initial: ScheduleResult
    steps: tuple[ReplayStep, ...]
    final_result: ScheduleResult | None
    failed_events: tuple[DynamicEvent, ...] = ()
    error: str = ''


def _validate_result(result, state, frozen):
    if result.instance != state.instance:
        raise ValueError('Returned schedule has the wrong instance')
    valid, issues = check_feasibility(result)
    if not valid:
        raise ValueError(f'Static feasibility failed: {issues}')
    valid, issues = check_dynamic_feasibility(result, state, frozen)
    if not valid:
        raise ValueError(f'Dynamic feasibility failed: {issues}')


def replay_events(instance: FJSPInstance, events: Iterable[DynamicEvent],
                  rule: RescheduleRule = 'eft') -> ReplayEpisode:
    """Replay isolated timestamp batches, freezing the preceding actual plan.

    A failed episode has no accepted final result. Its successful prefix is
    diagnostic evidence only. Equal-time events precede dispatch and preserve
    their supplied order. No future event is passed to the dispatch rule.
    """
    if rule not in ('fifo', 'spt', 'eft'):
        raise ValueError(f'Unsupported replay rule: {rule}')
    events = tuple(events)
    supported = (JobArrival, MachineBreakdown, MachineRepair, ProcessingTimeChange)
    if any(not isinstance(event, supported) or type(event.time) is not int or event.time < 0 for event in events):
        raise ValueError('Replay events must have supported types and nonnegative integer times')
    if any(left.time > right.time for left, right in zip(events, events[1:])):
        raise ValueError('Event order must be nondecreasing')
    state = DynamicFJSPState.from_instance(instance)
    initial = reschedule_from_state(state, rule='fifo')
    _validate_result(initial, state, ())
    current, steps = initial, []
    for timestamp, grouped in groupby(events, key=lambda event: event.time):
        batch = tuple(grouped)
        frozen = tuple(frozen_records_at_time(current, timestamp))
        frozen_keys = {(record.job_id, record.op_id) for record in frozen}
        try:
            candidate_state = state
            for event in batch:
                if isinstance(event, ProcessingTimeChange) and (event.job_id, event.op_id) in frozen_keys:
                    raise ValueError('Cannot change the processing time of a frozen operation')
                if isinstance(event, MachineBreakdown) and any(
                    record.machine_id == event.machine_id and record.start < timestamp < record.end for record in frozen
                ):
                    raise ValueError('Idle-only breakdown cannot target an in-process machine')
                candidate_state = candidate_state.apply_event(event)
            result = reschedule_from_state(candidate_state, frozen, rule=rule)
            _validate_result(result, candidate_state, frozen)
        except Exception as exc:
            return ReplayEpisode(initial, tuple(steps), None, batch, f'{type(exc).__name__}: {str(exc)[:500]}')
        steps.append(ReplayStep(timestamp, batch, candidate_state, frozen, result))
        state, current = candidate_state, result
    return ReplayEpisode(initial, tuple(steps), current)
