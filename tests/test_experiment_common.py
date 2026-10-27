import csv

from experiments.common import (
    ExperimentRecord,
    print_solver_runs,
    record_from_run,
    run_solver_suite,
    run_solver_once,
    write_results_csv,
)
from src.data.instance import create_toy_instance
from src.scheduling.encoding import ScheduleResult


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


def test_run_solver_once_success_builds_valid_run():
    instance = create_toy_instance()

    def solver():
        result = ScheduleResult(instance=instance)
        result.add_record(0, 0, 0, start=0, processing_time=3)
        result.add_record(0, 1, 1, start=3, processing_time=4)
        result.add_record(1, 0, 0, start=3, processing_time=2)
        result.add_record(1, 1, 1, start=7, processing_time=3)
        result.add_record(2, 0, 0, start=5, processing_time=5)
        result.add_record(2, 1, 2, start=10, processing_time=2)
        result.add_record(2, 2, 0, start=12, processing_time=1)
        result.compute_makespan()
        return result

    run = run_solver_once("manual", solver, expected_instance=instance)

    assert run.algorithm == "manual"
    assert run.result is not None
    assert run.feasible
    assert run.makespan == 13
    assert run.note == "PASS"


def test_run_solver_once_exception_builds_failed_run():
    def solver():
        raise RuntimeError("boom")

    run = run_solver_once("bad", solver, expected_instance=create_toy_instance())

    assert run.algorithm == "bad"
    assert run.result is None
    assert not run.feasible
    assert run.makespan is None
    assert run.note == "ERROR: boom"
    assert run.error == "boom"


def test_run_solver_once_marks_infeasible_result_as_failed():
    instance = create_toy_instance()
    result = ScheduleResult(instance=instance)
    result.add_record(0, 0, 0, start=0, processing_time=3)
    result.compute_makespan()

    run = run_solver_once("incomplete", lambda: result, expected_instance=instance)

    assert run.result is result
    assert not run.feasible
    assert run.makespan == 3
    assert run.note.startswith("violations=")
    assert run.error is None


def test_run_solver_suite_preserves_order():
    instance = create_toy_instance()

    def solver():
        result = ScheduleResult(instance=instance)
        result.add_record(0, 0, 0, start=0, processing_time=3)
        result.add_record(0, 1, 1, start=3, processing_time=4)
        result.add_record(1, 0, 0, start=3, processing_time=2)
        result.add_record(1, 1, 1, start=7, processing_time=3)
        result.add_record(2, 0, 0, start=5, processing_time=5)
        result.add_record(2, 1, 2, start=10, processing_time=2)
        result.add_record(2, 2, 0, start=12, processing_time=1)
        result.compute_makespan()
        return result

    runs = run_solver_suite([("first", solver), ("second", solver)], expected_instance=instance)

    assert [run.algorithm for run in runs] == ["first", "second"]
    assert all(run.feasible for run in runs)


def test_print_solver_runs_outputs_table(capsys):
    run = run_solver_once("bad", lambda: (_ for _ in ()).throw(RuntimeError("boom")), expected_instance=create_toy_instance())

    print_solver_runs([run], algorithm_width=10)

    output = capsys.readouterr().out
    assert "Algorithm" in output
    assert "makespan" in output
    assert "bad" in output
    assert "ERROR: boom" in output


def test_record_from_run_copies_solver_metadata():
    instance = create_toy_instance()
    result = ScheduleResult(
        instance=instance,
        solver_status="OPTIMAL",
        solver_objective_bound=11.0,
        solver_gap=0.0,
        solver_wall_time=0.01,
    )
    result.add_record(0, 0, 0, start=0, processing_time=3)
    result.compute_makespan()
    run = run_solver_once("metadata", lambda: result, expected_instance=instance)

    record = record_from_run("exp", "toy", run, note="custom")

    assert record.note == "custom"
    assert record.objective_bound == 11.0
    assert record.gap == 0.0
    assert record.solver_wall_time == 0.01
