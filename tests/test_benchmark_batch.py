from experiments.exp_005_benchmark_batch import (
    build_solver_specs,
    discover_benchmark_files,
    run_benchmark_batch,
)
from src.solvers.heuristics import fifo_solve


def test_discover_benchmark_files_recurses_and_sorts(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.fjs").write_text("1 1 1.0 1 1 0 2", encoding="utf-8")
    (tmp_path / "a.fjs").write_text("1 1 1.0 1 1 0 1", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("not a benchmark", encoding="utf-8")

    paths = discover_benchmark_files(tmp_path)

    assert [path.relative_to(tmp_path).as_posix() for path in paths] == [
        "a.fjs",
        "nested/b.fjs",
    ]


def test_discover_benchmark_files_applies_positive_cap(tmp_path):
    for name in ["c.fjs", "a.fjs", "b.fjs"]:
        (tmp_path / name).write_text("1 1 1.0 1 1 0 1", encoding="utf-8")

    paths = discover_benchmark_files(tmp_path, max_files=2)

    assert [path.name for path in paths] == ["a.fjs", "b.fjs"]


def test_run_benchmark_batch_records_loader_failure_and_valid_schedule(tmp_path):
    valid_path = tmp_path / "valid.fjs"
    invalid_path = tmp_path / "invalid.fjs"
    valid_path.write_text("1 1 1.0 1 1 0 3", encoding="utf-8")
    invalid_path.write_text("not a benchmark", encoding="utf-8")

    records, failures = run_benchmark_batch(
        [invalid_path, valid_path],
        tmp_path,
        [("FIFO", fifo_solve)],
    )

    assert [(record.instance_name, record.algorithm) for record in records] == [
        ("invalid.fjs", "LOAD"),
        ("valid.fjs", "FIFO"),
    ]
    assert not records[0].feasible
    assert records[0].note.startswith("ERROR:")
    assert records[1].feasible
    assert records[1].makespan == 3
    assert len(failures) == 1
    assert "invalid.fjs / LOAD" in failures[0]


def test_build_solver_specs_can_skip_cp_sat():
    names = [
        name
        for name, _solver_fn in build_solver_specs(
            cp_sat_time_limit=3.0,
            include_cp_sat=False,
        )
    ]

    assert names == [
        "FIFO",
        "SPT",
        "EarliestAvailableMachine",
        "DispatchFIFO",
        "DispatchSPT",
        "DispatchEFT",
        "DispatchMWKR",
        "DispatchMOPNR",
    ]
