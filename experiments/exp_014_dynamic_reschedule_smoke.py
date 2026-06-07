"""
exp_014_dynamic_reschedule_smoke.py

Phase 2A dynamic FJSP smoke experiment:
- Apply a machine-breakdown event and re-dispatch remaining operations
- Apply a job-arrival event and re-dispatch the enlarged instance
- Validate every dynamic reschedule through the Phase 1 feasibility checker
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.common import (  # noqa: E402
    ExperimentRecord,
    SolverRun,
    print_solver_runs,
    record_from_run,
    run_solver_once,
    write_results_csv,
)
from src.data.instance import FJSPInstance  # noqa: E402
from src.dynamic import (  # noqa: E402
    DynamicFJSPState,
    JobArrival,
    MachineBreakdown,
    apply_events,
    frozen_records_at_time,
    load_event_specs_json,
    reschedule_from_state,
)
from src.scheduling.encoding import ScheduleResult  # noqa: E402


def machine_breakdown_solver() -> ScheduleResult:
    """Return a rescheduled result after one machine breakdown."""

    instance = FJSPInstance.from_jobs_array([
        [[(0, 3)], [(0, 2)]],
    ])
    initial = ScheduleResult(instance=instance)
    initial.add_record(0, 0, 0, start=0, processing_time=3)
    initial.compute_makespan()
    state = DynamicFJSPState.from_instance(instance, current_time=3)
    state = state.apply_event(MachineBreakdown(time=3, machine_id=0, repair_time=10))
    frozen = frozen_records_at_time(initial, current_time=3)
    return reschedule_from_state(state, frozen_records=frozen, rule="eft")


def job_arrival_solver() -> ScheduleResult:
    """Return a rescheduled result after one new job arrives."""

    instance = FJSPInstance.from_jobs_array([
        [[(0, 2)]],
    ])
    state = DynamicFJSPState.from_instance(instance, current_time=5)
    state = state.apply_event(JobArrival(time=5, operations=(((0, 3),),)))
    return reschedule_from_state(state, rule="eft")


def multi_event_solver() -> ScheduleResult:
    """Return a rescheduled result after a small sequence of dynamic events."""

    instance = FJSPInstance.from_jobs_array([
        [[(0, 2)], [(0, 3), (1, 4)]],
    ], num_machines=2)
    initial = ScheduleResult(instance=instance)
    initial.add_record(0, 0, 0, start=0, processing_time=2)
    initial.compute_makespan()
    state = DynamicFJSPState.from_instance(instance, current_time=2)
    frozen = frozen_records_at_time(initial, current_time=2)
    event_path = Path(__file__).parent / "dynamic_events_multi_event.json"
    state = apply_events(
        state,
        load_event_specs_json(event_path),
    )
    return reschedule_from_state(state, frozen_records=frozen, rule="eft")


def build_dynamic_smoke_solvers() -> list[tuple[str, str, Callable[[], ScheduleResult]]]:
    """Return named Phase 2A smoke scenarios."""

    return [
        (
            "dynamic_breakdown_1x1",
            "DynamicEFT(machine_breakdown)",
            machine_breakdown_solver,
        ),
        (
            "dynamic_job_arrival_2x1",
            "DynamicEFT(job_arrival)",
            job_arrival_solver,
        ),
        (
            "dynamic_multi_event_2x2",
            "DynamicEFT(multi_event)",
            multi_event_solver,
        ),
    ]


def run_dynamic_smoke_experiment(
    experiment_id: str = "exp_014_dynamic_reschedule_smoke",
) -> tuple[list[SolverRun], list[ExperimentRecord]]:
    """Run all Phase 2A smoke scenarios and return runs plus records."""

    runs = []
    records: list[ExperimentRecord] = []
    for instance_name, algorithm, solver_fn in build_dynamic_smoke_solvers():
        run = run_solver_once(algorithm, solver_fn, success_note="DYNAMIC_PASS")
        runs.append(run)
        records.append(record_from_run(experiment_id, instance_name, run))
    return runs, records


def build_markdown_report(records: list[ExperimentRecord]) -> str:
    """Build a compact Markdown report for Phase 2A dynamic smoke runs."""

    total = len(records)
    feasible = sum(1 for record in records if record.feasible)
    rows = [
        "| scenario | algorithm | makespan | feasible | note |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in records:
        makespan = "" if record.makespan is None else str(record.makespan)
        feasible_text = "PASS" if record.feasible else "FAIL"
        rows.append(
            "| "
            + " | ".join([
                record.instance_name,
                record.algorithm,
                makespan,
                feasible_text,
                record.note,
            ])
            + " |"
        )
    return "\n".join([
        "# Phase 2A Dynamic Reschedule Smoke Report",
        "",
        (
            f"This report summarizes {total} dynamic smoke scenarios. "
            f"Feasible rows: {feasible}/{total}."
        ),
        "",
        *rows,
        "",
        (
            "Every PASS row is a full ScheduleResult validated by the static "
            "Phase 1 feasibility checker and the Phase 2A dynamic checks inside "
            "the rescheduling path."
        ),
        "",
    ])


def write_markdown_report(path: str | Path, report: str) -> None:
    """Write a UTF-8 Markdown report, creating parent folders as needed."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")


def main() -> None:
    root = Path(__file__).parent.parent
    experiment_id = "exp_014_dynamic_reschedule_smoke"
    runs, records = run_dynamic_smoke_experiment(experiment_id)

    print_solver_runs(runs, algorithm_width=32)
    output_path = root / "experiments" / "results" / f"{experiment_id}.csv"
    write_results_csv(output_path, records)
    report_path = root / "experiments" / "results" / f"{experiment_id}.md"
    write_markdown_report(report_path, build_markdown_report(records))
    print()
    print(f"CSV results written to: {output_path}")
    print(f"Markdown report written to: {report_path}")

    failures = [f"{record.algorithm}: {record.note}" for record in records if not record.feasible]
    if failures:
        print()
        print("FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        sys.exit(1)

    print()
    print("All Phase 2A dynamic reschedules passed feasibility check.")
    sys.exit(0)


if __name__ == "__main__":
    main()
