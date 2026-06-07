"""
exp_016_dynamic_event_file_reschedule.py

Phase 2A event-file rescheduling smoke experiment:
- Load each tracked dynamic event JSON scenario file
- Apply it to a small compatible base state
- Reschedule with the deterministic EFT repair baseline
- Validate each full schedule through the common experiment runner
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
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
    apply_events,
    frozen_records_at_time,
    load_event_specs_json,
    reschedule_from_state,
)
from src.scheduling.encoding import ScheduleRecord, ScheduleResult  # noqa: E402


@dataclass(frozen=True)
class EventFileScenario:
    """A JSON event file plus the minimal state needed to replay it."""

    instance_name: str
    event_file: str
    state: DynamicFJSPState
    frozen_records: tuple[ScheduleRecord, ...] = ()
    rule: str = "eft"


def build_event_file_scenarios() -> list[EventFileScenario]:
    """Return small deterministic scenarios driven by JSON event files."""

    multi_instance = FJSPInstance.from_jobs_array([
        [[(0, 2)], [(0, 3), (1, 4)]],
    ], num_machines=2)
    multi_initial = ScheduleResult(instance=multi_instance)
    multi_initial.add_record(0, 0, 0, start=0, processing_time=2)
    multi_initial.compute_makespan()

    repair_instance = FJSPInstance.from_jobs_array([
        [[(0, 2)], [(0, 3), (1, 4)]],
    ], num_machines=2)

    release_instance = FJSPInstance.from_jobs_array([
        [[(0, 2), (1, 3)]],
    ], num_machines=2)

    return [
        EventFileScenario(
            instance_name="dynamic_file_multi_event_2x2",
            event_file="dynamic_events_multi_event.json",
            state=DynamicFJSPState.from_instance(multi_instance, current_time=2),
            frozen_records=tuple(frozen_records_at_time(multi_initial, current_time=2)),
        ),
        EventFileScenario(
            instance_name="dynamic_file_repair_cycle_1x2",
            event_file="dynamic_events_repair_cycle.json",
            state=DynamicFJSPState.from_instance(repair_instance, current_time=0),
        ),
        EventFileScenario(
            instance_name="dynamic_file_release_stagger_3x2",
            event_file="dynamic_events_release_stagger.json",
            state=DynamicFJSPState.from_instance(release_instance, current_time=0),
        ),
    ]


def solver_from_event_file_scenario(
    scenario: EventFileScenario,
    event_root: str | Path,
) -> Callable[[], ScheduleResult]:
    """Build a solver callable that replays one JSON event-file scenario."""

    root = Path(event_root)

    def solve() -> ScheduleResult:
        events = load_event_specs_json(root / scenario.event_file)
        state = apply_events(scenario.state, events)
        return reschedule_from_state(
            state,
            frozen_records=scenario.frozen_records,
            rule=scenario.rule,
        )

    return solve


def build_event_file_solvers(
    event_root: str | Path,
) -> list[tuple[str, str, Callable[[], ScheduleResult]]]:
    """Return named event-file solver callables for Experiment 016."""

    return [
        (
            scenario.instance_name,
            f"DynamicEFT({scenario.event_file})",
            solver_from_event_file_scenario(scenario, event_root),
        )
        for scenario in build_event_file_scenarios()
    ]


def run_event_file_reschedule_experiment(
    event_root: str | Path | None = None,
    experiment_id: str = "exp_016_dynamic_event_file_reschedule",
) -> tuple[list[SolverRun], list[ExperimentRecord]]:
    """Run all JSON event-file rescheduling scenarios."""

    root = Path(__file__).parent if event_root is None else Path(event_root)
    runs = []
    records: list[ExperimentRecord] = []
    for instance_name, algorithm, solver_fn in build_event_file_solvers(root):
        run = run_solver_once(algorithm, solver_fn, success_note="EVENT_FILE_DYNAMIC_PASS")
        runs.append(run)
        records.append(record_from_run(experiment_id, instance_name, run))
    return runs, records


def build_markdown_report(records: list[ExperimentRecord]) -> str:
    """Build a readable Markdown report for event-file rescheduling runs."""

    total = len(records)
    feasible = sum(1 for record in records if record.feasible)
    rows = [
        "| scenario | event file | makespan | feasible | note |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for record in records:
        event_file = _event_file_from_algorithm(record.algorithm)
        makespan = "" if record.makespan is None else str(record.makespan)
        feasible_text = "PASS" if record.feasible else "FAIL"
        rows.append(
            "| "
            + " | ".join([
                record.instance_name,
                event_file,
                makespan,
                feasible_text,
                record.note,
            ])
            + " |"
        )
    return "\n".join([
        "# Phase 2A Event-File Reschedule Report",
        "",
        (
            f"This report replays {total} dynamic event JSON files. "
            f"Feasible rows: {feasible}/{total}."
        ),
        "",
        *rows,
        "",
        (
            "Each PASS row is a full ScheduleResult produced after loading the "
            "listed JSON file, applying its events to a compatible dynamic "
            "state, and passing both the static and dynamic feasibility gates."
        ),
        "",
    ])


def write_markdown_report(path: str | Path, report: str) -> None:
    """Write a UTF-8 Markdown report, creating parent folders as needed."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")


def _event_file_from_algorithm(algorithm: str) -> str:
    prefix = "DynamicEFT("
    suffix = ")"
    if algorithm.startswith(prefix) and algorithm.endswith(suffix):
        return algorithm[len(prefix):-len(suffix)]
    return ""


def main() -> None:
    root = Path(__file__).parent.parent
    experiment_id = "exp_016_dynamic_event_file_reschedule"
    runs, records = run_event_file_reschedule_experiment(
        event_root=root / "experiments",
        experiment_id=experiment_id,
    )

    print_solver_runs(runs, algorithm_width=48)
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
    print("All event-file dynamic reschedules passed feasibility check.")
    sys.exit(0)


if __name__ == "__main__":
    main()
