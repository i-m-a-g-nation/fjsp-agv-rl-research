"""Instance data, generator and the maintenance feasibility checker."""

from dataclasses import replace

import pytest

from fjsp_lab.maintenance import (
    MaintenanceRecord, MaintenanceRequirement, MaintenanceScheduleResult, ParallelMaintenanceInstance,
    ProductionTask, check_parallel_maintenance_feasibility, to_fjsp_instance,
)
from fjsp_lab.fjsp.schedule import ScheduleRecord
from fjsp_lab.maintenance.feasibility import build_plan
from fjsp_lab.maintenance.generator import (
    build_instance, cycle_counts, periodic_case, sample_instances, split_instances,
)


def two_machine_instance():
    tasks = (ProductionTask(0, 3, 3), ProductionTask(1, 2, 4), ProductionTask(2, 4, 6))
    maintenance = (MaintenanceRequirement(0, 2, 2, 8, 3), MaintenanceRequirement(1, 1, 0, 6, 4))
    return ParallelMaintenanceInstance(tasks, 2, maintenance)


def valid_plan(data):
    # machine 0: job 0 [0,3), maintenance [3,5), job 2 [5,9); machine 1: job 1 [0,2), maintenance [4,5)
    return build_plan(data, [(0, 0, 0), (2, 0, 5), (1, 1, 0)], [(0, 0, 3), (1, 0, 4)])


def codes(result, data, mode):
    accepted, violations = check_parallel_maintenance_feasibility(result, data, mode=mode)
    assert not accepted
    return {v.code for v in violations}


@pytest.mark.parametrize('kwargs, message', [
    ({'machine_id': 0, 'duration': 3, 'window_start': 0, 'window_end': 2}, 'fit inside'),
    ({'machine_id': 0, 'duration': 2, 'window_start': 0, 'window_end': 4, 'fixed_start': 3}, 'fixed_start'),
    ({'machine_id': 0, 'duration': True, 'window_start': 0, 'window_end': 4}, 'integer'),
])
def test_requirement_validation(kwargs, message):
    with pytest.raises(ValueError, match=message):
        MaintenanceRequirement(**kwargs)


def test_every_machine_needs_one_requirement_and_ids_are_dense():
    tasks = (ProductionTask(0, 1, 1),)
    with pytest.raises(ValueError, match='at least one maintenance window'):
        ParallelMaintenanceInstance(tasks, 2, (MaintenanceRequirement(0, 1, 0, 2),))
    with pytest.raises(ValueError, match='cover 0..n-1'):
        ParallelMaintenanceInstance((ProductionTask(1, 1, 1),), 1, (MaintenanceRequirement(0, 1, 0, 2),))


def test_record_round_trip_and_production_view():
    data = two_machine_instance()
    assert ParallelMaintenanceInstance.from_record(data.to_record()) == data
    fjsp = to_fjsp_instance(data)
    assert fjsp.num_jobs == 3 and fjsp.jobs[2].operations[0].machine_options == ((0, 4), (1, 4))


def test_generator_is_deterministic_and_follows_its_formulas():
    data = build_instance(8, 2, 30, 25, 75, 101)
    assert data == build_instance(8, 2, 30, 25, 75, 101)
    w = (sum(t.processing_time for t in data.tasks) + 1) // 2
    q, s = max(1, (30 * w + 99) // 100), (25 * w + 99) // 100
    for item in data.maintenance:
        assert (item.duration, item.window_end - item.window_start, item.fixed_start - item.window_start) == (q, q + s, s // 2)
    assert all(1 <= t.processing_time <= 20 for t in data.tasks)
    assert build_instance(8, 2, 30, 25, 75, 101, 'window_latest').maintenance[0].fixed_start == \
        data.maintenance[0].window_start + s


def test_g3a_grid_layout(cases):
    assert len(cases) == 240 and len({c.case_id for c in cases}) == 240
    assert [c.group for c in cases] == ['primary'] * 160 + ['sensitivity'] * 80
    assert {(c.num_tasks, c.num_machines) for c in cases[160:]} == {(8, 2)}
    assert cases[0].case_id == 'g3a-main-n8-m2-a10-b25-t75-s101-midpoint'
    assert cases[0].data.to_record() == {
        'tasks': [[0, 18, 18], [1, 18, 28], [2, 1, 36], [3, 10, 22], [4, 10, 33], [5, 20, 48], [6, 9, 24], [7, 6, 21]],
        'num_machines': 2, 'maintenance': [[0, 5, 0, 17, 6], [1, 5, 11, 28, 17]]}


def test_learning_splits_are_disjoint_and_balanced():
    test = split_instances('test')
    assert len(test) == 600 and {(i.num_tasks, i.num_machines) for i in test[:6]} == {
        (8, 2), (8, 4), (16, 2), (16, 4), (24, 2), (24, 4)}
    validation = split_instances('validation')
    assert {i.seed for i in test}.isdisjoint(i.seed for i in validation)
    assert sample_instances(range(5), sampler_seed=1) == sample_instances(range(5), sampler_seed=1)


def test_valid_plan_is_accepted_in_both_modes():
    data = two_machine_instance()
    plan = valid_plan(data)
    assert plan.total_tardiness == 0 + 0 + 3
    for mode in ('fixed', 'joint'):
        assert check_parallel_maintenance_feasibility(plan, data, mode=mode) == (True, [])


def test_maintenance_violations_are_named():
    data = two_machine_instance()
    plan = valid_plan(data)

    def with_maintenance(*records):
        return replace(plan, maintenance_records=list(records))

    good0, good1 = plan.maintenance_records
    assert 'MISSING_MAINTENANCE' in codes(with_maintenance(good0), data, 'joint')
    assert 'DUPLICATE_MAINTENANCE' in codes(with_maintenance(good0, good1, good1), data, 'joint')
    assert 'MAINTENANCE_OUTSIDE_WINDOW' in codes(with_maintenance(good0, MaintenanceRecord(1, 6, 7, 1)), data, 'joint')
    assert 'MAINTENANCE_DURATION_MISMATCH' in codes(with_maintenance(MaintenanceRecord(0, 3, 6, 3), good1), data, 'joint')
    assert 'MAINTENANCE_PRODUCTION_OVERLAP' in codes(with_maintenance(MaintenanceRecord(0, 2, 4, 2), good1), data, 'joint')
    shifted = with_maintenance(good0, MaintenanceRecord(1, 3, 4, 1))
    assert check_parallel_maintenance_feasibility(shifted, data, mode='joint')[0] is True
    assert 'FIXED_START_MISMATCH' in codes(shifted, data, 'fixed')


def test_production_and_objective_violations_are_named():
    data = two_machine_instance()
    plan = valid_plan(data)
    assert 'TOTAL_TARDINESS_MISMATCH' in codes(replace(plan, total_tardiness=2), data, 'joint')
    assert 'TOTAL_TARDINESS_MISMATCH' in codes(replace(plan, total_tardiness=None), data, 'joint')
    records = [ScheduleRecord(2, 0, 0, 2, 6, 4) if r.job_id == 2 else r for r in plan.records]
    assert 'BASE_SCHEDULE_INVALID' in codes(replace(plan, records=records, makespan=6), data, 'joint')
    wrong_instance = replace(plan, instance=to_fjsp_instance(build_instance(3, 2, 10, 25, 75, 1)))
    assert 'INSTANCE_MISMATCH' in codes(wrong_instance, data, 'joint')
    assert codes(MaintenanceScheduleResult(), data, 'joint')


def test_checker_rejects_bad_mode_arguments():
    data = two_machine_instance()
    with pytest.raises(ValueError):
        check_parallel_maintenance_feasibility(valid_plan(data), data, mode='both')
    unfixed = replace(data, maintenance=tuple(replace(m, fixed_start=None) for m in data.maintenance))
    with pytest.raises(ValueError, match='fixed mode'):
        check_parallel_maintenance_feasibility(valid_plan(unfixed), unfixed, mode='fixed')


def periodic_instance():
    # machine 0: windows [2, 6) and [10, 14), q = 2; machine 1: one window [0, 20), q = 3
    tasks = (ProductionTask(0, 2, 2), ProductionTask(1, 3, 9), ProductionTask(2, 4, 4))
    maintenance = (MaintenanceRequirement(0, 2, 10, 14, 11), MaintenanceRequirement(0, 2, 2, 6, 2),
                   MaintenanceRequirement(1, 3, 0, 20, 5))
    return ParallelMaintenanceInstance(tasks, 2, maintenance)


def test_periodic_windows_are_ordered_and_must_not_overlap():
    data = periodic_instance()
    assert [w.window_start for w in data.windows[0]] == [2, 10] and data.num_windows == 3
    with pytest.raises(ValueError, match='overlap'):
        ParallelMaintenanceInstance(data.tasks, 2, data.maintenance + (MaintenanceRequirement(0, 1, 5, 8),))
    assert ParallelMaintenanceInstance.from_record(data.to_record()) == data


def test_periodic_plan_needs_one_maintenance_in_every_window():
    data = periodic_instance()
    # machine 0: job 0 [0,2), maintenance [2,4), job 1 [4,7), maintenance [10,12); machine 1: job 2 [0,4), maintenance [5,8)
    plan = build_plan(data, [(0, 0, 0), (1, 0, 4), (2, 1, 0)], [(0, 0, 2), (0, 1, 10), (1, 0, 5)])
    assert check_parallel_maintenance_feasibility(plan, data, mode='joint') == (True, [])
    assert check_parallel_maintenance_feasibility(plan, data, mode='fixed')[0] is False   # window 1 fixed at 11
    first, second, other = plan.maintenance_records
    assert 'MISSING_MAINTENANCE' in codes(replace(plan, maintenance_records=[first, other]), data, 'joint')
    assert 'INVALID_MAINTENANCE_WINDOW' in codes(
        replace(plan, maintenance_records=[first, replace(second, window=2), other]), data, 'joint')
    misplaced = replace(second, window=0)          # the [10, 12) maintenance claimed for window [2, 6)
    assert {'MAINTENANCE_OUTSIDE_WINDOW', 'DUPLICATE_MAINTENANCE', 'MISSING_MAINTENANCE'} <= codes(
        replace(plan, maintenance_records=[first, misplaced, other]), data, 'joint')


def test_periodic_generator_keeps_windows_disjoint_and_load_independent_of_count():
    for profile in ('uniform2', 'mixed'):
        for n, m in ((20, 8), (50, 4), (100, 2)):
            data = periodic_case(n, m, profile, 20, 50, 75, 11).data
            assert [len(w) for w in data.windows] == list(cycle_counts(profile, m))
            w = (sum(t.processing_time for t in data.tasks) + m - 1) // m
            for windows in data.windows:
                total = sum(item.duration for item in windows)
                assert 0.2 * w <= total <= 0.2 * w + 2 * len(windows)
    assert periodic_case(20, 2, 'mixed', 10, 25, 75, 1).data.tasks == build_instance(20, 2, 10, 25, 75, 1).tasks
