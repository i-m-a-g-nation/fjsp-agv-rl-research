from copy import deepcopy

import pytest

from tests.graduation_helpers import one_machine, two_machines


@pytest.mark.parametrize('builder,fixed', [(one_machine, True), (one_machine, False), (two_machines, True), (two_machines, False)])
def test_hand_schedules_pass_complete_maintenance_and_production_conjunction(builder, fixed):
    from src.graduation.feasibility import check_parallel_maintenance_feasibility
    data, result = builder(fixed)
    passed, issues = check_parallel_maintenance_feasibility(result, data, mode='fixed' if fixed else 'joint')
    assert passed and issues == []
    # A fixed schedule is also feasible in the joint domain.
    assert check_parallel_maintenance_feasibility(result, data, mode='joint')[0]


@pytest.mark.parametrize('change,code', [
    ('missing', 'MISSING_MAINTENANCE'), ('duplicate', 'DUPLICATE_MAINTENANCE'),
    ('bad_machine', 'INVALID_MAINTENANCE_MACHINE'), ('negative_machine', 'INVALID_MAINTENANCE_MACHINE'),
    ('window_end', 'MAINTENANCE_OUTSIDE_WINDOW'), ('wrong_duration', 'MAINTENANCE_DURATION_MISMATCH'),
    ('overlap', 'MAINTENANCE_PRODUCTION_OVERLAP'), ('wrong_total', 'TOTAL_TARDINESS_MISMATCH'),
    ('production_duplicate', 'BASE_SCHEDULE_INVALID'), ('wrong_instance', 'INSTANCE_MISMATCH'),
])
def test_invalid_schedules_are_rejected_without_repair(change, code):
    from src.graduation.feasibility import check_parallel_maintenance_feasibility
    from src.data.instance import FJSPInstance
    data, result = one_machine(False)
    if change == 'missing': result.maintenance_records.clear()
    if change == 'duplicate': result.maintenance_records.append(deepcopy(result.maintenance_records[0]))
    if change == 'bad_machine': result.maintenance_records[0].machine_id = 1
    if change == 'negative_machine': result.maintenance_records[0].machine_id = -1
    if change == 'window_end': result.maintenance_records[0].start, result.maintenance_records[0].end = 5, 7
    if change == 'wrong_duration': result.maintenance_records[0].duration = 3
    if change == 'overlap': result.maintenance_records[0].start, result.maintenance_records[0].end = 1, 3
    if change == 'wrong_total': result.total_tardiness = 1
    if change == 'production_duplicate': result.records.append(deepcopy(result.records[0]))
    if change == 'wrong_instance': result.instance = FJSPInstance.from_jobs_array([[[(0, 3)]], [[(0, 2)]]])
    before = deepcopy(result)
    passed, issues = check_parallel_maintenance_feasibility(result, data, mode='joint')
    assert not passed and code in {issue.code for issue in issues}
    assert result == before


def test_idle_machine_still_needs_maintenance_and_parallel_maintenance_is_allowed():
    from src.graduation.data import ProductionTask, MaintenanceRequirement, ParallelMaintenanceInstance, to_fjsp_instance
    from src.graduation.result import MaintenanceRecord, MaintenanceScheduleResult
    from src.graduation.feasibility import check_parallel_maintenance_feasibility
    data = ParallelMaintenanceInstance((ProductionTask(0, 2, 2),), 2,
        (MaintenanceRequirement(0, 2, 0, 6), MaintenanceRequirement(1, 2, 0, 6)))
    result = MaintenanceScheduleResult(instance=to_fjsp_instance(data), total_tardiness=0,
        maintenance_records=[MaintenanceRecord(0, 2, 4, 2)])
    result.add_record(0, 0, 0, 0, 2)
    result.compute_makespan()
    passed, issues = check_parallel_maintenance_feasibility(result, data, mode='joint')
    assert not passed and 'MISSING_MAINTENANCE' in {issue.code for issue in issues}
    result.maintenance_records.append(MaintenanceRecord(1, 2, 4, 2))
    assert check_parallel_maintenance_feasibility(result, data, mode='joint')[0]


def test_fixed_mode_does_not_accept_a_joint_only_maintenance_start():
    from src.graduation.feasibility import check_parallel_maintenance_feasibility
    data, result = one_machine(False)
    passed, issues = check_parallel_maintenance_feasibility(result, data, mode='fixed')
    assert not passed and 'FIXED_START_MISMATCH' in {issue.code for issue in issues}


def test_invalid_mode_and_missing_fixed_start_are_configuration_errors():
    from src.graduation.feasibility import check_parallel_maintenance_feasibility
    data, result = one_machine(False, fixed_start=None)
    with pytest.raises(ValueError): check_parallel_maintenance_feasibility(result, data, mode='unknown')
    with pytest.raises(ValueError): check_parallel_maintenance_feasibility(result, data, mode='fixed')
    assert check_parallel_maintenance_feasibility(result, data, mode='joint')[0]


@pytest.mark.parametrize('field,value,code', [
    ('machine_id', True, 'INVALID_MAINTENANCE_MACHINE'),
    ('start', float('nan'), 'INVALID_MAINTENANCE_TIME'), ('start', True, 'INVALID_MAINTENANCE_TIME'),
    ('end', float('inf'), 'INVALID_MAINTENANCE_TIME'), ('duration', 2.0, 'INVALID_MAINTENANCE_TIME'),
    ('start', -1, 'INVALID_MAINTENANCE_TIME'),
])
def test_malformed_maintenance_values_return_diagnostics(field, value, code):
    from src.graduation.feasibility import check_parallel_maintenance_feasibility
    data, result = one_machine(False)
    setattr(result.maintenance_records[0], field, value)
    passed, issues = check_parallel_maintenance_feasibility(result, data, mode='joint')
    assert not passed and code in {issue.code for issue in issues}


@pytest.mark.parametrize('reported', [None, -1, 1, False, 0.0, float('nan')])
def test_reported_tardiness_must_match_exact_integer_recomputation(reported):
    from src.graduation.feasibility import check_parallel_maintenance_feasibility
    data, result = one_machine(False)
    result.total_tardiness = reported
    passed, issues = check_parallel_maintenance_feasibility(result, data, mode='joint')
    assert not passed and 'TOTAL_TARDINESS_MISMATCH' in {issue.code for issue in issues}


@pytest.mark.parametrize('records', [None, {'machine_id': 0}, [object()], [{'machine_id': 0, 'start': 4, 'end': 6, 'duration': 2}]])
def test_malformed_maintenance_collections_never_pass(records):
    from src.graduation.feasibility import check_parallel_maintenance_feasibility
    data, result = one_machine(False)
    result.maintenance_records = records
    passed, issues = check_parallel_maintenance_feasibility(result, data, mode='joint')
    assert not passed and issues


def test_original_checker_rejection_is_not_bypassed(monkeypatch):
    from src.graduation import _production
    from src.graduation.feasibility import check_parallel_maintenance_feasibility
    from src.scheduling.feasibility import Violation
    data, result = one_machine(False)
    monkeypatch.setattr(_production, 'check_feasibility', lambda value: (False, [Violation('DENIED', 'test refusal')]))
    passed, issues = check_parallel_maintenance_feasibility(result, data, mode='joint')
    assert not passed and any('DENIED' in issue.message for issue in issues)
