"""The static checker must accept a valid schedule and name every broken constraint."""

from dataclasses import replace

import pytest

from fjsp_lab.fjsp import FJSPInstance, ScheduleResult, check_feasibility, create_toy_instance, decode_schedule


def valid_schedule() -> ScheduleResult:
    instance = create_toy_instance()
    order = [(0, 0, 0), (1, 0, 2), (2, 0, 0), (0, 1, 1), (1, 1, 1), (2, 1, 2), (2, 2, 1)]
    return decode_schedule(order, instance)


def codes(result, **kwargs):
    passed, violations = check_feasibility(result, **kwargs)
    assert not passed
    return {v.code for v in violations}


def test_valid_schedule_passes():
    passed, violations = check_feasibility(valid_schedule(), expected_instance=create_toy_instance())
    assert passed and violations == []


def mutate(index, **changes):
    result = valid_schedule()
    result.records[index] = replace(result.records[index], **changes)
    return result


def test_missing_and_duplicate_operation():
    result = valid_schedule()
    result.records.pop()
    assert {'OP_COUNT_MISMATCH', 'MISSING_OP'} <= codes(result)
    result = valid_schedule()
    result.records[-1] = replace(result.records[0])
    assert 'DUPLICATE_OP' in codes(result)


def test_precedence_violation():
    result = valid_schedule()
    second = next(i for i, r in enumerate(result.records) if (r.job_id, r.op_id) == (0, 1))
    record = result.records[second]
    result.records[second] = replace(record, start=0, end=record.processing_time)
    result.compute_makespan()
    assert 'PRECEDENCE_VIOLATION' in codes(result)


def test_machine_overlap():
    instance = FJSPInstance.from_jobs_array([[[(0, 3)]], [[(0, 2)]]])
    result = ScheduleResult(instance=instance)
    result.add_record(0, 0, 0, 0, 3)
    result.add_record(1, 0, 0, 2, 2)
    result.compute_makespan()
    assert 'MACHINE_OVERLAP' in codes(result)


def test_ineligible_machine_and_wrong_durations():
    record = valid_schedule().records[0]          # job 0 op 0 on machine 0, p = 3
    assert 'MACHINE_INELIGIBLE' in codes(mutate(0, machine_id=2))
    assert 'PROCESSING_TIME_MISMATCH' in codes(mutate(0, end=record.end + 1))
    assert 'PT_INSTANCE_MISMATCH' in codes(mutate(0, end=record.start + 4, processing_time=4))
    assert 'INVALID_MACHINE_ID' in codes(mutate(0, machine_id=7))


def test_makespan_must_match():
    result = valid_schedule()
    result.makespan += 1
    assert 'MAKESPAN_MISMATCH' in codes(result)


@pytest.mark.parametrize('field, value', [('start', 1.0), ('end', True), ('job_id', '0')])
def test_noninteger_fields_are_rejected_not_coerced(field, value):
    assert codes(mutate(0, **{field: value}))


def test_result_must_reference_the_expected_instance():
    result = valid_schedule()
    other = FJSPInstance.from_jobs_array([[[(0, 3)]]])
    assert 'INSTANCE_MISMATCH' in codes(result, expected_instance=other)
    result.instance = None
    assert codes(result) == {'NO_INSTANCE'}


def test_empty_schedule_is_infeasible():
    assert 'NO_RECORDS' in codes(ScheduleResult(instance=create_toy_instance()))


def test_decoder_rejects_invalid_assignments():
    instance = create_toy_instance()
    with pytest.raises(ValueError, match='exactly'):
        decode_schedule([(0, 0, 0)], instance)
    order = [(0, 1, 1), (0, 0, 0), (1, 0, 2), (2, 0, 0), (1, 1, 1), (2, 1, 2), (2, 2, 1)]
    with pytest.raises(ValueError, match='out-of-order'):
        decode_schedule(order, instance)
    order = [(0, 0, 2), (1, 0, 2), (2, 0, 0), (0, 1, 1), (1, 1, 1), (2, 1, 2), (2, 2, 1)]
    with pytest.raises(ValueError, match='ineligible'):
        decode_schedule(order, instance)
