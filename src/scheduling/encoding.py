from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from src.data.instance import FJSPInstance


@dataclass
class ScheduleRecord:
    job_id: int
    op_id: int
    machine_id: int
    start: int
    end: int
    processing_time: int


@dataclass
class ScheduleResult:
    records: List[ScheduleRecord] = field(default_factory=list)
    makespan: int = 0
    instance: FJSPInstance | None = None
    solver_status: str | None = None

    def add_record(self, job_id: int, op_id: int, machine_id: int,
                   start: int, processing_time: int) -> ScheduleRecord:
        rec = ScheduleRecord(
            job_id=job_id,
            op_id=op_id,
            machine_id=machine_id,
            start=start,
            end=start + processing_time,
            processing_time=processing_time,
        )
        self.records.append(rec)
        return rec

    def compute_makespan(self) -> int:
        if not self.records:
            self.makespan = 0
            return 0
        self.makespan = max(r.end for r in self.records)
        return self.makespan

    def sorted_records(self) -> List[ScheduleRecord]:
        return sorted(self.records, key=lambda r: (r.job_id, r.op_id))
