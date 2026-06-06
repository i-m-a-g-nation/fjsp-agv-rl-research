from experiments.exp_013_cpsat_report import (
    best_row_per_instance,
    build_markdown_report,
    load_cpsat_aggregates,
    summarize_by_worker,
    validate_reference_coverage,
    write_markdown_report,
)
from experiments.exp_011_heuristic_quality_report import BenchmarkReference


HEADER = (
    "instance_name,workers,repeats,feasible_runs,best_makespan,"
    "mean_makespan,stdev_makespan,worst_makespan,best_bound,mean_bound,"
    "best_gap,mean_gap,mean_runtime_s,mean_solver_wall_time,statuses\n"
)


def test_load_cpsat_aggregates_validates_required_fields(tmp_path):
    invalid = tmp_path / "invalid.csv"
    invalid.write_text("instance_name,workers\nmk01.fjs,1\n", encoding="utf-8")

    try:
        load_cpsat_aggregates(invalid)
    except ValueError as exc:
        assert "missing required fields" in str(exc)
    else:
        raise AssertionError("expected missing-field rejection")


def test_cpsat_report_summarizes_workers_and_best_rows(tmp_path):
    summary = tmp_path / "summary.csv"
    summary.write_text(
        HEADER +
        "mk01.fjs,1,2,2,40,40.0,0.0,40,40.0,40.0,0.0,0.0,1.0,1.0,OPTIMAL:2\n"
        "mk01.fjs,auto,2,2,41,41.0,0.0,41,40.0,40.0,0.02,0.02,0.5,0.5,FEASIBLE:2\n"
        "mk02.fjs,1,2,2,31,31.0,0.0,31,3.0,3.0,0.9,0.9,3.0,3.0,FEASIBLE:2\n"
        "mk02.fjs,auto,2,2,30,30.5,0.5,31,20.0,20.0,0.333,0.344,3.0,3.0,FEASIBLE:2\n",
        encoding="utf-8",
    )

    rows = load_cpsat_aggregates(summary)
    references = {
        "mk01.fjs": BenchmarkReference("mk01.fjs", 40, 40),
        "mk02.fjs": BenchmarkReference("mk02.fjs", 26, 26),
    }
    worker_rows = summarize_by_worker(rows)
    best_rows = best_row_per_instance(rows)
    report = build_markdown_report(rows, references)

    assert len(rows) == 4
    assert [(row.workers, row.instances) for row in worker_rows] == [("1", 2), ("auto", 2)]
    assert [(row.instance_name, row.workers) for row in best_rows] == [
        ("mk01.fjs", "1"),
        ("mk02.fjs", "auto"),
    ]
    assert "Fully feasible aggregate rows: 4/4" in report
    assert "Best worker rows reaching the upstream FJSPLib upper bound: 1/2" in report
    assert "Rows reaching UB without a local optimality proof: 0/2" in report
    assert "mk02.fjs | auto | 30 | 26 | 26 | 0.153846 | no | no" in report


def test_validate_reference_coverage_rejects_mismatch(tmp_path):
    summary = tmp_path / "summary.csv"
    summary.write_text(
        HEADER +
        "mk01.fjs,1,2,2,40,40.0,0.0,40,40.0,40.0,0.0,0.0,1.0,1.0,OPTIMAL:2\n",
        encoding="utf-8",
    )
    rows = load_cpsat_aggregates(summary)

    try:
        validate_reference_coverage(rows, {})
    except ValueError as exc:
        assert "missing BKS reference" in str(exc)
    else:
        raise AssertionError("expected missing-reference rejection")


def test_write_markdown_report_creates_parent_directory(tmp_path):
    output = tmp_path / "nested" / "report.md"

    write_markdown_report(output, "# Report\n")

    assert output.read_text(encoding="utf-8") == "# Report\n"
