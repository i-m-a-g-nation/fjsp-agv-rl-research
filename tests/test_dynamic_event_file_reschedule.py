import csv

from experiments.common import write_results_csv
from experiments.exp_016_dynamic_event_file_reschedule import (
    build_event_file_scenarios,
    build_event_file_solvers,
    run_event_file_reschedule_experiment,
)


def test_event_file_scenarios_cover_tracked_json_files():
    scenarios = build_event_file_scenarios()

    assert {scenario.event_file for scenario in scenarios} == {
        "dynamic_events_multi_event.json",
        "dynamic_events_repair_cycle.json",
        "dynamic_events_release_stagger.json",
    }
    assert all(scenario.rule == "eft" for scenario in scenarios)


def test_event_file_reschedule_experiment_records_all_scenarios(tmp_path):
    event_root = "experiments"

    runs, records = run_event_file_reschedule_experiment(event_root=event_root)

    assert len(runs) == len(build_event_file_solvers(event_root))
    assert len(records) == len(build_event_file_solvers(event_root))
    assert all(run.feasible for run in runs)
    assert all(record.feasible for record in records)
    assert {record.instance_name for record in records} == {
        "dynamic_file_multi_event_2x2",
        "dynamic_file_repair_cycle_1x2",
        "dynamic_file_release_stagger_3x2",
    }
    assert all(record.note == "EVENT_FILE_DYNAMIC_PASS" for record in records)

    output = tmp_path / "exp_016.csv"
    write_results_csv(output, records)
    with output.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 3
    assert {row["feasible"] for row in rows} == {"PASS"}
