from dataclasses import replace

import pytest

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
            (2, 0, 0), (2, 1, 2), (2, 2, 1),
        ]
        result = _make_schedule(instance, assignment)
        result.records.pop()
        result.compute_makespan()
        feasible, violations = check_feasibility(result)
        assert not feasible
        assert any("MISSING_OP" in v.code for v in violations)

    def test_duplicate_op_detected(self):
        instance = create_toy_instance()
        assignment = [
            (0, 0, 0), (0, 1, 1),
            (1, 0, 0), (1, 1, 1),
            (2, 0, 0), (2, 1, 2),
            (2, 2, 1),
        ]
        result = _make_schedule(instance, assignment)
        result.records.append(replace(result.records[-1]))
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


def _single_operation_result():
    instance = FJSPInstance.from_jobs_array([[[(0, 3)]]])
    return ScheduleResult(
        records=[ScheduleRecord(0, 0, 0, 0, 3, 3)],
        makespan=3,
        instance=instance,
    )


def _assert_violation(result, code, **kwargs):
    feasible, violations = check_feasibility(result, **kwargs)
    assert feasible is False
    assert all(isinstance(violation, Violation) for violation in violations)
    assert code in {violation.code for violation in violations}


@pytest.mark.parametrize("result", [None, {}, [], "schedule", object()])
def test_malformed_result_is_reported(result):
    _assert_violation(result, "INVALID_RESULT")


@pytest.mark.parametrize("records", [None, {}, "records", 42, iter(())])
def test_malformed_records_container_is_reported(records):
    result = _single_operation_result()
    result.records = records
    _assert_violation(result, "INVALID_RECORDS")


@pytest.mark.parametrize("record", [None, {}, (0, 0, 0, 0, 3, 3), object()])
def test_malformed_record_is_reported(record):
    result = _single_operation_result()
    result.records = [record]
    _assert_violation(result, "INVALID_RECORD")


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("job_id", "INVALID_JOB_ID"),
        ("op_id", "INVALID_OP_ID"),
        ("machine_id", "INVALID_MACHINE_ID"),
        ("start", "INVALID_TIME"),
        ("end", "INVALID_TIME"),
        ("processing_time", "INVALID_TIME"),
    ],
)
@pytest.mark.parametrize("bad_value", [False, True, 0.0, 3.0, 0.5, float("nan"), float("inf"), "0", None, []])
def test_record_fields_require_python_integers(field, code, bad_value):
    result = _single_operation_result()
    setattr(result.records[0], field, bad_value)
    _assert_violation(result, code)


def test_missing_record_field_is_reported():
    result = _single_operation_result()
    del result.records[0].end
    _assert_violation(result, "INVALID_RECORD")


@pytest.mark.parametrize("makespan", [True, 3.0, float("nan"), float("inf"), "3", None, [], -1])
def test_makespan_requires_nonnegative_python_integer(makespan):
    result = _single_operation_result()
    result.makespan = makespan
    _assert_violation(result, "INVALID_MAKESPAN")


@pytest.mark.parametrize("instance", [{}, object(), "instance", FJSPInstance.__new__(FJSPInstance)])
def test_malformed_instance_is_reported(instance):
    result = _single_operation_result()
    result.instance = instance
    _assert_violation(result, "INVALID_INSTANCE")


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [("num_jobs", True), ("num_jobs", 2), ("num_machines", 0), ("jobs", None), ("jobs", ())],
)
def test_corrupted_instance_is_revalidated(field, bad_value):
    result = _single_operation_result()
    object.__setattr__(result.instance, field, bad_value)
    _assert_violation(result, "INVALID_INSTANCE")


def test_result_cannot_substitute_an_easier_instance():
    result = _single_operation_result()
    expected = FJSPInstance.from_jobs_array([[[(0, 4)]]])
    _assert_violation(result, "INSTANCE_MISMATCH", expected_instance=expected)


def test_reconstructed_equal_expected_instance_is_accepted():
    result = _single_operation_result()
    expected = FJSPInstance.from_jobs_array([[[(0, 3)]]])
    assert result.instance is not expected
    assert check_feasibility(result, expected_instance=expected) == (True, [])


def test_invalid_expected_instance_is_reported():
    _assert_violation(_single_operation_result(), "INVALID_EXPECTED_INSTANCE", expected_instance={})


def test_checking_does_not_repair_or_coerce_invalid_fields():
    result = _single_operation_result()
    result.records[0].start = 0.0
    _assert_violation(result, "INVALID_TIME")
    assert type(result.records[0].start) is float


def test_checker_accepts_valid_records_in_any_container_order():
    instance = FJSPInstance.from_jobs_array([[[(0, 2)], [(1, 3)]], [[(1, 2)]]])
    result = ScheduleResult(
        records=[ScheduleRecord(0, 1, 1, 2, 5, 3), ScheduleRecord(1, 0, 1, 0, 2, 2), ScheduleRecord(0, 0, 0, 0, 2, 2)],
        makespan=5,
        instance=instance,
    )
    assert check_feasibility(result) == (True, [])


def test_touching_machine_intervals_are_feasible():
    instance = FJSPInstance.from_jobs_array([[[(0, 2)]], [[(0, 3)]]])
    result = ScheduleResult(
        records=[ScheduleRecord(0, 0, 0, 0, 2, 2), ScheduleRecord(1, 0, 0, 2, 5, 3)],
        makespan=5,
        instance=instance,
    )
    assert check_feasibility(result) == (True, [])
