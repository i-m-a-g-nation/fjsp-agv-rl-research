from pathlib import Path

import pytest

from src.ai_workflow import LLMConfig


def _decision(result, value="approve"):
    request = result["pending_review"]
    return {"stage": request["stage"], "artifact_hash": request["artifact_hash"],
            "reviewer": "test human", "decision": value, "note": "Foundation experiment only"}


def _start(tmp_path, **kwargs):
    from src.ai_workflow.sessions import run_session
    return run_session(tmp_path / "run", track="graduation", project_root=tmp_path,
                       config=LLMConfig(api_key=""), benchmark_paths=[],
                       input_state={"paper_text": "Title: Note", "allow_network_fetch": False}, **kwargs)


def test_session_restarts_and_keeps_review_and_budget_history(tmp_path):
    from src.ai_workflow.sessions import run_session, read_session_status
    first = _start(tmp_path)
    assert first["status"] == "WAITING_HUMAN"
    assert first["pending_review"]["stage"] == "scope"
    for stage in ("evidence", "conclusion", None):
        next_result = run_session(tmp_path / "run", track="graduation", config=LLMConfig(api_key=""), decision=_decision(first))
        assert next_result["budget"]["active_seconds"] >= first["budget"]["active_seconds"]
        assert next_result["budget"]["provider_calls"] == 0
        if stage is not None:
            assert next_result["pending_review"]["stage"] == stage
        first = next_result
    assert first["status"] == "COMPLETED"
    assert first["state"]["acceptance"]["research_status"] == "not_achieved"
    assert read_session_status(tmp_path / "run")["status"] == "COMPLETED"
    assert (tmp_path / "run" / "decision-template.json").is_file()


def test_stale_review_and_wrong_track_do_not_resume(tmp_path):
    from src.ai_workflow.sessions import run_session
    first = _start(tmp_path)
    wrong = _decision(first)
    wrong["artifact_hash"] = "changed"
    with pytest.raises(ValueError, match="review decision"):
        run_session(tmp_path / "run", track="graduation", config=LLMConfig(api_key=""), decision=wrong)
    with pytest.raises(ValueError, match="track"):
        run_session(tmp_path / "run", track="innovation", config=LLMConfig(api_key=""), decision=_decision(first))


def test_rejected_session_is_terminal(tmp_path):
    from src.ai_workflow.sessions import run_session
    first = _start(tmp_path)
    rejected = run_session(tmp_path / "run", track="graduation", config=LLMConfig(api_key=""), decision=_decision(first, "reject"))
    assert rejected["status"] == "REJECTED"
    with pytest.raises(ValueError, match="terminal"):
        run_session(tmp_path / "run", track="graduation", config=LLMConfig(api_key=""), decision=_decision(first))


def test_outer_deadline_stops_worker_and_persists_exhaustion(tmp_path):
    from src.ai_workflow.runtime_budget import BudgetLimits
    result = _start(tmp_path, limits=BudgetLimits(max_active_seconds=0.1))
    assert result["status"] == "BUDGET_EXHAUSTED"


def test_config_cannot_change_on_resume(tmp_path):
    from src.ai_workflow.sessions import run_session
    first = _start(tmp_path)
    with pytest.raises(ValueError, match="configuration"):
        run_session(tmp_path / "run", track="graduation", config=LLMConfig(api_key="", max_output_tokens=100), decision=_decision(first))


def test_changed_paper_invalidates_scope_approval(tmp_path):
    from src.ai_workflow.sessions import run_session
    paper = tmp_path / "paper.md"
    paper.write_text("Original paper", encoding="utf-8")
    first = run_session(tmp_path / "run", track="graduation", config=LLMConfig(api_key=""), project_root=tmp_path,
                        benchmark_paths=[], input_state={"paper_path": str(paper), "paper_text": "", "allow_network_fetch": False})
    paper.write_text("Changed paper", encoding="utf-8")
    second = run_session(tmp_path / "run", track="graduation", config=LLMConfig(api_key=""), decision=_decision(first))
    assert second["status"] == "FAILED"


def test_changed_resolved_cache_invalidates_evidence_approval(tmp_path):
    from src.ai_workflow.sessions import run_session
    from src.ai_workflow.paper_fetcher import _write_resolved_cache, _cache_request_identity
    paper = tmp_path / "paper.md"
    paper.write_text("Title: Local cached study", encoding="utf-8")
    cache = tmp_path / "papers" / "auto_fetched" / "paper.fulltext.md"
    cache.parent.mkdir(parents=True)
    _write_resolved_cache(cache, "We minimize makespan in this study.", "full_text", None, None,
                          request_identity=_cache_request_identity(paper.read_text(encoding="utf-8"), "Local cached study", None, None))
    cfg = LLMConfig(api_key="")
    first = run_session(tmp_path / "run", track="graduation", config=cfg, project_root=tmp_path,
                        benchmark_paths=[], input_state={"paper_path": str(paper), "allow_network_fetch": False})
    second = run_session(tmp_path / "run", track="graduation", config=cfg, decision=_decision(first))
    assert second["pending_review"]["stage"] == "evidence"
    evidence = second["pending_review"]["payload"]["extraction_report"]["evidence_audit"]
    assert evidence["source"]["source_path"] == str(cache)
    cache.write_text("Changed resolved source", encoding="utf-8")
    third = run_session(tmp_path / "run", track="graduation", config=cfg, decision=_decision(second))
    assert third["status"] == "FAILED"


def test_credentials_are_not_persisted_and_zero_quota_does_not_fallback(tmp_path):
    from src.ai_workflow.sessions import run_session
    from src.ai_workflow.runtime_budget import BudgetLimits
    key = "audit-placeholder-secret-must-not-be-persisted"
    cfg = LLMConfig(api_key=key, allow_fallback=True, embedding_backend="hybrid_local")
    first = run_session(tmp_path / "run", track="graduation", config=cfg, project_root=tmp_path,
                        benchmark_paths=[], limits=BudgetLimits(max_provider_calls=0),
                        input_state={"paper_text": "Title: note", "allow_network_fetch": False})
    assert first["status"] == "WAITING_HUMAN"
    for path in (tmp_path / "run").rglob("*"):
        if path.is_file():
            assert key.encode() not in path.read_bytes()
    second = run_session(tmp_path / "run", track="graduation", config=cfg, decision=_decision(first))
    assert second["status"] == "BUDGET_EXHAUSTED"
    assert second["budget"]["provider_calls"] == 0


def test_new_session_rejects_preexisting_unassociated_rag(tmp_path):
    from src.ai_workflow.sessions import run_session
    folder = tmp_path / "run" / "rag_index"
    folder.mkdir(parents=True)
    (folder / "chunks.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="Unexpected session artifacts"):
        run_session(tmp_path / "run", track="graduation", config=LLMConfig(api_key=""),
                    input_state={"allow_network_fetch": False})


def test_resume_rejects_changed_benchmark_and_workspace(tmp_path):
    from src.ai_workflow.sessions import run_session
    benchmark = tmp_path / "tiny.fjs"
    benchmark.write_text("1 1\n1 1 1 3\n", encoding="utf-8")
    first = run_session(tmp_path / "run", track="graduation", config=LLMConfig(api_key=""), project_root=tmp_path,
                        benchmark_paths=[benchmark], input_state={"allow_network_fetch": False})
    benchmark.write_text("1 1\n1 1 1 9\n", encoding="utf-8")
    with pytest.raises(ValueError, match="benchmark"):
        run_session(tmp_path / "run", track="graduation", config=LLMConfig(api_key=""), decision=_decision(first))
    benchmark.write_text("1 1\n1 1 1 3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="workspace"):
        run_session(tmp_path / "run", track="graduation", project_root=tmp_path / "other",
                    config=LLMConfig(api_key=""), decision=_decision(first))


def test_stale_status_cannot_reject_already_completed_gate(tmp_path):
    import json
    from src.ai_workflow.sessions import run_session
    first = _start(tmp_path)
    old = dict(first)
    run_session(tmp_path / "run", track="graduation", config=LLMConfig(api_key=""), decision=_decision(first, "reject"))
    (tmp_path / "run" / "status.json").write_text(json.dumps(old), encoding="utf-8")
    result = run_session(tmp_path / "run", track="graduation", config=LLMConfig(api_key=""), decision=_decision(old))
    assert result["status"] == "FAILED"


def test_missing_associated_vectors_are_not_implicitly_rebuilt(tmp_path):
    from src.ai_workflow.sessions import run_session
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "reference.md").write_text("FJSP reference text", encoding="utf-8")
    first = _start(tmp_path)
    second = run_session(tmp_path / "run", track="graduation", config=LLMConfig(api_key=""), decision=_decision(first))
    (tmp_path / "run" / "rag_index" / "index.faiss").unlink()
    third = run_session(tmp_path / "run", track="graduation", config=LLMConfig(api_key=""), decision=_decision(second))
    assert third["status"] == "FAILED"
