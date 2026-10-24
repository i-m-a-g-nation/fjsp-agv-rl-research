from dataclasses import asdict

import pytest

from src.data.instance import FJSPInstance
from src.dynamic import JobArrival, MachineBreakdown, MachineRepair, ProcessingTimeChange
from src.scheduling.feasibility import check_feasibility


def history(record):
    return record.job_id, record.op_id, record.machine_id, record.start, record.end, record.processing_time


@pytest.mark.parametrize('rule', ['fifo', 'spt', 'eft'])
def test_later_repair_does_not_change_earlier_dispatch(rule):
    from src.dynamic.rolling import replay_events
    instance = FJSPInstance.from_jobs_array([[[(0, 4)]]])
    events = [MachineBreakdown(time=0, machine_id=0, repair_time=20), MachineRepair(time=5, machine_id=0)]
    result = replay_events(instance, events, rule=rule)
    assert result.error == ''
    assert [(s.time, s.result.records[0].start, s.result.makespan) for s in result.steps] == [(0, 20, 24), (5, 5, 9)]
    assert result.final_result.makespan == 9
    prefix = replay_events(instance, events[:1], rule=rule)
    assert [history(r) for r in prefix.final_result.records] == [history(r) for r in result.steps[0].result.records]


@pytest.mark.parametrize('rule', ['fifo', 'spt', 'eft'])
def test_each_event_freezes_the_previous_reschedule_including_new_job_history(rule):
    from src.dynamic.rolling import replay_events
    instance = FJSPInstance.from_jobs_array([[[(0, 3)], [(1, 4)], [(0, 2)]]], num_machines=2)
    result = replay_events(instance, [
        MachineBreakdown(time=1, machine_id=1, repair_time=5),
        JobArrival(time=4, operations=(((0, 2),),)),
        ProcessingTimeChange(time=6, job_id=0, op_id=2, machine_id=0, new_processing_time=4),
    ], rule=rule)
    assert result.error == ''
    assert [s.result.makespan for s in result.steps] == [11, 11, 13]
    assert {history(r) for r in result.steps[2].frozen_records} == {
        (0, 0, 0, 0, 3, 3), (0, 1, 1, 5, 9, 4), (1, 0, 0, 4, 6, 2)}
    assert result.final_result.makespan == 13
    assert result.steps[0].result.instance.get_processing_time(0, 2, 0) == 2
    assert result.final_result.instance.get_processing_time(0, 2, 0) == 4
    assert all(check_feasibility(step.result)[0] for step in result.steps)


def test_simultaneous_events_are_applied_before_one_dispatch():
    from src.dynamic.rolling import replay_events
    instance = FJSPInstance.from_jobs_array([[[(0, 3)], [(0, 2)]]])
    result = replay_events(instance, [
        MachineBreakdown(time=0, machine_id=0, repair_time=2),
        ProcessingTimeChange(time=0, job_id=0, op_id=0, machine_id=0, new_processing_time=7),
        JobArrival(time=0, operations=(((0, 1),),)),
    ])
    assert len(result.steps) == 1
    assert len(result.steps[0].events) == 3
    assert result.steps[0].frozen_records == ()
    assert result.final_result.makespan == 12
    assert min(r.start for r in result.final_result.records) == 2


@pytest.mark.parametrize('bad_event', [
    ProcessingTimeChange(time=1, job_id=0, op_id=0, machine_id=0, new_processing_time=8),
    MachineBreakdown(time=1, machine_id=0, repair_time=8),
])
def test_unsupported_busy_operation_change_fails_without_an_accepted_final_result(bad_event):
    from src.dynamic.rolling import replay_events
    instance = FJSPInstance.from_jobs_array([[[(0, 3)], [(0, 2)]]])
    result = replay_events(instance, [bad_event, JobArrival(time=9, operations=(((0, 1),),))])
    assert result.error
    assert result.final_result is None
    assert result.steps == ()
    assert result.failed_events == (bad_event,)


def test_failed_later_batch_retains_successful_prefix_but_not_a_final_schedule():
    from src.dynamic.rolling import replay_events
    instance = FJSPInstance.from_jobs_array([[[(0, 4)]]])
    result = replay_events(instance, [
        MachineBreakdown(time=0, machine_id=0, repair_time=20),
        MachineRepair(time=5, machine_id=0),
        ProcessingTimeChange(time=6, job_id=0, op_id=0, machine_id=0, new_processing_time=8),
    ])
    assert len(result.steps) == 2
    assert result.steps[-1].result.makespan == 9
    assert result.final_result is None
    assert result.error
    assert len(result.failed_events) == 1


def test_invalid_order_and_unknown_rule_are_configuration_errors():
    from src.dynamic.rolling import replay_events
    instance = FJSPInstance.from_jobs_array([[[(0, 4)]]])
    with pytest.raises(ValueError, match='order'):
        replay_events(instance, [MachineRepair(time=5, machine_id=0), MachineRepair(time=4, machine_id=0)])
    with pytest.raises(ValueError, match='rule'):
        replay_events(instance, [], rule='ppo')


def test_empty_stream_returns_a_validated_initial_schedule():
    from src.dynamic.rolling import replay_events
    instance = FJSPInstance.from_jobs_array([[[(0, 4)]]])
    result = replay_events(instance, [])
    assert result.error == '' and result.final_result.makespan == 4
    assert result.steps == ()
    assert asdict(result.final_result.records[0]) == {'job_id': 0, 'op_id': 0, 'machine_id': 0, 'start': 0, 'end': 4, 'processing_time': 4}


@pytest.mark.parametrize('corruption', ['static', 'dynamic', 'instance'])
def test_replay_independently_rejects_corrupt_solver_results(monkeypatch, corruption):
    from src.dynamic import rolling
    original = rolling.reschedule_from_state
    calls = []
    def corrupt(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(True)
        if len(calls) == 2:
            if corruption == 'static':
                result.records[0].end += 1
            elif corruption == 'dynamic':
                for record in result.records:
                    record.start += 1
                    record.end += 1
                result.compute_makespan()
            else:
                result.instance = FJSPInstance.from_jobs_array([[[(0, 9)]]])
        return result
    monkeypatch.setattr(rolling, 'reschedule_from_state', corrupt)
    result = rolling.replay_events(FJSPInstance.from_jobs_array([[[(0, 4)]]]),
                                   [JobArrival(time=1, operations=(((0, 1),),))])
    expected = {'static': 'Static feasibility', 'dynamic': 'Dynamic feasibility', 'instance': 'wrong instance'}[corruption]
    assert expected in result.error
    assert result.final_result is None and result.steps == ()
