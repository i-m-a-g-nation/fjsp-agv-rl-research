from experiments.exp_009_cpsat_benchmark_matrix import (
    BenchmarkWorkerAggregate,
    run_benchmark_matrix,
    write_benchmark_aggregates_csv,
)
from src.solvers.heuristics import fifo_solve


def test_run_benchmark_matrix_records_loader_failure_and_valid_aggregates(tmp_path):
    invalid_path = tmp_path / "invalid.fjs"
    valid_path = tmp_path / "valid.fjs"
    invalid_path.write_text("not a benchmark", encoding="utf-8")
    valid_path.write_text("1 1 1.0\n1 1 0 3\n", encoding="utf-8")
    observed = []

    def solver_fn(instance, time_limit, num_workers):
        observed.append((time_limit, num_workers))
        result = fifo_solve(instance)
        result.solver_status = "FEASIBLE"
        result.solver_objective_bound = float(num_workers)
        result.solver_gap = 0.5
        result.solver_wall_time = time_limit
        return result

    records, aggregates, failures = run_benchmark_matrix(
        [invalid_path, valid_path],
        tmp_path,
        [1, 0],
        repeats=2,
        time_limit=3.0,
        solver_fn=solver_fn,
    )

    assert [(record.instance_name, record.algorithm) for record in records[:1]] == [
        ("invalid.fjs", "LOAD"),
    ]
    assert not records[0].feasible
    assert len(records) == 5
    assert observed == [(3.0, 1), (3.0, 1), (3.0, 0), (3.0, 0)]
    assert [aggregate.instance_name for aggregate in aggregates] == [
        "valid.fjs",
        "valid.fjs",
    ]
    assert [aggregate.aggregate.feasible_runs for aggregate in aggregates] == [2, 2]
    assert len(failures) == 1
    assert "invalid.fjs / LOAD" in failures[0]


def test_write_benchmark_aggregates_csv_prepends_instance_name(tmp_path):
    valid_path = tmp_path / "valid.fjs"
    valid_path.write_text("1 1 1.0\n1 1 0 3\n", encoding="utf-8")

    def solver_fn(instance, time_limit, num_workers):
        result = fifo_solve(instance)
        result.solver_status = "FEASIBLE"
        result.solver_objective_bound = float(num_workers)
        result.solver_gap = 0.5
        result.solver_wall_time = time_limit
        return result

    _records, aggregates, failures = run_benchmark_matrix(
        [valid_path],
        tmp_path,
        [1],
        repeats=1,
        time_limit=3.0,
        solver_fn=solver_fn,
    )
    output = tmp_path / "summary.csv"

    write_benchmark_aggregates_csv(output, aggregates)

    assert not failures
    text = output.read_text(encoding="utf-8")
    assert text.startswith("instance_name,workers,repeats,feasible_runs")
    assert "valid.fjs,1,1,1,3,3.000000,0.000000,3,1.000000" in text


def test_benchmark_worker_aggregate_exposes_instance_name():
    class Aggregate:
        def to_csv_row(self):
            return {"workers": "auto"}

    row = BenchmarkWorkerAggregate("mk03.fjs", Aggregate()).to_csv_row()

    assert row == {"instance_name": "mk03.fjs", "workers": "auto"}
