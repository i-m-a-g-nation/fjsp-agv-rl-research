import pytest

from src.data.instance import FJSPInstance
from src.dynamic import (
    DynamicFJSPState,
    JobArrival,
    remaining_operations_from_frozen,
)
from src.scheduling.encoding import ScheduleRecord


def test_remaining_operations_from_frozen_skips_frozen_prefix():
    instance = FJSPInstance.from_jobs_array([
        [[(0, 2)], [(0, 3)], [(1, 4)]],
        [[(1, 5)]],
    ], num_machines=2)
    state = DynamicFJSPState.from_instance(instance, current_time=2)
    frozen = [
        ScheduleRecord(0, 0, 0, start=0, end=2, processing_time=2),
    ]

    remaining = remaining_operations_from_frozen(state, frozen)

    assert [(op.job_id, op.op_id) for op in remaining] == [(0, 1), (0, 2), (1, 0)]
    assert remaining[0].machine_options == ((0, 3),)


def test_remaining_operations_include_job_release_time():
    instance = FJSPInstance.from_jobs_array([
        [[(0, 2)]],
    ])
    state = DynamicFJSPState.from_instance(instance, current_time=5)
    state = state.apply_event(JobArrival(time=5, operations=(((0, 3),),)))

    remaining = remaining_operations_from_frozen(state)

    assert [(op.job_id, op.op_id, op.release_time) for op in remaining] == [
        (0, 0, 0),
        (1, 0, 5),
    ]


def test_remaining_operations_reject_non_prefix_frozen_records():
    instance = FJSPInstance.from_jobs_array([
        [[(0, 2)], [(0, 3)]],
    ])
    state = DynamicFJSPState.from_instance(instance, current_time=3)
    frozen = [
        ScheduleRecord(0, 1, 0, start=0, end=3, processing_time=3),
    ]

    with pytest.raises(ValueError, match="route prefix"):
        remaining_operations_from_frozen(state, frozen)
