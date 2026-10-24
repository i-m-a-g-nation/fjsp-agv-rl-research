import csv
import hashlib
import json

import pytest


@pytest.fixture
def batch_input(tmp_path):
    benchmark = tmp_path / "tiny.fjs"
    benchmark.write_text("1 1 1\n2 1 1 3 1 1 2\n", encoding="utf-8")
    payload = {"schema_version": 1, "protocol_id": "tiny-v1", "phase": "Phase 2A",
               "instances": [{"id": "tiny", "path": "tiny.fjs"}],
               "event_types": ["machine_breakdown", "job_arrival", "processing_time_change"],
               "rules": ["fifo", "spt", "eft"], "seeds": [42], "timing_repetitions": 2}
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps(payload), encoding="utf-8")
    return protocol, benchmark


def read_rows(folder):
    with (folder / "raw.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_batch_replay_preserves_schedules_and_independent_case_denominator(tmp_path, batch_input):
    from src.research.batch import run_protocol
    protocol, benchmark = batch_input
    first = run_protocol(protocol, tmp_path / "a", tmp_path, plots=False)
    second = run_protocol(protocol, tmp_path / "b", tmp_path, plots=False)
    assert first["status"] == "COMPLETED"
    assert (first["expected_runs"], first["passed_runs"], first["failed_runs"]) == (18, 18, 0)
    assert first["case_count"] == 3
    assert first["deterministic_digest"] == second["deterministic_digest"]
    rows = read_rows(tmp_path / "a")
    assert len(rows) == 18
    assert {r["makespan"] for r in rows if r["event_type"] == "machine_breakdown"} == {"6"}
    assert {r["makespan"] for r in rows if r["event_type"] == "job_arrival"} == {"10"}
    assert {r["makespan"] for r in rows if r["event_type"] == "processing_time_change"} == {"6"}
    assert len(first["groups"]) == 9
    assert all(g["expected_runs"] == g["passed_runs"] == 2 for g in first["groups"])
    assert first["input_hashes"]["tiny"] == hashlib.sha256(benchmark.read_bytes()).hexdigest()


@pytest.mark.parametrize("failure", ["static", "dynamic", "exception"])
def test_invalid_or_failed_solver_runs_remain_in_report_and_have_no_accepted_makespan(tmp_path, batch_input, monkeypatch, failure):
    from src.research import batch
    original = batch.reschedule_from_state
    def broken(*args, **kwargs):
        if failure == "exception":
            raise RuntimeError("deliberate solver failure")
        result = original(*args, **kwargs)
        if failure == "static":
            result.records[0].end += 1
        else:
            for record in result.records:
                record.start += 1
                record.end += 1
            result.compute_makespan()
        return result
    monkeypatch.setattr(batch, "reschedule_from_state", broken)
    result = batch.run_protocol(batch_input[0], tmp_path / "failed", tmp_path, plots=False)
    assert result["status"] == "FAILED"
    assert (result["passed_runs"], result["failed_runs"]) == (0, 18)
    rows = read_rows(tmp_path / "failed")
    assert len(rows) == 18
    assert all(row["makespan"] == "" and row["error"] for row in rows)
    expected_error = {"static": "static=", "dynamic": "FROZEN_RECORD_CHANGED", "exception": "deliberate solver failure"}[failure]
    assert all(expected_error in row["error"] for row in rows)
    assert (tmp_path / "failed" / "report.md").exists()


def test_case_preparation_failures_are_counted_in_the_full_declared_grid(tmp_path, batch_input):
    from src.research.batch import run_protocol
    batch_input[1].write_text("1 1 1\n1 1 1 3\n", encoding="utf-8")
    result = run_protocol(batch_input[0], tmp_path / "partial", tmp_path, plots=False)
    assert (result["expected_runs"], result["passed_runs"], result["failed_runs"]) == (18, 6, 12)
    assert len(read_rows(tmp_path / "partial")) == 18


def test_output_reuse_is_rejected_without_touching_existing_evidence(tmp_path, batch_input):
    from src.research.batch import run_protocol
    output = tmp_path / "existing"
    output.mkdir()
    (output / "sentinel").write_text("preserve", encoding="utf-8")
    with pytest.raises(FileExistsError):
        run_protocol(batch_input[0], output, tmp_path, plots=False)
    assert list(p.name for p in output.iterdir()) == ["sentinel"]


@pytest.mark.parametrize("changed", ["protocol", "input"])
def test_expected_hash_mismatch_stops_before_experiment_output(tmp_path, batch_input, changed):
    from src.research.batch import run_protocol
    kwargs = {"expected_protocol_hash": "not-the-protocol"} if changed == "protocol" else {
        "expected_input_hashes": {str(batch_input[1].resolve()): "not-the-input"}}
    with pytest.raises(ValueError, match="changed"):
        run_protocol(batch_input[0], tmp_path / "blocked", tmp_path, plots=False, **kwargs)
    assert not (tmp_path / "blocked").exists()


def test_representative_plots_are_selected_by_protocol_not_best_result(tmp_path, batch_input):
    from src.research.batch import run_protocol
    run_protocol(batch_input[0], tmp_path / "plotted", tmp_path, plots=True)
    pictures = list((tmp_path / "plotted" / "gantt").glob("*.png"))
    assert len(pictures) == 3
    assert all(path.name.endswith("-eft.png") and path.read_bytes().startswith(b"\x89PNG") for path in pictures)


def test_batch_cli_reports_success_and_refuses_overwrite(tmp_path, batch_input):
    from experiments.exp_019_phase2a_protocol import main
    args = ["--protocol", str(batch_input[0]), "--project-root", str(tmp_path), "--output-dir", str(tmp_path / "cli"), "--no-plots"]
    assert main(args) == 0
    assert main(args) == 1
