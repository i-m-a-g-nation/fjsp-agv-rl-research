"""Literal, hand-derived G1 schedules; no optimization or metric under test."""

from src.graduation.data import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask, to_fjsp_instance
from src.graduation.result import MaintenanceRecord, MaintenanceScheduleResult


def one_machine(fixed=True, due_dates=(2, 4), fixed_start=0):
    data = ParallelMaintenanceInstance(tuple(ProductionTask(j, 2, d) for j, d in enumerate(due_dates)), 1,
                                       (MaintenanceRequirement(0, 2, 0, 6, fixed_start),))
    maintenance = MaintenanceRecord(0, 0, 2, 2) if fixed else MaintenanceRecord(0, 4, 6, 2)
    result = MaintenanceScheduleResult(instance=to_fjsp_instance(data), maintenance_records=[maintenance],
                                       total_tardiness=4 if fixed else 0)
    result.add_record(0, 0, 0, 2 if fixed else 0, 2)
    result.add_record(1, 0, 0, 4 if fixed else 2, 2)
    result.compute_makespan()
    return data, result


def two_machines(fixed=True):
    data = ParallelMaintenanceInstance(tuple(ProductionTask(j, 2, d) for j, d in enumerate((2, 2, 4))), 2,
        tuple(MaintenanceRequirement(m, 2, 0, 6, 0) for m in range(2)))
    records = [MaintenanceRecord(0, 0, 2, 2), MaintenanceRecord(1, 0, 2, 2)] if fixed else [
        MaintenanceRecord(0, 4, 6, 2), MaintenanceRecord(1, 2, 4, 2)]
    result = MaintenanceScheduleResult(instance=to_fjsp_instance(data), maintenance_records=records,
                                       total_tardiness=6 if fixed else 0)
    offset = 2 if fixed else 0
    result.add_record(0, 0, 0, offset, 2)
    result.add_record(1, 0, 1, offset, 2)
    result.add_record(2, 0, 0, offset + 2, 2)
    result.compute_makespan()
    return data, result
