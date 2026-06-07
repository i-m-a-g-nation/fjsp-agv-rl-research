"""
exp_017_phase2a_dynamic_report.py

Phase 2A dynamic report builder:
- Read exp_014 dynamic smoke results
- Read exp_015 dynamic event-file audit results
- Read exp_016 event-file reschedule results
- Write one compact Markdown report for Phase 2A dynamic reproducibility

The script does not run solvers. It summarizes already validated CSV artifacts.
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class ScheduleResultRow:
    """One normalized schedule-result row from exp_014 or exp_016."""

    experiment_id: str
    instance_name: str
    algorithm: str
    makespan: int
    feasible: str
    note: str


@dataclass(frozen=True)
class EventAuditRow:
    """One dynamic event-file audit row from exp_015."""

    file_name: str
    event_count: int
    first_time: int | None
    last_time: int | None
    nondecreasing_time: str
    status: str
    note: str


def load_schedule_rows(path: str | Path) -> list[ScheduleResultRow]:
    """Load schedule result rows and validate required fields."""

    required = {"experiment_id", "instance_name", "algorithm", "makespan", "feasible", "note"}
    rows: list[ScheduleResultRow] = []
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("schedule result CSV is missing required fields")
        for raw in reader:
            rows.append(
                ScheduleResultRow(
                    experiment_id=raw["experiment_id"],
                    instance_name=raw["instance_name"],
                    algorithm=raw["algorithm"],
                    makespan=int(raw["makespan"]),
                    feasible=raw["feasible"],
                    note=raw["note"],
                )
            )
    if not rows:
        raise ValueError("schedule result CSV must contain at least one row")
    return rows


def load_event_audit_rows(path: str | Path) -> list[EventAuditRow]:
    """Load dynamic event-file audit rows and validate required fields."""

    required = {
        "file_name",
        "event_count",
        "first_time",
        "last_time",
        "nondecreasing_time",
        "status",
        "note",
    }
    rows: list[EventAuditRow] = []
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("event audit CSV is missing required fields")
        for raw in reader:
            rows.append(
                EventAuditRow(
                    file_name=raw["file_name"],
                    event_count=int(raw["event_count"]),
                    first_time=_optional_int(raw["first_time"]),
                    last_time=_optional_int(raw["last_time"]),
                    nondecreasing_time=raw["nondecreasing_time"],
                    status=raw["status"],
                    note=raw["note"],
                )
            )
    if not rows:
        raise ValueError("event audit CSV must contain at least one row")
    return rows


def build_markdown_report(
    smoke_rows: Sequence[ScheduleResultRow],
    audit_rows: Sequence[EventAuditRow],
    replay_rows: Sequence[ScheduleResultRow],
) -> str:
    """Build a compact Phase 2A dynamic overview report."""

    smoke_pass = sum(1 for row in smoke_rows if row.feasible == "PASS")
    audit_pass = sum(1 for row in audit_rows if row.status == "PASS")
    replay_pass = sum(1 for row in replay_rows if row.feasible == "PASS")
    all_pass = (
        smoke_pass == len(smoke_rows)
        and audit_pass == len(audit_rows)
        and replay_pass == len(replay_rows)
    )

    return "\n\n".join([
        "# Phase 2A Dynamic Overview Report",
        (
            "This report summarizes the current Phase 2A dynamic FJSP chain: "
            "dynamic smoke rescheduling, JSON event-file auditing, and JSON-driven "
            "event replay rescheduling."
        ),
        _summary_table([
            ("dynamic smoke reschedules", smoke_pass, len(smoke_rows)),
            ("event-file audits", audit_pass, len(audit_rows)),
            ("event-file replay reschedules", replay_pass, len(replay_rows)),
        ]),
        "Overall status: PASS." if all_pass else "Overall status: FAIL.",
        "## Dynamic Smoke Reschedules",
        _schedule_table(smoke_rows),
        "## Dynamic Event Files",
        _event_audit_table(audit_rows),
        "## Event-File Replay Reschedules",
        _schedule_table(replay_rows),
        (
            "Interpretation note: this overview is a report-only gate. It does "
            "not rerun solvers; it expects exp_014, exp_015, and exp_016 CSV "
            "artifacts to have been refreshed first."
        ),
        "",
    ])


def write_markdown_report(path: str | Path, text: str) -> None:
    """Write a Markdown report using UTF-8 encoding."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def _summary_table(rows: Sequence[tuple[str, int, int]]) -> str:
    table = [
        "| gate | passed | total |",
        "| --- | ---: | ---: |",
    ]
    table.extend(f"| {name} | {passed} | {total} |" for name, passed, total in rows)
    return "\n".join(table)


def _schedule_table(rows: Sequence[ScheduleResultRow]) -> str:
    table = [
        "| scenario | algorithm | makespan | feasible | note |",
        "| --- | --- | ---: | --- | --- |",
    ]
    table.extend(
        (
            f"| {row.instance_name} | {row.algorithm} | {row.makespan} | "
            f"{row.feasible} | {row.note} |"
        )
        for row in rows
    )
    return "\n".join(table)


def _event_audit_table(rows: Sequence[EventAuditRow]) -> str:
    table = [
        "| file | events | first | last | order | status | note |",
        "| --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    table.extend(
        (
            f"| {row.file_name} | {row.event_count} | {_optional_text(row.first_time)} | "
            f"{_optional_text(row.last_time)} | {row.nondecreasing_time} | "
            f"{row.status} | {row.note} |"
        )
        for row in rows
    )
    return "\n".join(table)


def _optional_int(value: str) -> int | None:
    return None if value == "" else int(value)


def _optional_text(value: int | None) -> str:
    return "" if value is None else str(value)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the report builder."""

    root = Path(__file__).parent.parent
    result_root = root / "experiments" / "results"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke-input",
        type=Path,
        default=result_root / "exp_014_dynamic_reschedule_smoke.csv",
        help="Input exp_014 dynamic smoke CSV",
    )
    parser.add_argument(
        "--audit-input",
        type=Path,
        default=result_root / "exp_015_dynamic_event_file_check.csv",
        help="Input exp_015 dynamic event-file audit CSV",
    )
    parser.add_argument(
        "--replay-input",
        type=Path,
        default=result_root / "exp_016_dynamic_event_file_reschedule.csv",
        help="Input exp_016 event-file replay CSV",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=result_root / "exp_017_phase2a_dynamic_report.md",
        help="Output Markdown report",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Build the Phase 2A dynamic Markdown report and return an exit code."""

    args = parse_args(argv)
    try:
        report = build_markdown_report(
            load_schedule_rows(args.smoke_input),
            load_event_audit_rows(args.audit_input),
            load_schedule_rows(args.replay_input),
        )
        write_markdown_report(args.output, report)
    except Exception as exc:
        print(f"Dynamic report error: {exc}")
        return 2

    print(f"Phase 2A dynamic report written to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
