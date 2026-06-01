from experiments.exp_011_heuristic_quality_report import BenchmarkReference
from experiments.exp_012_benchmark_metadata_audit import (
    audit_benchmark_metadata,
    main,
    write_metadata_audit_csv,
)


VALID_BENCHMARK = "1 1 1 1 1 1 1"


def test_audit_benchmark_metadata_accepts_matching_loadable_file(tmp_path):
    (tmp_path / "mk01.fjs").write_text(VALID_BENCHMARK, encoding="utf-8")
    references = {"mk01.fjs": BenchmarkReference("mk01.fjs", 1, 1)}

    rows = audit_benchmark_metadata(tmp_path, references)

    assert len(rows) == 1
    assert rows[0].to_csv_row() == {
        "instance_name": "mk01.fjs",
        "file_tracked": "PASS",
        "bks_recorded": "PASS",
        "loadable": "PASS",
        "fjsplib_lb": "1",
        "fjsplib_ub": "1",
        "status": "PASS",
        "note": "PASS",
    }


def test_audit_benchmark_metadata_reports_missing_bks_row(tmp_path):
    (tmp_path / "mk01.fjs").write_text(VALID_BENCHMARK, encoding="utf-8")

    row = audit_benchmark_metadata(tmp_path, {})[0]

    assert row.file_tracked
    assert row.loadable
    assert not row.bks_recorded
    assert row.status == "FAIL"
    assert row.note == "BKS metadata row is missing"


def test_audit_benchmark_metadata_reports_missing_file(tmp_path):
    references = {"mk01.fjs": BenchmarkReference("mk01.fjs", 1, 1)}

    row = audit_benchmark_metadata(tmp_path, references)[0]

    assert not row.file_tracked
    assert row.bks_recorded
    assert not row.loadable
    assert row.status == "FAIL"
    assert row.note == "tracked benchmark file is missing"


def test_audit_benchmark_metadata_reports_loader_failure(tmp_path):
    (tmp_path / "broken.fjs").write_text("not a benchmark", encoding="utf-8")
    references = {"broken.fjs": BenchmarkReference("broken.fjs", 1, 1)}

    row = audit_benchmark_metadata(tmp_path, references)[0]

    assert row.file_tracked
    assert row.bks_recorded
    assert not row.loadable
    assert row.status == "FAIL"
    assert row.note.startswith("benchmark loader failed:")


def test_write_metadata_audit_csv_uses_stable_fields(tmp_path):
    (tmp_path / "mk01.fjs").write_text(VALID_BENCHMARK, encoding="utf-8")
    references = {"mk01.fjs": BenchmarkReference("mk01.fjs", 1, 1)}
    rows = audit_benchmark_metadata(tmp_path, references)
    output = tmp_path / "audit.csv"

    write_metadata_audit_csv(output, rows)

    assert output.read_text(encoding="utf-8").startswith(
        "instance_name,file_tracked,bks_recorded,loadable"
    )
    assert "mk01.fjs,PASS,PASS,PASS,1,1,PASS,PASS" in output.read_text(
        encoding="utf-8"
    )


def test_main_returns_failure_for_metadata_mismatch(tmp_path):
    input_dir = tmp_path / "instances"
    input_dir.mkdir()
    (input_dir / "mk01.fjs").write_text(VALID_BENCHMARK, encoding="utf-8")
    bks_input = tmp_path / "bks.csv"
    bks_input.write_text(
        "instance_name,fjsplib_lb,fjsplib_ub\n"
        "missing.fjs,1,1\n",
        encoding="utf-8",
    )
    output = tmp_path / "audit.csv"

    exit_code = main(
        [
            "--input-dir",
            str(input_dir),
            "--bks-input",
            str(bks_input),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    assert output.is_file()
