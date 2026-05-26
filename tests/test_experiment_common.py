import csv

from experiments.common import ExperimentRecord, write_results_csv


def test_experiment_record_csv_row_formats_values():
    record = ExperimentRecord(
        experiment_id="exp_test",
        instance_name="toy",
        algorithm="DispatchMWKR",
        makespan=12,
        feasible=True,
        runtime_s=0.1234567,
        note="PASS",
        objective_bound=11.0,
        gap=0.0,
        solver_wall_time=0.2,
    )

    assert record.to_csv_row() == {
        "experiment_id": "exp_test",
        "instance_name": "toy",
        "algorithm": "DispatchMWKR",
        "makespan": "12",
        "feasible": "PASS",
        "runtime_s": "0.123457",
        "note": "PASS",
        "objective_bound": "11.000000",
        "gap": "0.000000",
        "solver_wall_time": "0.200000",
    }


def test_write_results_csv_creates_parent_and_file(tmp_path):
    path = tmp_path / "nested" / "results.csv"
    records = [
        ExperimentRecord(
            experiment_id="exp_test",
            instance_name="toy",
            algorithm="CP-SAT",
            makespan=None,
            feasible=False,
            runtime_s=1.0,
            note="ERROR",
        )
    ]

    write_results_csv(path, records)

    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert rows == [
        {
            "experiment_id": "exp_test",
            "instance_name": "toy",
            "algorithm": "CP-SAT",
            "makespan": "",
            "feasible": "FAIL",
            "runtime_s": "1.000000",
            "note": "ERROR",
            "objective_bound": "",
            "gap": "",
            "solver_wall_time": "",
        }
    ]
