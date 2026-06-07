import csv

from experiments.exp_014_dynamic_reschedule_smoke import (
    build_markdown_report,
    build_dynamic_smoke_solvers,
    main,
    run_dynamic_smoke_experiment,
    write_markdown_report,
)
from experiments.common import write_results_csv


def test_dynamic_smoke_experiment_records_all_scenarios(tmp_path):
    runs, records = run_dynamic_smoke_experiment()

    assert len(runs) == len(build_dynamic_smoke_solvers())
    assert len(records) == len(build_dynamic_smoke_solvers())
    assert all(run.feasible for run in runs)
    assert all(record.feasible for record in records)
    assert {record.instance_name for record in records} == {
        "dynamic_breakdown_1x1",
        "dynamic_job_arrival_2x1",
        "dynamic_multi_event_2x2",
    }
    assert all(record.note == "DYNAMIC_PASS" for record in records)

    output = tmp_path / "exp_014.csv"
    write_results_csv(output, records)
    with output.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 3
    assert {row["feasible"] for row in rows} == {"PASS"}


def test_dynamic_smoke_markdown_report_lists_scenarios(tmp_path):
    _runs, records = run_dynamic_smoke_experiment()

    report = build_markdown_report(records)
    output = tmp_path / "report.md"
    write_markdown_report(output, report)

    text = output.read_text(encoding="utf-8")
    assert "Feasible rows: 3/3" in text
    assert "dynamic_breakdown_1x1" in text
    assert "dynamic_job_arrival_2x1" in text
    assert "dynamic_multi_event_2x2" in text


def test_dynamic_smoke_main_writes_to_custom_output_dir(tmp_path):
    exit_code = main(["--output-dir", str(tmp_path)])

    assert exit_code == 0
    assert (tmp_path / "exp_014_dynamic_reschedule_smoke.csv").exists()
    assert (tmp_path / "exp_014_dynamic_reschedule_smoke.md").exists()
