"""Maintenance plan: production records (ScheduleResult) plus one maintenance record per window."""

from dataclasses import dataclass

from fjsp_lab.fjsp.schedule import ScheduleResult


@dataclass(frozen=True)
class MaintenanceRecord:
    machine_id: int
    start: int
    end: int
    duration: int
    window: int = 0          # index k of the machine's maintenance window


@dataclass(frozen=True)
class MaintenanceScheduleResult(ScheduleResult):
    maintenance_records: tuple[MaintenanceRecord, ...] = ()
    total_tardiness: int | None = None
    solver_objective_value: float | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if isinstance(self.maintenance_records, list):
            object.__setattr__(self, 'maintenance_records', tuple(self.maintenance_records))
