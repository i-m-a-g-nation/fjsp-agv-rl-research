"""Maintenance plan: production records (ScheduleResult) plus one maintenance record per machine."""

from dataclasses import dataclass, field

from fjsp_lab.fjsp.schedule import ScheduleResult


@dataclass
class MaintenanceRecord:
    machine_id: int
    start: int
    end: int
    duration: int


@dataclass
class MaintenanceScheduleResult(ScheduleResult):
    maintenance_records: list[MaintenanceRecord] = field(default_factory=list)
    total_tardiness: int | None = None
    solver_objective_value: float | None = None
