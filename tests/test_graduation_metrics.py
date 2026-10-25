from copy import deepcopy

import pytest

from tests.graduation_helpers import one_machine, two_machines


@pytest.mark.parametrize('builder,fixed,want', [(one_machine, True, 4), (one_machine, False, 0),
                                               (two_machines, True, 6), (two_machines, False, 0)])
def test_total_tardiness_matches_hand_schedules_not_makespan_or_reported_total(builder, fixed, want):
    from src.graduation.metrics import calculate_total_tardiness
    data, result = builder(fixed)
    result.total_tardiness = 999
    assert calculate_total_tardiness(data, result) == want
    assert result.total_tardiness == 999


def test_earliness_cannot_cancel_another_jobs_tardiness():
    from src.graduation.metrics import calculate_total_tardiness
    data, result = one_machine(due_dates=(10, 0))
    assert calculate_total_tardiness(data, result) == 6


@pytest.mark.parametrize('invalid', ['missing', 'duplicate', 'wrong_makespan', 'wrong_instance'])
def test_invalid_production_is_rejected_without_partial_metrics_or_repairs(invalid):
    from src.graduation.metrics import calculate_total_tardiness
    from src.data.instance import FJSPInstance
    data, result = one_machine()
    if invalid == 'missing': result.records.pop()
    if invalid == 'duplicate': result.records.append(deepcopy(result.records[0]))
    if invalid == 'wrong_makespan': result.makespan = 999
    if invalid == 'wrong_instance':
        result.instance = FJSPInstance.from_jobs_array([[[(0, 3)]], [[(0, 2)]]], num_machines=1)
        result.records[0].processing_time = 3
        result.records[0].end = 5
        result.records[1].start, result.records[1].end = 5, 7
        result.compute_makespan()
    before = deepcopy(result)
    with pytest.raises(ValueError):
        calculate_total_tardiness(data, result)
    assert result == before


@pytest.mark.parametrize('field,value', [('start', float('nan')), ('end', float('inf')), ('job_id', True),
                                       ('op_id', 0.0), ('machine_id', '0'), ('processing_time', 2.0)])
def test_malformed_time_and_identity_values_do_not_reach_metric_computation(field, value):
    from src.graduation.metrics import calculate_total_tardiness
    data, result = one_machine()
    setattr(result.records[0], field, value)
    with pytest.raises(ValueError):
        calculate_total_tardiness(data, result)
