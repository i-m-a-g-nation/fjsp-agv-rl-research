from experiments.exp_007_cpsat_worker_sweep import (
    build_worker_solvers,
    run_worker_sweep,
    validate_worker_counts,
    worker_label,
)
from src.data.instance import create_toy_instance
from src.solvers.heuristics import fifo_solve


def test_validate_worker_counts_preserves_distinct_order():
    assert validate_worker_counts([1, 4, 0, 2]) == [1, 4, 0, 2]


def test_validate_worker_counts_rejects_negative_values():
    try:
        validate_worker_counts([1, -1])
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:
        raise AssertionError("expected negative worker-count rejection")


def test_validate_worker_counts_rejects_duplicates():
    try:
        validate_worker_counts([1, 1])
    except ValueError as exc:
        assert "distinct" in str(exc)
    else:
        raise AssertionError("expected duplicate worker-count rejection")


def test_worker_label_names_automatic_configuration():
    assert worker_label(0) == "auto"
    assert worker_label(4) == "4"


def test_build_worker_solvers_binds_each_worker_count():
    instance = create_toy_instance()
    observed = []

    def solver_fn(inst, time_limit, num_workers):
        assert inst is instance
        observed.append((time_limit, num_workers))
        return fifo_solve(inst)

    solvers = build_worker_solvers(
        instance,
        [1, 0],
        time_limit=3.0,
        solver_fn=solver_fn,
    )

    assert [name for name, _fn in solvers] == [
        "CP-SAT(workers=1,tl=3s)",
        "CP-SAT(workers=auto,tl=3s)",
    ]
    for _name, fn in solvers:
        fn()
    assert observed == [(3.0, 1), (3.0, 0)]


def test_run_worker_sweep_normalizes_records(tmp_path):
    path = tmp_path / "tiny.fjs"
    path.write_text("1 1 1.0\n1 1 0 3\n", encoding="utf-8")

    def solver_fn(instance, time_limit, num_workers):
        result = fifo_solve(instance)
        result.solver_status = "FEASIBLE"
        result.solver_objective_bound = float(num_workers)
        result.solver_gap = 0.5
        result.solver_wall_time = time_limit
        return result

    records, failures = run_worker_sweep(
        path,
        [1, 0],
        time_limit=3.0,
        instance_name="tiny.fjs",
        solver_fn=solver_fn,
    )

    assert not failures
    assert [record.algorithm for record in records] == [
        "CP-SAT(workers=1,tl=3s)",
        "CP-SAT(workers=auto,tl=3s)",
    ]
    assert [record.note for record in records] == ["FEASIBLE", "FEASIBLE"]
    assert [record.objective_bound for record in records] == [1.0, 0.0]
