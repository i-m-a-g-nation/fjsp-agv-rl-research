from experiments.exp_011_heuristic_quality_report import (
    BenchmarkReference,
    aggregate_family_quality,
    build_quality_rows,
    load_benchmark_references,
    relative_gap,
    write_family_quality_csv,
    write_quality_rows_csv,
)


def test_relative_gap_rejects_invalid_values():
    assert relative_gap(110, 100) == 0.1
    for makespan, bks in [(99, 100), (1, 0)]:
        try:
            relative_gap(makespan, bks)
        except ValueError:
            pass
        else:
            raise AssertionError("expected invalid relative-gap rejection")


def test_load_benchmark_references_validates_bounds_and_duplicates(tmp_path):
    valid = tmp_path / "valid.csv"
    valid.write_text(
        "instance_name,fjsplib_lb,fjsplib_ub\n"
        "mk01.fjs,40,40\n",
        encoding="utf-8",
    )
    references = load_benchmark_references(valid)
    assert references["mk01.fjs"] == BenchmarkReference("mk01.fjs", 40, 40)

    invalid = tmp_path / "invalid.csv"
    invalid.write_text(
        "instance_name,fjsplib_lb,fjsplib_ub\n"
        "mk01.fjs,40,40\n"
        "mk01.fjs,40,40\n",
        encoding="utf-8",
    )
    try:
        load_benchmark_references(invalid)
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("expected duplicate BKS rejection")


def test_build_quality_rows_computes_bks_relative_metrics(tmp_path):
    summary = tmp_path / "summary.csv"
    summary.write_text(
        "instance_name,algorithm_family,variants,feasible_runs,best_makespan,"
        "mean_makespan,stdev_makespan,worst_makespan,statuses\n"
        "mk01.fjs,FIFO,fixed,1,44,48.0,0.0,52,PASS:1\n",
        encoding="utf-8",
    )
    references = {"mk01.fjs": BenchmarkReference("mk01.fjs", 40, 40)}

    row = build_quality_rows(summary, references)[0]

    assert row.best_gap_ratio == 0.1
    assert row.mean_gap_ratio == 0.2
    assert row.worst_gap_ratio == 0.3


def test_build_quality_rows_rejects_missing_reference(tmp_path):
    summary = tmp_path / "summary.csv"
    summary.write_text(
        "instance_name,algorithm_family,variants,feasible_runs,best_makespan,"
        "mean_makespan,stdev_makespan,worst_makespan,statuses\n"
        "missing.fjs,FIFO,fixed,1,44,44.0,0.0,44,PASS:1\n",
        encoding="utf-8",
    )
    try:
        build_quality_rows(summary, {})
    except ValueError as exc:
        assert "missing BKS reference" in str(exc)
    else:
        raise AssertionError("expected missing BKS rejection")


def test_build_quality_rows_rejects_missing_summary_instance(tmp_path):
    summary = tmp_path / "summary.csv"
    summary.write_text(
        "instance_name,algorithm_family,variants,feasible_runs,best_makespan,"
        "mean_makespan,stdev_makespan,worst_makespan,statuses\n"
        "mk01.fjs,FIFO,fixed,1,44,44.0,0.0,44,PASS:1\n",
        encoding="utf-8",
    )
    references = {
        "mk01.fjs": BenchmarkReference("mk01.fjs", 40, 40),
        "mk03.fjs": BenchmarkReference("mk03.fjs", 204, 204),
    }

    try:
        build_quality_rows(summary, references)
    except ValueError as exc:
        assert "missing BKS instances" in str(exc)
    else:
        raise AssertionError("expected missing summary instance rejection")


def test_aggregate_family_quality_summarizes_instances(tmp_path):
    summary = tmp_path / "summary.csv"
    summary.write_text(
        "instance_name,algorithm_family,variants,feasible_runs,best_makespan,"
        "mean_makespan,stdev_makespan,worst_makespan,statuses\n"
        "one.fjs,FIFO,fixed,1,110,110.0,0.0,110,PASS:1\n"
        "two.fjs,FIFO,fixed,1,240,240.0,0.0,240,PASS:1\n",
        encoding="utf-8",
    )
    references = {
        "one.fjs": BenchmarkReference("one.fjs", 100, 100),
        "two.fjs": BenchmarkReference("two.fjs", 200, 200),
    }

    family = aggregate_family_quality(build_quality_rows(summary, references))[0]

    assert family.family == "FIFO"
    assert family.instances == 2
    assert abs(family.mean_best_gap_ratio - 0.15) < 1e-12
    assert family.max_best_gap_ratio == 0.2


def test_quality_csv_writers_use_stable_fields(tmp_path):
    summary = tmp_path / "summary.csv"
    summary.write_text(
        "instance_name,algorithm_family,variants,feasible_runs,best_makespan,"
        "mean_makespan,stdev_makespan,worst_makespan,statuses\n"
        "mk01.fjs,FIFO,fixed,1,44,44.0,0.0,44,PASS:1\n",
        encoding="utf-8",
    )
    references = {"mk01.fjs": BenchmarkReference("mk01.fjs", 40, 40)}
    rows = build_quality_rows(summary, references)
    families = aggregate_family_quality(rows)
    quality_output = tmp_path / "quality.csv"
    family_output = tmp_path / "family.csv"

    write_quality_rows_csv(quality_output, rows)
    write_family_quality_csv(family_output, families)

    assert quality_output.read_text(encoding="utf-8").startswith(
        "instance_name,algorithm_family,variants,feasible_runs"
    )
    assert "mk01.fjs,FIFO,fixed,1,40,40,44,0.100000" in quality_output.read_text(
        encoding="utf-8"
    )
    assert family_output.read_text(encoding="utf-8").startswith(
        "algorithm_family,instances,mean_best_gap_ratio"
    )
