from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExperimentRecord:
    """One normalized row for an experiment result table."""

    experiment_id: str
    instance_name: str
    algorithm: str
    makespan: int | None
    feasible: bool
    runtime_s: float
    note: str

    def to_csv_row(self) -> dict[str, str]:
        """Convert the record to stable text values for CSV output."""

        return {
            "experiment_id": self.experiment_id,
            "instance_name": self.instance_name,
            "algorithm": self.algorithm,
            "makespan": "" if self.makespan is None else str(self.makespan),
            "feasible": "PASS" if self.feasible else "FAIL",
            "runtime_s": f"{self.runtime_s:.6f}",
            "note": self.note,
        }


def write_results_csv(path: str | Path, records: list[ExperimentRecord]) -> None:
    """Write normalized experiment records to a UTF-8 CSV file."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "experiment_id",
        "instance_name",
        "algorithm",
        "makespan",
        "feasible",
        "runtime_s",
        "note",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_csv_row())
