"""Maintenance records accompany the existing mutable production result API."""

from dataclasses import dataclass, field

from src.scheduling.encoding import ScheduleResult


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
