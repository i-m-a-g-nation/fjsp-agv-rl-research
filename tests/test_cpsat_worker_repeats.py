from pathlib import Path

from experiments.common import SolverRun
from experiments.exp_008_cpsat_worker_repeats import (
    aggregate_worker_runs,
    build_repeated_worker_solvers,
    run_repeated_worker_sweep,
    validate_repeats,
    write_worker_aggregates_csv,
)
from src.data.instance import create_toy_instance
from src.solvers.heuristics import fifo_solve


def _run(name, makespan, bound, gap, runtime=1.0, feasible=True):
    result = fifo_solve(create_toy_instance()) if feasible else None
    if result is not None:
        result.makespan = makespan
        result.solver_objective_bound = bound
        result.solver_gap = gap
        result.solver_wall_time = runtime - 0.1
    return SolverRun(
        algorithm=name,
        result=result,
        makespan=makespan if feasible else None,
        feasible=feasible,
        runtime_s=runtime,
        note="FEASIBLE" if feasible else "ERROR: failed",
        error=None if feasible else "failed",
    )


def test_validate_repeats_rejects_non_positive_values():
    for repeats in [0, -1]:
        try:
            validate_repeats(repeats)
        except ValueError as exc:
            assert "positive" in str(exc)
        else:
            raise AssertionError("expected repetition-count rejection")


def test_build_repeated_worker_solvers_binds_worker_major_runs():
    instance = create_toy_instance()
    observed = []

    def solver_fn(inst, time_limit, num_workers):
        assert inst is instance
        observed.append((time_limit, num_workers))
        return fifo_solve(inst)

    solvers = build_repeated_worker_solvers(
        instance,
        [1, 0],
        repeats=2,
        time_limit=3.0,
        solver_fn=solver_fn,
    )

    assert [name for name, _fn in solvers] == [
        "CP-SAT(workers=1,tl=3s,run=1/2)",
        "CP-SAT(workers=1,tl=3s,run=2/2)",
        "CP-SAT(workers=auto,tl=3s,run=1/2)",
        "CP-SAT(workers=auto,tl=3s,run=2/2)",
    ]
    for _name, fn in solvers:
        fn()
    assert observed == [(3.0, 1), (3.0, 1), (3.0, 0), (3.0, 0)]


def test_aggregate_worker_runs_computes_statistics_and_keeps_failures_visible():
    runs = [
        _run("one-1", 20, 5.0, 0.75, runtime=1.0),
        _run("one-2", 10, 6.0, 0.40, runtime=2.0),
        _run("auto-1", 12, 7.0, 0.42, runtime=3.0),
        _run("auto-2", None, None, None, runtime=5.0, feasible=False),
    ]

    one, auto = aggregate_worker_runs(runs, [1, 0], repeats=2)

    assert one.feasible_runs == 2
    assert one.best_makespan == 10
    assert one.mean_makespan == 15
    assert one.stdev_makespan == 5
    assert one.worst_makespan == 20
    assert one.best_bound == 6.0
    assert one.mean_bound == 5.5
    assert one.best_gap == 0.40
    assert one.mean_gap == 0.575
    assert one.mean_runtime_s == 1.5
    assert one.statuses == "FEASIBLE:2"

    assert auto.feasible_runs == 1
    assert auto.mean_runtime_s == 4.0
    assert auto.statuses == "ERROR: failed:1;FEASIBLE:1"


def test_aggregate_worker_runs_rejects_unexpected_run_count():
    try:
        aggregate_worker_runs([], [1], repeats=2)
    except ValueError as exc:
        assert "expected 2 solver runs" in str(exc)
    else:
        raise AssertionError("expected run-count rejection")


def test_write_worker_aggregates_csv_uses_stable_fields(tmp_path):
    aggregate = aggregate_worker_runs(
        [_run("one", 10, 6.0, 0.4)],
        [1],
        repeats=1,
    )[0]
    output = tmp_path / "summary.csv"

    write_worker_aggregates_csv(output, [aggregate])

    text = output.read_text(encoding="utf-8")
    assert text.startswith("workers,repeats,feasible_runs,best_makespan")
    assert "1,1,1,10,10.000000,0.000000,10,6.000000" in text


def test_run_repeated_worker_sweep_normalizes_raw_and_summary_records(tmp_path):
    path = Path(tmp_path) / "tiny.fjs"
    path.write_text("1 1 1.0\n1 1 0 3\n", encoding="utf-8")
    observed = []

    def solver_fn(instance, time_limit, num_workers):
        observed.append(num_workers)
        result = fifo_solve(instance)
        result.solver_status = "FEASIBLE"
        result.solver_objective_bound = float(num_workers)
        result.solver_gap = 0.5
        result.solver_wall_time = time_limit
        return result

    records, aggregates, failures = run_repeated_worker_sweep(
        path,
        [1, 0],
        repeats=2,
        time_limit=3.0,
        instance_name="tiny.fjs",
        solver_fn=solver_fn,
    )

    assert not failures
    assert observed == [1, 1, 0, 0]
    assert len(records) == 4
    assert [aggregate.feasible_runs for aggregate in aggregates] == [2, 2]
    assert [aggregate.best_bound for aggregate in aggregates] == [1.0, 0.0]
