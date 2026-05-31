from experiments.exp_006_cpsat_time_limit_sweep import (
    build_cpsat_solvers,
    print_sweep_runs,
    run_cpsat_sweep,
    validate_time_limits,
)
from src.data.instance import create_toy_instance
from src.solvers.heuristics import fifo_solve


def test_validate_time_limits_preserves_positive_order():
    assert validate_time_limits([3.0, 1.0, 10.0]) == [3.0, 1.0, 10.0]


def test_validate_time_limits_rejects_non_positive_values():
    try:
        validate_time_limits([1.0, 0.0])
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("expected non-positive time limit rejection")


def test_build_cpsat_solvers_binds_each_time_limit():
    instance = create_toy_instance()
    observed_limits = []

    def solver_fn(inst, time_limit, num_workers):
        assert inst is instance
        observed_limits.append((time_limit, num_workers))
        return fifo_solve(inst)

    solvers = build_cpsat_solvers(instance, [1.0, 3.0], solver_fn=solver_fn)

    assert [name for name, _fn in solvers] == [
        "CP-SAT(tl=1s)",
        "CP-SAT(tl=3s)",
    ]
    for _name, fn in solvers:
        fn()
    assert observed_limits == [(1.0, 1), (3.0, 1)]


def test_build_cpsat_solvers_rejects_non_positive_workers():
    instance = create_toy_instance()

    try:
        build_cpsat_solvers(instance, [1.0], num_workers=0)
    except ValueError as exc:
        assert "num_workers" in str(exc)
    else:
        raise AssertionError("expected non-positive worker count rejection")


def test_run_cpsat_sweep_normalizes_records(tmp_path):
    path = tmp_path / "tiny.fjs"
    path.write_text("1 1 1.0\n1 1 0 3\n", encoding="utf-8")

    def solver_fn(instance, time_limit, num_workers):
        assert num_workers == 1
        result = fifo_solve(instance)
        result.solver_status = "FEASIBLE"
        result.solver_objective_bound = time_limit
        result.solver_gap = 0.5
        result.solver_wall_time = time_limit / 2
        return result

    records, failures = run_cpsat_sweep(
        path,
        [1.0, 3.0],
        instance_name="tiny.fjs",
        solver_fn=solver_fn,
    )

    assert not failures
    assert [record.algorithm for record in records] == [
        "CP-SAT(tl=1s)",
        "CP-SAT(tl=3s)",
    ]
    assert [record.note for record in records] == ["FEASIBLE", "FEASIBLE"]
    assert [record.objective_bound for record in records] == [1.0, 3.0]
    assert [record.solver_wall_time for record in records] == [0.5, 1.5]


def test_print_sweep_runs_includes_diagnostics(capsys, tmp_path):
    path = tmp_path / "tiny.fjs"
    path.write_text("1 1 1.0\n1 1 0 3\n", encoding="utf-8")

    def solver_fn(instance, time_limit, num_workers):
        assert num_workers == 1
        result = fifo_solve(instance)
        result.solver_status = "FEASIBLE"
        result.solver_objective_bound = 2.0
        result.solver_gap = 1 / 3
        result.solver_wall_time = time_limit
        return result

    run_cpsat_sweep(path, [1.0], solver_fn=solver_fn)

    output = capsys.readouterr().out
    assert "bound" in output
    assert "gap" in output
    assert "2.000000" in output
    assert "0.333333" in output
