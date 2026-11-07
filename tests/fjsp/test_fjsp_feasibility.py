"""The static checker must accept a valid schedule and name every broken constraint."""

from dataclasses import replace

import pytest

from fjsp_lab.fjsp import FJSPInstance, ScheduleRecord, ScheduleResult, check_feasibility, create_toy_instance, decode_schedule


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


def with_records(result, records):
    return replace(result, records=tuple(records), makespan=max(r.end for r in records))


def mutate(index, **changes):
    result = valid_schedule()
    records = list(result.records)
    records[index] = replace(records[index], **changes)
    return replace(result, records=tuple(records))


def test_missing_and_duplicate_operation():
    result = valid_schedule()
    assert {'OP_COUNT_MISMATCH', 'MISSING_OP'} <= codes(replace(result, records=result.records[:-1]))
    assert 'DUPLICATE_OP' in codes(replace(result, records=result.records[:-1] + result.records[:1]))


def test_precedence_violation():
    result = valid_schedule()
    second = next(i for i, r in enumerate(result.records) if (r.job_id, r.op_id) == (0, 1))
    records = list(result.records)
    records[second] = replace(records[second], start=0, end=records[second].processing_time)
    assert 'PRECEDENCE_VIOLATION' in codes(with_records(result, records))


def test_machine_overlap():
    instance = FJSPInstance.from_jobs_array([[[(0, 3)]], [[(0, 2)]]])
    result = ScheduleResult.from_records(
        [ScheduleRecord.placed(0, 0, 0, 0, 3), ScheduleRecord.placed(1, 0, 0, 2, 2)], instance=instance)
    assert 'MACHINE_OVERLAP' in codes(result)


def test_ineligible_machine_and_wrong_durations():
    record = valid_schedule().records[0]          # job 0 op 0 on machine 0, p = 3
    assert 'MACHINE_INELIGIBLE' in codes(mutate(0, machine_id=2))
    assert 'PROCESSING_TIME_MISMATCH' in codes(mutate(0, end=record.end + 1))
    assert 'PT_INSTANCE_MISMATCH' in codes(mutate(0, end=record.start + 4, processing_time=4))
    assert 'INVALID_MACHINE_ID' in codes(mutate(0, machine_id=7))


def test_makespan_must_match():
    result = valid_schedule()
    assert 'MAKESPAN_MISMATCH' in codes(replace(result, makespan=result.makespan + 1))


@pytest.mark.parametrize('changes, code', [
    ({'job_id': 3}, 'INVALID_JOB_ID'),
    ({'job_id': -1}, 'INVALID_JOB_ID'),     # must not silently index the last job
    ({'op_id': 5}, 'INVALID_OP_ID'),
    ({'op_id': -1}, 'INVALID_OP_ID'),
])
def test_out_of_range_identifiers_are_rejected(changes, code):
    assert code in codes(mutate(0, **changes))


@pytest.mark.parametrize('changes, message', [
    ({'start': -1, 'end': 2}, 'is negative'),
    ({'end': 0, 'processing_time': 0}, '<= 0'),
    ({'start': 3, 'end': 0}, '< start'),
])
def test_invalid_times_are_rejected(changes, message):
    # record 0 is job 0 op 0 on machine 0, start 0, p = 3
    _, violations = check_feasibility(mutate(0, **changes))
    assert any(v.code == 'INVALID_TIME' and message in v.message for v in violations), violations


@pytest.mark.parametrize('build, kwargs, code', [
    (lambda r: object(), {}, 'INVALID_RESULT'),
    (lambda r: replace(r, instance='toy'), {}, 'INVALID_INSTANCE'),
    (lambda r: r, {'expected_instance': 'toy'}, 'INVALID_EXPECTED_INSTANCE'),
    (lambda r: replace(r, records='abc'), {}, 'INVALID_RECORDS'),
    (lambda r: replace(r, makespan=-1), {}, 'INVALID_MAKESPAN'),
    (lambda r: replace(r, makespan=True), {}, 'INVALID_MAKESPAN'),
    (lambda r: replace(r, records=r.records[:-1] + ((2, 2, 1, 9, 10, 1),)), {}, 'INVALID_RECORD'),
])
def test_malformed_results_are_rejected(build, kwargs, code):
    assert code in codes(build(valid_schedule()), **kwargs)


@pytest.mark.parametrize('field, value', [('start', 1.0), ('end', True), ('job_id', '0')])
def test_noninteger_fields_are_rejected_not_coerced(field, value):
    assert codes(mutate(0, **{field: value}))


def test_result_must_reference_the_expected_instance():
    result = valid_schedule()
    other = FJSPInstance.from_jobs_array([[[(0, 3)]]])
    assert 'INSTANCE_MISMATCH' in codes(result, expected_instance=other)
    assert codes(replace(result, instance=None)) == {'NO_INSTANCE'}


def test_results_cannot_be_changed_after_construction():
    result = valid_schedule()
    assert isinstance(result.records, tuple)
    with pytest.raises(AttributeError):
        result.makespan = 0
    with pytest.raises(AttributeError):
        result.records[0].start = 5


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
