import pytest

from src.data.instance import FJSPInstance, create_toy_instance
from src.dynamic import (
    DynamicFJSPState,
    JobArrival,
    MachineBreakdown,
    MachineRepair,
    ProcessingTimeChange,
    apply_events,
    check_dynamic_feasibility,
    reschedule_from_state,
)
from src.scheduling.encoding import ScheduleRecord
from src.scheduling.feasibility import check_feasibility


def test_machine_breakdown_delays_future_operation_until_repair():
    instance = FJSPInstance.from_jobs_array([
        [[(0, 3)], [(0, 2)]],
    ])
    state = DynamicFJSPState.from_instance(instance, current_time=3)
    state = state.apply_event(MachineBreakdown(time=3, machine_id=0, repair_time=10))
    frozen = [
        ScheduleRecord(
            job_id=0,
            op_id=0,
            machine_id=0,
            start=0,
            end=3,
            processing_time=3,
        )
    ]

    result = reschedule_from_state(state, frozen, rule="eft")

    op1 = next(record for record in result.records if (record.job_id, record.op_id) == (0, 1))
    assert op1.start == 10
    feasible, violations = check_feasibility(result)
    assert feasible, violations
    dynamic_feasible, dynamic_violations = check_dynamic_feasibility(result, state, frozen)
    assert dynamic_feasible, dynamic_violations


def test_machine_repair_clears_future_unavailability_at_event_time():
    instance = FJSPInstance.from_jobs_array([
        [[(0, 4)]],
    ])
    state = DynamicFJSPState.from_instance(instance, current_time=0)
    state = state.apply_event(MachineBreakdown(time=0, machine_id=0, repair_time=20))
    state = state.apply_event(MachineRepair(time=5, machine_id=0))

    result = reschedule_from_state(state, rule="eft")

    assert result.records[0].start == 5
    feasible, violations = check_feasibility(result)
    assert feasible, violations
    dynamic_feasible, dynamic_violations = check_dynamic_feasibility(result, state)
    assert dynamic_feasible, dynamic_violations


def test_job_arrival_appends_new_job_and_reschedule_includes_it():
    instance = FJSPInstance.from_jobs_array([
        [[(0, 2)]],
    ])
    state = DynamicFJSPState.from_instance(instance, current_time=5)
    state = state.apply_event(JobArrival(time=5, operations=(((0, 3),),)))

    result = reschedule_from_state(state, rule="eft")

    assert state.instance.num_jobs == 2
    assert {(record.job_id, record.op_id) for record in result.records} == {
        (0, 0),
        (1, 0),
    }
    assert min(record.start for record in result.records) == 5
    feasible, violations = check_feasibility(result)
    assert feasible, violations


def test_processing_time_change_updates_future_reschedule_duration():
    instance = FJSPInstance.from_jobs_array([
        [[(0, 2), (1, 4)]],
    ])
    state = DynamicFJSPState.from_instance(instance, current_time=0)
    state = state.apply_event(
        ProcessingTimeChange(
            time=0,
            job_id=0,
            op_id=0,
            machine_id=0,
            new_processing_time=6,
        )
    )

    result = reschedule_from_state(state, rule="spt")

    # SPT now prefers machine 1 because machine 0 was changed from 2 to 6.
    record = result.records[0]
    assert record.machine_id == 1
    assert record.processing_time == 4
    feasible, violations = check_feasibility(result)
    assert feasible, violations


def test_multi_event_sequence_reschedules_with_release_and_unavailability():
    instance = FJSPInstance.from_jobs_array([
        [[(0, 2)], [(0, 3), (1, 4)]],
    ], num_machines=2)
    state = DynamicFJSPState.from_instance(instance, current_time=2)
    frozen = [ScheduleRecord(0, 0, 0, start=0, end=2, processing_time=2)]
    state = apply_events(
        state,
        [
            JobArrival(time=2, operations=(((1, 2),),)),
            MachineBreakdown(time=2, machine_id=1, repair_time=6),
            ProcessingTimeChange(
                time=2,
                job_id=0,
                op_id=1,
                machine_id=0,
                new_processing_time=5,
            ),
        ],
    )

    result = reschedule_from_state(state, frozen, rule="eft")

    assert state.instance.num_jobs == 2
    assert len(result.records) == 3
    assert all(
        record.start >= 6
        for record in result.records
        if record.machine_id == 1 and (record.job_id, record.op_id) != (0, 0)
    )
    feasible, violations = check_feasibility(result)
    assert feasible, violations
    dynamic_feasible, dynamic_violations = check_dynamic_feasibility(result, state, frozen)
    assert dynamic_feasible, dynamic_violations


def test_apply_events_rejects_out_of_order_events():
    instance = FJSPInstance.from_jobs_array([
        [[(0, 2)]],
    ])
    state = DynamicFJSPState.from_instance(instance, current_time=0)

    with pytest.raises(ValueError, match="sorted"):
        apply_events(
            state,
            [
                MachineBreakdown(time=5, machine_id=0, repair_time=8),
                JobArrival(time=4, operations=(((0, 3),),)),
            ],
        )


def test_reschedule_rejects_non_prefix_frozen_records():
    instance = create_toy_instance()
    state = DynamicFJSPState.from_instance(instance, current_time=3)
    frozen = [
        ScheduleRecord(
            job_id=0,
            op_id=1,
            machine_id=1,
            start=0,
            end=4,
            processing_time=4,
        )
    ]

    with pytest.raises(ValueError, match="route prefix"):
        reschedule_from_state(state, frozen)


def test_reschedule_rejects_unreleased_jobs_in_current_instance():
    instance = create_toy_instance()
    state = DynamicFJSPState(
        instance=instance,
        current_time=0,
        released_job_ids=frozenset({0, 1}),
    )

    with pytest.raises(ValueError, match="unreleased jobs"):
        reschedule_from_state(state)
