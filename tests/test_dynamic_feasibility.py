from src.data.instance import FJSPInstance
from src.dynamic import (
    DynamicFJSPState,
    JobArrival,
    MachineBreakdown,
    check_dynamic_feasibility,
)
from src.scheduling.encoding import ScheduleRecord, ScheduleResult


def _single_record_result(instance, record):
    result = ScheduleResult(instance=instance)
    result.records.append(record)
    result.compute_makespan()
    return result


def test_dynamic_feasibility_accepts_reschedule_that_respects_state():
    instance = FJSPInstance.from_jobs_array([
        [[(0, 3)]],
    ])
    state = DynamicFJSPState.from_instance(instance, current_time=0)
    result = _single_record_result(
        instance,
        ScheduleRecord(0, 0, 0, start=0, end=3, processing_time=3),
    )

    feasible, violations = check_dynamic_feasibility(result, state)

    assert feasible, violations


def test_dynamic_feasibility_rejects_changed_frozen_record():
    instance = FJSPInstance.from_jobs_array([
        [[(0, 3)]],
    ])
    state = DynamicFJSPState.from_instance(instance, current_time=3)
    frozen = [ScheduleRecord(0, 0, 0, start=0, end=3, processing_time=3)]
    result = _single_record_result(
        instance,
        ScheduleRecord(0, 0, 0, start=1, end=4, processing_time=3),
    )

    feasible, violations = check_dynamic_feasibility(result, state, frozen)

    assert not feasible
    assert violations[0].code == "FROZEN_RECORD_CHANGED"


def test_dynamic_feasibility_rejects_job_before_release_time():
    instance = FJSPInstance.from_jobs_array([
        [[(0, 2)]],
    ])
    state = DynamicFJSPState.from_instance(instance, current_time=5)
    state = state.apply_event(JobArrival(time=5, operations=(((0, 3),),)))
    result = ScheduleResult(instance=state.instance)
    result.add_record(0, 0, 0, start=5, processing_time=2)
    result.add_record(1, 0, 0, start=3, processing_time=3)
    result.compute_makespan()

    feasible, violations = check_dynamic_feasibility(result, state)

    assert not feasible
    assert any(violation.code == "JOB_BEFORE_RELEASE" for violation in violations)


def test_dynamic_feasibility_rejects_start_during_machine_unavailability():
    instance = FJSPInstance.from_jobs_array([
        [[(0, 4)]],
    ])
    state = DynamicFJSPState.from_instance(instance, current_time=0)
    state = state.apply_event(MachineBreakdown(time=0, machine_id=0, repair_time=10))
    result = _single_record_result(
        instance,
        ScheduleRecord(0, 0, 0, start=5, end=9, processing_time=4),
    )

    feasible, violations = check_dynamic_feasibility(result, state)

    assert not feasible
    assert violations[0].code == "MACHINE_UNAVAILABLE"


def test_dynamic_feasibility_allows_frozen_record_inside_past_breakdown_window():
    instance = FJSPInstance.from_jobs_array([
        [[(0, 4)]],
    ])
    state = DynamicFJSPState.from_instance(instance, current_time=2)
    state = state.apply_event(MachineBreakdown(time=2, machine_id=0, repair_time=10))
    frozen = [ScheduleRecord(0, 0, 0, start=0, end=4, processing_time=4)]
    result = _single_record_result(instance, frozen[0])

    feasible, violations = check_dynamic_feasibility(result, state, frozen)

    assert feasible, violations
