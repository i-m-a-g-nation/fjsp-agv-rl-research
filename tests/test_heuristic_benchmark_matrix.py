from experiments.common import SolverRun
from experiments.exp_010_heuristic_benchmark_matrix import (
    HeuristicSpec,
    aggregate_heuristic_runs,
    build_heuristic_specs,
    run_heuristic_benchmark_matrix,
    validate_seeds,
    write_heuristic_aggregates_csv,
)
from src.data.instance import create_toy_instance
from src.solvers.heuristics import fifo_solve


def _run(name, makespan, runtime=1.0, feasible=True):
    return SolverRun(
        algorithm=name,
        result=fifo_solve(create_toy_instance()) if feasible else None,
        makespan=makespan if feasible else None,
        feasible=feasible,
        runtime_s=runtime,
        note="PASS" if feasible else "ERROR: failed",
        error=None if feasible else "failed",
    )


def test_validate_seeds_rejects_empty_and_duplicate_values():
    for seeds in [[], [42, 42]]:
        try:
            validate_seeds(seeds)
        except ValueError:
            pass
        else:
            raise AssertionError("expected random-seed rejection")


def test_build_heuristic_specs_binds_random_seed_labels():
    specs = build_heuristic_specs([42, 123])

    assert [spec.run_label for spec in specs[-4:]] == [
        "Random(seed=42)",
        "Random(seed=123)",
        "DispatchRandom(seed=42)",
        "DispatchRandom(seed=123)",
    ]
    assert [spec.family for spec in specs[-4:]] == [
        "Random",
        "Random",
        "DispatchRandom",
        "DispatchRandom",
    ]


def test_aggregate_heuristic_runs_groups_variants_and_keeps_failures_visible():
    specs = [
        HeuristicSpec("FIFO", "FIFO", "fixed", fifo_solve),
        HeuristicSpec("Random", "Random(seed=1)", "seed=1", fifo_solve),
        HeuristicSpec("Random", "Random(seed=2)", "seed=2", fifo_solve),
    ]
    runs = [
        _run("FIFO", 20, runtime=1.0),
        _run("Random(seed=1)", 10, runtime=2.0),
        _run("Random(seed=2)", None, runtime=4.0, feasible=False),
    ]

    fifo, random = aggregate_heuristic_runs("tiny.fjs", specs, runs)

    assert fifo.family == "FIFO"
    assert fifo.variants == "fixed"
    assert fifo.mean_makespan == 20.0
    assert random.family == "Random"
    assert random.variants == "seed=1;seed=2"
    assert random.runs == 2
    assert random.feasible_runs == 1
    assert random.best_makespan == 10
    assert random.mean_runtime_s == 3.0
    assert random.statuses == "ERROR: failed:1;PASS:1"


def test_run_heuristic_benchmark_matrix_records_loader_failure_and_valid_run(tmp_path):
    invalid_path = tmp_path / "invalid.fjs"
    valid_path = tmp_path / "valid.fjs"
    invalid_path.write_text("not a benchmark", encoding="utf-8")
    valid_path.write_text("1 1 1.0\n1 1 0 3\n", encoding="utf-8")
    specs = [HeuristicSpec("FIFO", "FIFO", "fixed", fifo_solve)]

    records, aggregates, failures = run_heuristic_benchmark_matrix(
        [invalid_path, valid_path],
        tmp_path,
        specs,
    )

    assert [(record.instance_name, record.algorithm) for record in records] == [
        ("invalid.fjs", "LOAD"),
        ("valid.fjs", "FIFO"),
    ]
    assert not records[0].feasible
    assert records[1].feasible
    assert records[1].makespan == 3
    assert len(aggregates) == 1
    assert aggregates[0].instance_name == "valid.fjs"
    assert len(failures) == 1
    assert "invalid.fjs / LOAD" in failures[0]


def test_write_heuristic_aggregates_csv_uses_stable_fields(tmp_path):
    specs = [HeuristicSpec("FIFO", "FIFO", "fixed", fifo_solve)]
    aggregate = aggregate_heuristic_runs(
        "tiny.fjs",
        specs,
        [_run("FIFO", 10)],
    )[0]
    output = tmp_path / "summary.csv"

    write_heuristic_aggregates_csv(output, [aggregate])

    text = output.read_text(encoding="utf-8")
    assert text.startswith("instance_name,algorithm_family,variants,runs")
    assert "tiny.fjs,FIFO,fixed,1,1,10,10.000000,0.000000,10" in text
