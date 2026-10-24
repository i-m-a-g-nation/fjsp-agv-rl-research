import json
from pathlib import Path

import pytest

from experiments.exp_018_ai_rag_workflow import main, parse_args


def test_cli_requires_explicit_track():
    with pytest.raises(SystemExit):
        parse_args([])


def test_cli_defaults_to_offline_without_network():
    args = parse_args(["--track", "innovation"])
    assert args.mode == "offline"
    assert not args.allow_network_fetch


def test_offline_research_report_is_incomplete_not_success(tmp_path: Path):
    paper = tmp_path / "note.md"
    paper.write_text("Title: A note", encoding="utf-8")
    output = tmp_path / "graduation" / "report.md"
    session = tmp_path / "session"
    common = ["--track", "graduation", "--session-dir", str(session), "--output-report", str(output)]
    assert main([*common, "--paper-path", str(paper)]) == 3
    for index in range(3):
        decision = json.loads((session / "decision-template.json").read_text(encoding="utf-8"))
        decision.update(decision="approve", reviewer="test human", note="Offline demonstration only")
        decision_path = tmp_path / f"decision-{index}.json"
        decision_path.write_text(json.dumps(decision), encoding="utf-8")
        code = main([*common, "--decision-file", str(decision_path)])
        assert code == (2 if index == 2 else 3)
    assert code == 2
    metadata = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    assert metadata["contract"]["track"] == "graduation"
    assert metadata["overall_status"] == "DEMO_ONLY"
    assert metadata["acceptance"]["research_status"] == "not_achieved"
    assert metadata["acceptance"]["unmet_requirements"]


def test_status_command_does_not_execute_worker(tmp_path: Path):
    folder = tmp_path / "session"
    folder.mkdir()
    (folder / "status.json").write_text(json.dumps({"status": "WAITING_HUMAN", "budget": {"provider_calls": 0}}), encoding="utf-8")
    assert main(["--track", "graduation", "--session-dir", str(folder), "--status"]) == 0


def test_decision_requires_existing_session(tmp_path: Path):
    assert main(["--track", "graduation", "--decision-file", str(tmp_path / "decision.json")]) == 1


def test_paper_parsing_is_inside_supervised_worker(tmp_path, monkeypatch):
    paper = tmp_path / "paper.md"
    paper.write_text("Title: note", encoding="utf-8")
    def fail(*args, **kwargs):
        raise AssertionError("Paper parsing escaped the supervised process")
    monkeypatch.setattr("src.ai_workflow.rag_store.ResearchRAGStore._read_file_text", fail)
    assert main(["--track", "graduation", "--paper-path", str(paper), "--session-dir", str(tmp_path / "run")]) == 3


def test_explicit_network_override_on_resume_is_rejected(tmp_path):
    paper = tmp_path / "paper.md"
    paper.write_text("Title: note", encoding="utf-8")
    folder = tmp_path / "run"
    common = ["--track", "graduation", "--session-dir", str(folder)]
    assert main([*common, "--paper-path", str(paper), "--allow-network-fetch"]) == 3
    assert main([*common, "--no-network-fetch"]) == 1


def test_live_mode_without_key_fails_before_network(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert main(["--track", "innovation", "--mode", "live"]) == 1
