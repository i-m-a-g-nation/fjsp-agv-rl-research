"""Phase 2A: events, frozen snapshots, rescheduling and the dynamic checker."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from fjsp_lab.dynamic import (
    DynamicFJSPState, JobArrival, MachineBreakdown, MachineRepair, ProcessingTimeChange, apply_events,
    check_dynamic_feasibility, event_from_spec, frozen_records_at_time, load_event_specs_json, replay_events,
    reschedule_from_state,
)
from fjsp_lab.dynamic.perturbation import build_case, parse_protocol
from fjsp_lab.fjsp import FJSPInstance, check_feasibility, create_toy_instance, load_project_benchmark_file

ROOT = Path(__file__).resolve().parents[1]


def both_checks(result, state, frozen=()):
    static_ok, static_issues = check_feasibility(result, expected_instance=state.instance)
    dynamic_ok, dynamic_issues = check_dynamic_feasibility(result, state, frozen)
    assert static_ok is True and dynamic_ok is True, (static_issues, dynamic_issues)


@pytest.mark.parametrize('spec', [
    {'type': 'machine_breakdown', 'time': 2, 'machine_id': 0, 'repair_time': 1},
    {'type': 'machine_breakdown', 'time': -1, 'machine_id': 0, 'repair_time': 3},
    {'type': 'machine_repair', 'time': 2, 'machine_id': True},
    {'type': 'job_arrival', 'time': 2, 'operations': []},
    {'type': 'processing_time_change', 'time': 1, 'job_id': 0, 'op_id': 0, 'machine_id': 0, 'new_processing_time': 0},
    {'type': 'teleport', 'time': 1},
])
def test_invalid_event_specs_are_rejected(spec):
    with pytest.raises(ValueError):
        event_from_spec(spec)


def test_state_transitions_are_pure():
    base = DynamicFJSPState.from_instance(create_toy_instance())
    down = base.apply_event(MachineBreakdown(time=2, machine_id=1, repair_time=9))
    assert base.machine_unavailable_until == (0, 0, 0) and down.machine_unavailable_until == (0, 9, 0)
    assert down.apply_event(MachineRepair(time=4, machine_id=1)).machine_unavailable_until == (0, 4, 0)
    arrived = down.apply_event(JobArrival(time=5, operations=(((0, 2),),)))
    assert arrived.instance.num_jobs == 4 and arrived.job_release_times[-1] == 5
    changed = base.apply_event(ProcessingTimeChange(time=1, job_id=0, op_id=0, machine_id=1, new_processing_time=9))
    assert changed.instance.get_processing_time(0, 0, 1) == 9 and base.instance.get_processing_time(0, 0, 1) == 5
    with pytest.raises(ValueError):
        down.apply_event(MachineRepair(time=1, machine_id=1))       # earlier than current time
    with pytest.raises(ValueError):
        apply_events(base, [MachineRepair(time=3, machine_id=0), MachineRepair(time=2, machine_id=0)])


def test_frozen_snapshot_keeps_completed_and_running_operations():
    initial = reschedule_from_state(DynamicFJSPState.from_instance(create_toy_instance()), rule='fifo')
    time = 4
    frozen = frozen_records_at_time(initial, time)
    assert frozen and all(r.start < time for r in frozen)
    assert {(r.job_id, r.op_id) for r in initial.records if r.start < time} == {(r.job_id, r.op_id) for r in frozen}


@pytest.mark.parametrize('rule', ['fifo', 'spt', 'eft'])
def test_reschedule_respects_frozen_records_downtime_and_releases(rule):
    instance = create_toy_instance()
    initial = reschedule_from_state(DynamicFJSPState.from_instance(instance), rule='fifo')
    frozen = tuple(frozen_records_at_time(initial, 3))
    state = DynamicFJSPState.from_instance(instance, current_time=3).apply_event(
        MachineBreakdown(time=3, machine_id=1, repair_time=10))
    state = state.apply_event(JobArrival(time=4, operations=(((1, 2), (2, 3)),)))
    result = reschedule_from_state(state, frozen, rule=rule)
    both_checks(result, state, frozen)
    assert all(r.start >= 10 for r in result.records if r.machine_id == 1 and r not in frozen)
    assert all(r.start >= 4 for r in result.records if r.job_id == 3)


def test_dynamic_checker_rejects_violations():
    instance = create_toy_instance()
    initial = reschedule_from_state(DynamicFJSPState.from_instance(instance), rule='fifo')
    frozen = tuple(frozen_records_at_time(initial, 3))
    state = DynamicFJSPState.from_instance(instance, current_time=3).apply_event(
        MachineBreakdown(time=3, machine_id=2, repair_time=50))
    result = reschedule_from_state(state, frozen)
    moved = replace(frozen[0], start=frozen[0].start + 1, end=frozen[0].end + 1)
    tampered = replace(result, records=[moved if (r.job_id, r.op_id) == (moved.job_id, moved.op_id) else r
                                        for r in result.records])
    ok, issues = check_dynamic_feasibility(tampered, state, frozen)
    assert not ok and 'FROZEN_RECORD_CHANGED' in {i.code for i in issues}
    late = next(r for r in result.records if r not in frozen)
    early = replace(late, machine_id=2, start=3, end=3 + late.processing_time)
    tampered = replace(result, records=[early if r is late else r for r in result.records])
    ok, issues = check_dynamic_feasibility(tampered, state, frozen)
    assert not ok and 'MACHINE_UNAVAILABLE' in {i.code for i in issues}


@pytest.mark.parametrize('name, jobs, time, frozen_end', [
    ('multi_event', [[[(0, 2)], [(0, 3), (1, 4)]]], 2, 2),
    ('repair_cycle', [[[(0, 2)], [(0, 3), (1, 4)]]], 0, None),
    ('release_stagger', [[[(0, 2), (1, 3)]]], 0, None),
])
@pytest.mark.parametrize('rule', ['fifo', 'spt', 'eft'])
def test_event_files_reschedule_to_feasible_plans(name, jobs, time, frozen_end, rule):
    instance = FJSPInstance.from_jobs_array(jobs, num_machines=2)
    frozen = ()
    if frozen_end is not None:
        initial = reschedule_from_state(DynamicFJSPState.from_instance(instance), rule='fifo')
        frozen = tuple(frozen_records_at_time(initial, frozen_end))
    events = load_event_specs_json(ROOT / f'experiments/inputs/dynamic_events_{name}.json')
    state = apply_events(DynamicFJSPState.from_instance(instance, current_time=time), events)
    both_checks(reschedule_from_state(state, frozen, rule=rule), state, frozen)


def test_sequential_replay_freezes_each_prefix():
    instance = FJSPInstance.from_jobs_array([[[(0, 3)], [(1, 4)], [(0, 2)]]], num_machines=2)
    events = [MachineBreakdown(time=1, machine_id=1, repair_time=5), JobArrival(time=4, operations=(((0, 2),),)),
              ProcessingTimeChange(time=6, job_id=0, op_id=2, machine_id=0, new_processing_time=4)]
    episode = replay_events(instance, events)
    assert episode.final_result is not None, episode.error
    assert [step.time for step in episode.steps] == [1, 4, 6]
    for step in episode.steps:
        both_checks(step.result, step.state, step.frozen_records)


def test_replay_reports_failure_instead_of_returning_a_plan():
    instance = FJSPInstance.from_jobs_array([[[(0, 5)], [(0, 2)]]])
    episode = replay_events(instance, [ProcessingTimeChange(time=2, job_id=0, op_id=0, machine_id=0,
                                                            new_processing_time=7)])
    assert episode.final_result is None and 'frozen' in episode.error


def test_protocol_cases_reschedule_feasibly():
    protocol = parse_protocol((ROOT / 'experiments/inputs/phase2a_v1.json').read_bytes())
    assert protocol.expected_runs == 243
    instance = load_project_benchmark_file(ROOT / protocol.instances[1][1])
    for event_type in protocol.event_types:
        case = build_case(instance, event_type, protocol.seeds[0])
        for rule in protocol.rules:
            both_checks(reschedule_from_state(case.state, case.frozen, rule=rule), case.state, case.frozen)


def test_protocol_parser_is_strict():
    good = json.loads((ROOT / 'experiments/inputs/phase2a_v1.json').read_text(encoding='utf-8'))
    for change in ({'rules': ['fifo', 'fifo']}, {'extra': 1}, {'seeds': [True]},
                   {'instances': [{'id': 'x', 'path': '../x.fjs'}]}):
        with pytest.raises(ValueError):
            parse_protocol(json.dumps({**good, **change}).encode('utf-8'))
