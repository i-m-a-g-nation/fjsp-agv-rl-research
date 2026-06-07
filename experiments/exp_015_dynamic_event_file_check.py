"""
exp_015_dynamic_event_file_check.py

Phase 2A dynamic event-file audit:
- Discover tracked dynamic event JSON files
- Validate that each file can be loaded into typed dynamic events
- Check that event times are non-decreasing for deterministic replay
"""
from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dynamic import load_event_specs_json  # noqa: E402


@dataclass(frozen=True)
class EventFileAudit:
    """One audit row for a dynamic event JSON file."""

    file_name: str
    event_count: int
    first_time: int | None
    last_time: int | None
    nondecreasing_time: bool
    status: str
    note: str

    def to_csv_row(self) -> dict[str, str]:
        """Convert the audit result to stable CSV text values."""

        return {
            "file_name": self.file_name,
            "event_count": str(self.event_count),
            "first_time": "" if self.first_time is None else str(self.first_time),
            "last_time": "" if self.last_time is None else str(self.last_time),
            "nondecreasing_time": "PASS" if self.nondecreasing_time else "FAIL",
            "status": self.status,
            "note": self.note,
        }


def discover_event_files(root: str | Path) -> list[Path]:
    """Return dynamic event JSON files under an experiments directory."""

    experiments_root = Path(root)
    return sorted(experiments_root.glob("dynamic_events*.json"))


def audit_event_file(path: str | Path, display_root: str | Path | None = None) -> EventFileAudit:
    """Audit one dynamic event JSON file without applying it to an instance."""

    event_path = Path(path)
    if display_root is None:
        file_name = event_path.name
    else:
        file_name = event_path.relative_to(Path(display_root)).as_posix()
    try:
        events = load_event_specs_json(event_path)
    except Exception as exc:
        return EventFileAudit(
            file_name=file_name,
            event_count=0,
            first_time=None,
            last_time=None,
            nondecreasing_time=False,
            status="FAIL",
            note=f"LOAD_ERROR: {exc}",
        )

    times = [event.time for event in events]
    is_ordered = all(previous <= current for previous, current in zip(times, times[1:]))
    if not events:
        return EventFileAudit(
            file_name=file_name,
            event_count=0,
            first_time=None,
            last_time=None,
            nondecreasing_time=True,
            status="FAIL",
            note="EMPTY_EVENT_FILE",
        )
    if not is_ordered:
        return EventFileAudit(
            file_name=file_name,
            event_count=len(events),
            first_time=times[0],
            last_time=times[-1],
            nondecreasing_time=False,
            status="FAIL",
            note="EVENT_TIMES_NOT_NONDECREASING",
        )
    return EventFileAudit(
        file_name=file_name,
        event_count=len(events),
        first_time=times[0],
        last_time=times[-1],
        nondecreasing_time=True,
        status="PASS",
        note="EVENT_FILE_OK",
    )


def run_event_file_audit(root: str | Path) -> list[EventFileAudit]:
    """Audit every dynamic event JSON file under an experiments directory."""

    experiments_root = Path(root)
    return [
        audit_event_file(path, display_root=experiments_root)
        for path in discover_event_files(experiments_root)
    ]


def write_event_audit_csv(path: str | Path, audits: list[EventFileAudit]) -> None:
    """Write event-file audit rows to a UTF-8 CSV file."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "file_name",
        "event_count",
        "first_time",
        "last_time",
        "nondecreasing_time",
        "status",
        "note",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for audit in audits:
            writer.writerow(audit.to_csv_row())


def print_event_audits(audits: list[EventFileAudit]) -> None:
    """Print a compact console table for dynamic event-file audits."""

    header = (
        f"{'file':36s} {'events':>6s} {'first':>6s} {'last':>6s} "
        f"{'order':>6s} {'status':>6s} note"
    )
    print(header)
    print("-" * len(header))
    for audit in audits:
        first = "" if audit.first_time is None else str(audit.first_time)
        last = "" if audit.last_time is None else str(audit.last_time)
        order = "PASS" if audit.nondecreasing_time else "FAIL"
        print(
            f"{audit.file_name:36s} {audit.event_count:>6d} "
            f"{first:>6s} {last:>6s} {order:>6s} {audit.status:>6s} {audit.note}"
        )


def main() -> None:
    root = Path(__file__).parent.parent
    experiments_root = root / "experiments"
    audits = run_event_file_audit(experiments_root)

    print_event_audits(audits)
    output_path = root / "experiments" / "results" / "exp_015_dynamic_event_file_check.csv"
    write_event_audit_csv(output_path, audits)
    print()
    print(f"CSV results written to: {output_path}")

    failures = [audit for audit in audits if audit.status != "PASS"]
    if failures:
        print()
        print("FAILURES:")
        for failure in failures:
            print(f"  - {failure.file_name}: {failure.note}")
        sys.exit(1)

    print()
    print("All dynamic event JSON files passed the Phase 2A audit.")
    sys.exit(0)


if __name__ == "__main__":
    main()
