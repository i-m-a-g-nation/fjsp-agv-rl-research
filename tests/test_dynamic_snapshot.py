import pytest

from src.data.instance import FJSPInstance
from src.dynamic import frozen_records_at_time
from src.scheduling.encoding import ScheduleResult


def _snapshot_schedule():
    instance = FJSPInstance.from_jobs_array([
        [[(0, 3)], [(0, 4)]],
        [[(1, 5)]],
    ], num_machines=2)
    schedule = ScheduleResult(instance=instance)
    schedule.add_record(0, 0, 0, start=0, processing_time=3)
    schedule.add_record(0, 1, 0, start=3, processing_time=4)
    schedule.add_record(1, 0, 1, start=8, processing_time=5)
    schedule.compute_makespan()
    return schedule


def test_frozen_records_at_time_includes_completed_and_in_process_by_default():
    schedule = _snapshot_schedule()

    frozen = frozen_records_at_time(schedule, current_time=5)

    assert [(record.job_id, record.op_id) for record in frozen] == [(0, 0), (0, 1)]


def test_frozen_records_at_time_can_exclude_in_process_records():
    schedule = _snapshot_schedule()

    frozen = frozen_records_at_time(
        schedule,
        current_time=5,
        include_in_process=False,
    )

    assert [(record.job_id, record.op_id) for record in frozen] == [(0, 0)]


def test_frozen_records_at_time_returns_copies():
    schedule = _snapshot_schedule()

    frozen = frozen_records_at_time(schedule, current_time=5)

    assert frozen[0] is not schedule.records[0]
    assert frozen[0] == schedule.records[0]


def test_frozen_records_at_time_rejects_negative_time():
    with pytest.raises(ValueError, match="non-negative"):
        frozen_records_at_time(_snapshot_schedule(), current_time=-1)
