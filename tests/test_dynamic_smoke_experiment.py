import csv

from experiments.exp_014_dynamic_reschedule_smoke import (
    build_dynamic_smoke_solvers,
    run_dynamic_smoke_experiment,
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
    }
    assert all(record.note == "DYNAMIC_PASS" for record in records)

    output = tmp_path / "exp_014.csv"
    write_results_csv(output, records)
    with output.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    assert {row["feasible"] for row in rows} == {"PASS"}
