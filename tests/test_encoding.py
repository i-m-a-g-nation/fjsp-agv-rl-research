from src.data.instance import create_toy_instance
from src.scheduling.encoding import ScheduleRecord, ScheduleResult


class TestScheduleRecord:

    def test_create_record(self):
        rec = ScheduleRecord(
            job_id=0, op_id=0, machine_id=1,
            start=0, end=5, processing_time=5,
        )
        assert rec.job_id == 0
        assert rec.op_id == 0
        assert rec.machine_id == 1
        assert rec.start == 0
        assert rec.end == 5
        assert rec.processing_time == 5


class TestScheduleResult:

    def test_add_record(self):
        instance = create_toy_instance()
        result = ScheduleResult(instance=instance)
        rec = result.add_record(0, 0, 0, start=0, processing_time=3)
        assert rec.start == 0
        assert rec.end == 3
        assert len(result.records) == 1

    def test_compute_makespan(self):
        instance = create_toy_instance()
        result = ScheduleResult(instance=instance)
        result.add_record(0, 0, 0, start=0, processing_time=3)
        result.add_record(0, 1, 1, start=3, processing_time=4)
        result.compute_makespan()
        assert result.makespan == 7

    def test_empty_makespan(self):
        result = ScheduleResult()
        assert result.compute_makespan() == 0

    def test_sorted_records(self):
        instance = create_toy_instance()
        result = ScheduleResult(instance=instance)
        result.add_record(1, 0, 0, start=0, processing_time=2)
        result.add_record(0, 0, 0, start=0, processing_time=3)
        sorted_recs = result.sorted_records()
        assert sorted_recs[0].job_id == 0
        assert sorted_recs[1].job_id == 1
