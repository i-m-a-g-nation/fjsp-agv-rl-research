import json

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from src.ai_workflow import LLMConfig, ResearchRAGStore, build_research_workflow


@pytest.fixture
def protocol_input(tmp_path):
    (tmp_path / "tiny.fjs").write_text("1 1 1\n2 1 1 3 1 1 2\n", encoding="utf-8")
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps({"schema_version": 1, "protocol_id": "tiny-v1", "phase": "Phase 2A",
        "instances": [{"id": "tiny", "path": "tiny.fjs"}], "event_types": ["machine_breakdown"],
        "rules": ["eft"], "seeds": [42], "timing_repetitions": 1}), encoding="utf-8")
    return {"experiment_protocol_path": str(path), "allow_network_fetch": False}


def approve(request):
    return {"stage": request["stage"], "artifact_hash": request["artifact_hash"], "decision": "approve",
            "reviewer": "synthetic test reviewer", "note": "Test fixture only, not scientific acceptance"}


@pytest.mark.parametrize("track", ["innovation", "graduation"])
def test_fixed_protocol_has_three_reviews_without_rag_models_or_generation(tmp_path, protocol_input, monkeypatch, track):
    from src.ai_workflow import langgraph_pipeline as pipeline
    def forbidden(*a, **k):
        raise AssertionError("Fixed protocol must not build RAG, call models or generate a selector")
    monkeypatch.setattr(ResearchRAGStore, "build_from_workspace", forbidden)
    monkeypatch.setattr(pipeline, "_llm_extract_paper", forbidden)
    monkeypatch.setattr(pipeline, "_llm_generate_rule_code", forbidden)
    monkeypatch.setattr(pipeline, "_offline_generate_rule_code", forbidden)
    config = {"configurable": {"thread_id": "protocol"}}
    with SqliteSaver.from_conn_string(str(tmp_path / "session.sqlite")) as saver:
        graph = build_research_workflow(ResearchRAGStore(tmp_path, LLMConfig(api_key="")), track=track,
            config=LLMConfig(api_key=""), checkpointer=saver, review_required=True, workspace_index_path=tmp_path / "rag_index")
        result = graph.invoke(protocol_input, config)
        for stage in ("scope", "evidence", "conclusion"):
            request = result["__interrupt__"][0].value
            assert request["stage"] == stage
            if stage == "scope":
                assert request["payload"]["experiment_protocol"]["expected_runs"] == 1
            result = graph.invoke(Command(resume=approve(request)), config)
        assert not result.get("__interrupt__")
        assert result["eval_passed"] is True
        assert result["acceptance"]["research_status"] == "not_achieved"
        assert result["protocol_result"]["passed_runs"] == 1
        assert not result.get("generated_code")
        assert not (tmp_path / "rag_index").exists()


def test_protocol_reject_stops_before_batch(tmp_path, protocol_input):
    from src.ai_workflow.sessions import run_session
    first = run_session(tmp_path / "run", track="foundation", config=LLMConfig(api_key=""), project_root=tmp_path,
                        input_state=protocol_input)
    decision = {**approve(first["pending_review"]), "decision": "reject"}
    result = run_session(tmp_path / "run", track="foundation", config=LLMConfig(api_key=""), decision=decision)
    assert result["status"] == "REJECTED"
    assert not (tmp_path / "run" / "protocol_run").exists()


@pytest.mark.parametrize("changed", ["protocol", "benchmark"])
def test_session_pins_protocol_and_its_declared_benchmarks(tmp_path, protocol_input, changed):
    from src.ai_workflow.sessions import run_session
    first = run_session(tmp_path / "run", track="foundation", config=LLMConfig(api_key=""), project_root=tmp_path,
                        input_state=protocol_input)
    if changed == "protocol":
        path = tmp_path / "protocol.json"
        payload = json.loads(path.read_text())
        payload["seeds"] = [43]
        path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        (tmp_path / "tiny.fjs").write_text("changed benchmark", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        run_session(tmp_path / "run", track="foundation", config=LLMConfig(api_key=""), decision=approve(first["pending_review"]))


def test_supervised_protocol_session_restores_between_all_three_reviews(tmp_path, protocol_input):
    from src.ai_workflow.sessions import run_session
    result = run_session(tmp_path / "run", track="graduation", config=LLMConfig(api_key=""), project_root=tmp_path,
                         input_state=protocol_input)
    for stage in ("scope", "evidence", "conclusion"):
        assert result["pending_review"]["stage"] == stage
        result = run_session(tmp_path / "run", track="graduation", config=LLMConfig(api_key=""), decision=approve(result["pending_review"]))
    assert result["status"] == "COMPLETED"
    assert result["budget"]["provider_calls"] == 0
    assert result["state"]["protocol_result"]["passed_runs"] == 1
    assert result["state"]["acceptance"]["research_status"] == "not_achieved"


def test_batch_artifact_change_prevents_conclusion_approval(tmp_path, protocol_input):
    from src.ai_workflow.sessions import run_session
    result = run_session(tmp_path / "run", track="foundation", config=LLMConfig(api_key=""), project_root=tmp_path,
                         input_state=protocol_input)
    for _ in range(2):
        result = run_session(tmp_path / "run", track="foundation", config=LLMConfig(api_key=""), decision=approve(result["pending_review"]))
    assert result["pending_review"]["stage"] == "conclusion"
    (tmp_path / "run" / "protocol_run" / "raw.csv").write_text("changed", encoding="utf-8")
    final = run_session(tmp_path / "run", track="foundation", config=LLMConfig(api_key=""), decision=approve(result["pending_review"]))
    assert final["status"] == "FAILED"


def test_protocol_cli_pauses_without_requiring_a_paper(tmp_path, protocol_input):
    from experiments.exp_018_ai_rag_workflow import main
    # Use a project-relative protocol in the real project for the real CLI.
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert main(["--track", "foundation", "--experiment-protocol", str(root / "experiments/protocols/phase2a_v1.json"),
                 "--session-dir", str(tmp_path / "cli")]) == 3
    request = json.loads((tmp_path / "cli" / "review-request.json").read_text(encoding="utf-8"))
    assert request["payload"]["experiment_protocol"]["expected_runs"] == 243


def test_fixed_protocol_refuses_live_mode_before_loading_credentials(tmp_path, protocol_input, monkeypatch):
    from experiments import exp_018_ai_rag_workflow as cli
    def forbidden():
        raise AssertionError("Fixed protocol must not load credentials")
    monkeypatch.setattr(cli, "load_dotenv_if_present", forbidden)
    assert cli.main(["--track", "foundation", "--mode", "live", "--experiment-protocol", protocol_input["experiment_protocol_path"]]) == 1
