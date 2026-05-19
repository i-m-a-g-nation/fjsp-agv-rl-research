from src.data.instance import FJSPInstance, create_toy_instance
from src.scheduling.decoding import decode_schedule
from src.scheduling.encoding import ScheduleRecord, ScheduleResult
from src.scheduling.feasibility import check_feasibility, Violation


def _make_schedule(instance, assignment):
    return decode_schedule(assignment, instance)


class TestFeasibilityChecker:

    def test_valid_schedule_passes(self):
        instance = create_toy_instance()
        assignment = [
            (0, 0, 0), (0, 1, 1),
            (1, 0, 0), (1, 1, 1),
            (2, 0, 0), (2, 1, 2), (2, 2, 1),
        ]
        result = _make_schedule(instance, assignment)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"

    def test_missing_op_detected(self):
        instance = create_toy_instance()
        assignment = [
            (0, 0, 0), (0, 1, 1),
            (1, 0, 0), (1, 1, 1),
            (2, 0, 0), (2, 1, 2),
        ]
        result = _make_schedule(instance, assignment)
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("MISSING_OP" in v.code for v in violations)

    def test_duplicate_op_detected(self):
        instance = create_toy_instance()
        assignment = [
            (0, 0, 0), (0, 1, 1),
            (1, 0, 0), (1, 1, 1),
            (2, 0, 0), (2, 1, 2),
            (2, 2, 1), (2, 2, 1),
        ]
        result = _make_schedule(instance, assignment)
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("DUPLICATE_OP" in v.code for v in violations)

    def test_machine_overlap_detected(self):
        instance = create_toy_instance()
        result = ScheduleResult(instance=instance)
        result.add_record(0, 0, 0, start=0, processing_time=5)
        result.add_record(1, 0, 0, start=3, processing_time=5)
        result.compute_makespan()
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("MACHINE_OVERLAP" in v.code for v in violations)

    def test_precedence_violation_detected(self):
        instance = create_toy_instance()
        result = ScheduleResult(instance=instance)
        result.add_record(0, 0, 0, start=5, processing_time=3)
        result.add_record(0, 1, 1, start=4, processing_time=4)
        result.compute_makespan()
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("PRECEDENCE_VIOLATION" in v.code for v in violations)

    def test_machine_ineligible_detected(self):
        instance = create_toy_instance()
        result = ScheduleResult(instance=instance)
        result.add_record(0, 0, 99, start=0, processing_time=3)
        result.compute_makespan()
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any(
            v.code in ("MACHINE_INELIGIBLE", "INVALID_MACHINE_ID")
            for v in violations
        )

    def test_pt_instance_mismatch_detected(self):
        instance = create_toy_instance()
        result = ScheduleResult(instance=instance)
        result.add_record(0, 0, 0, start=0, processing_time=99)
        result.compute_makespan()
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("PT_INSTANCE_MISMATCH" in v.code for v in violations)

    def test_makespan_mismatch_detected(self):
        instance = create_toy_instance()
        result = ScheduleResult(instance=instance)
        result.add_record(0, 0, 0, start=0, processing_time=3)
        result.makespan = 999
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("MAKESPAN_MISMATCH" in v.code for v in violations)

    def test_no_instance_reference(self):
        result = ScheduleResult()
        result.add_record(0, 0, 0, start=0, processing_time=3)
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("NO_INSTANCE" in v.code for v in violations)

    def test_empty_records(self):
        instance = create_toy_instance()
        result = ScheduleResult(instance=instance)
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("NO_RECORDS" in v.code for v in violations)


class TestFeasibilityCheckerRobustness:

    @staticmethod
    def _toy() -> FJSPInstance:
        return create_toy_instance()

    def test_invalid_job_id_does_not_crash(self):
        instance = self._toy()
        result = ScheduleResult(instance=instance)
        result.add_record(99, 0, 0, start=0, processing_time=3)
        result.compute_makespan()
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("INVALID_JOB_ID" in v.code for v in violations)

    def test_negative_job_id_does_not_crash(self):
        instance = self._toy()
        result = ScheduleResult(instance=instance)
        result.add_record(-1, 0, 0, start=0, processing_time=3)
        result.compute_makespan()
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("INVALID_JOB_ID" in v.code for v in violations)

    def test_invalid_op_id_does_not_crash(self):
        instance = self._toy()
        result = ScheduleResult(instance=instance)
        result.add_record(0, 99, 0, start=0, processing_time=3)
        result.compute_makespan()
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("INVALID_OP_ID" in v.code for v in violations)

    def test_invalid_op_id_does_not_crash_edge(self):
        instance = self._toy()
        result = ScheduleResult(instance=instance)
        result.add_record(1, -1, 1, start=0, processing_time=3)
        result.compute_makespan()
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("INVALID_OP_ID" in v.code for v in violations)

    def test_negative_start_rejected(self):
        instance = self._toy()
        result = ScheduleResult(instance=instance)
        result.add_record(0, 0, 0, start=-5, processing_time=3)
        result.compute_makespan()
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("INVALID_TIME" in v.code for v in violations)

    def test_zero_processing_time_rejected(self):
        instance = self._toy()
        result = ScheduleResult(instance=instance)
        result.add_record(0, 0, 0, start=0, processing_time=0)
        result.compute_makespan()
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("INVALID_TIME" in v.code for v in violations)

    def test_negative_processing_time_rejected(self):
        instance = self._toy()
        result = ScheduleResult(instance=instance)
        result.add_record(0, 0, 0, start=0, processing_time=-3)
        result.compute_makespan()
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("INVALID_TIME" in v.code for v in violations)

    def test_end_less_than_start_rejected(self):
        instance = self._toy()
        result = ScheduleResult(instance=instance)
        rec = ScheduleRecord(
            job_id=0, op_id=0, machine_id=0,
            start=10, end=5, processing_time=3,
        )
        result.records.append(rec)
        result.compute_makespan()
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("INVALID_TIME" in v.code for v in violations)

    def test_invalid_machine_id_detected(self):
        instance = self._toy()
        result = ScheduleResult(instance=instance)
        result.add_record(0, 0, -1, start=0, processing_time=3)
        result.compute_makespan()
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("INVALID_MACHINE_ID" in v.code for v in violations)

    def test_invalid_machine_id_out_of_range(self):
        instance = self._toy()
        result = ScheduleResult(instance=instance)
        result.add_record(0, 0, 100, start=0, processing_time=3)
        result.compute_makespan()
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("INVALID_MACHINE_ID" in v.code for v in violations)

    def test_multiple_invalid_fields_collected(self):
        instance = self._toy()
        result = ScheduleResult(instance=instance)
        result.add_record(99, 99, -1, start=-5, processing_time=-3)
        result.compute_makespan()
        feasible, violations = check_feasibility(result)
        assert not feasible
        codes = {v.code for v in violations}
        assert "INVALID_JOB_ID" in codes
        assert "INVALID_TIME" in codes
        assert "INVALID_MACHINE_ID" in codes
