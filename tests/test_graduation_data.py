from dataclasses import FrozenInstanceError

import pytest


@pytest.mark.parametrize('field,value', [
    ('job_id', -1), ('job_id', True), ('processing_time', 0), ('processing_time', 2.0),
    ('processing_time', float('nan')), ('due_date', -1), ('due_date', False),
])
def test_production_data_refuses_invalid_or_noninteger_values(field, value):
    from src.graduation.data import ProductionTask
    values = dict(job_id=0, processing_time=2, due_date=4)
    values[field] = value
    with pytest.raises(ValueError):
        ProductionTask(**values)


@pytest.mark.parametrize('changes', [
    {'duration': 0}, {'duration': True}, {'window_start': -1}, {'window_end': 0},
    {'duration': 7}, {'fixed_start': 5}, {'fixed_start': 1.0}, {'machine_id': False},
])
def test_maintenance_data_requires_complete_window_fit(changes):
    from src.graduation.data import MaintenanceRequirement
    values = dict(machine_id=0, duration=2, window_start=0, window_end=6, fixed_start=0)
    values.update(changes)
    with pytest.raises(ValueError):
        MaintenanceRequirement(**values)


def test_identical_adapter_preserves_job_identity_and_requires_idle_machine_maintenance():
    from src.graduation.data import ProductionTask, MaintenanceRequirement, ParallelMaintenanceInstance, to_fjsp_instance
    tasks = [ProductionTask(1, 3, 7), ProductionTask(0, 2, 4)]
    maintenance = [MaintenanceRequirement(1, 2, 0, 6), MaintenanceRequirement(0, 2, 0, 6)]
    data = ParallelMaintenanceInstance(tasks, 2, maintenance)
    tasks.clear()
    maintenance.clear()
    instance = to_fjsp_instance(data)
    assert [task.job_id for task in data.tasks] == [0, 1]
    assert [item.machine_id for item in data.maintenance] == [0, 1]
    assert instance.num_jobs == 2 and instance.num_machines == 2 and instance.total_ops == 2
    assert instance.get_op_options(0, 0) == ((0, 2), (1, 2))
    assert instance.get_op_options(1, 0) == ((0, 3), (1, 3))
    with pytest.raises(FrozenInstanceError):
        data.tasks[0].processing_time = 99
    with pytest.raises(FrozenInstanceError):
        data.num_machines = 3
    with pytest.raises(ValueError):
        ParallelMaintenanceInstance(data.tasks, 2, data.maintenance[:1])


@pytest.mark.parametrize('bad', ['empty', 'duplicate_jobs', 'gap_jobs', 'duplicate_machines', 'wrong_machine', 'bool_machines'])
def test_instance_refuses_missing_or_ambiguous_identity(bad):
    from src.graduation.data import ProductionTask, MaintenanceRequirement, ParallelMaintenanceInstance
    task = ProductionTask(0, 2, 4)
    maint = MaintenanceRequirement(0, 2, 0, 6)
    values = dict(tasks=(task,), num_machines=1, maintenance=(maint,))
    if bad == 'empty': values['tasks'] = ()
    if bad == 'duplicate_jobs': values['tasks'] = (task, task)
    if bad == 'gap_jobs': values['tasks'] = (ProductionTask(1, 2, 4),)
    if bad == 'duplicate_machines': values.update(num_machines=2, maintenance=(maint, maint))
    if bad == 'wrong_machine': values['maintenance'] = (MaintenanceRequirement(1, 2, 0, 6),)
    if bad == 'bool_machines': values['num_machines'] = True
    with pytest.raises(ValueError):
        ParallelMaintenanceInstance(**values)


def test_unsupported_features_are_rejected_instead_of_ignored():
    from src.graduation.data import ProductionTask, ParallelMaintenanceInstance
    with pytest.raises((TypeError, ValueError)):
        ProductionTask(job_id=0, processing_time=2, due_date=4, release_time=5)
    with pytest.raises((TypeError, ValueError)):
        ParallelMaintenanceInstance(tasks=(), num_machines=1, maintenance=(), crew_capacity=1)


def test_maintenance_result_keeps_production_makespan_and_uniform_result_type():
    from src.graduation.data import ProductionTask, MaintenanceRequirement, ParallelMaintenanceInstance, to_fjsp_instance
    from src.graduation.result import MaintenanceRecord, MaintenanceScheduleResult
    from src.scheduling.encoding import ScheduleResult
    data = ParallelMaintenanceInstance((ProductionTask(0, 2, 2),), 1, (MaintenanceRequirement(0, 2, 0, 6),))
    result = MaintenanceScheduleResult(instance=to_fjsp_instance(data), maintenance_records=[MaintenanceRecord(0, 4, 6, 2)])
    result.add_record(0, 0, 0, 0, 2)
    assert isinstance(result, ScheduleResult)
    assert result.compute_makespan() == 2
    assert len(result.records) == 1 and result.maintenance_records[0].end == 6
    assert result.total_tardiness is None
