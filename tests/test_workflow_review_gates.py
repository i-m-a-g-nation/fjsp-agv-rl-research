from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from src.ai_workflow import LLMConfig, ResearchRAGStore, build_research_workflow


def _invoke(path: Path, value, config=None):
    cfg = LLMConfig(api_key="")
    with SqliteSaver.from_conn_string(str(path)) as saver:
        graph = build_research_workflow(ResearchRAGStore(project_root=path.parent, config=cfg), cfg, [],
                                        track="graduation", checkpointer=saver, review_required=True)
        return graph.invoke(value, config or {"configurable": {"thread_id": "test-run"}})


def _approve(result, decision="approve"):
    request = result["__interrupt__"][0].value
    return Command(resume={"stage": request["stage"], "artifact_hash": request["artifact_hash"],
                           "decision": decision, "reviewer": "test human", "note": "Reviewed for demonstration only"})


def test_three_reviews_persist_without_repeating_completed_extraction(tmp_path, monkeypatch):
    from src.ai_workflow import langgraph_pipeline as pipeline
    original = pipeline._heuristic_extract_paper
    calls = []
    def counted(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(pipeline, "_heuristic_extract_paper", counted)
    path = tmp_path / "state.sqlite"
    first = _invoke(path, {"paper_text": "Title: Note", "allow_network_fetch": False})
    assert first["__interrupt__"][0].value["stage"] == "scope"
    assert calls == []
    second = _invoke(path, _approve(first))
    assert second["__interrupt__"][0].value["stage"] == "evidence"
    request = second["__interrupt__"][0].value
    extraction = request["payload"]["extraction_report"]
    assert extraction["evidence_status"] == "unverified"
    assert extraction["evidence_audit"]["source"]["text_sha256"]
    assert extraction["evidence_audit"]["summary"]["all_claims_located"] is False
    from src.ai_workflow.review import artifact_hash
    assert request["artifact_hash"] == artifact_hash({key: value for key, value in request.items() if key != "artifact_hash"})
    third = _invoke(path, _approve(second))
    assert third["__interrupt__"][0].value["stage"] == "conclusion"
    final = _invoke(path, _approve(third))
    assert not final.get("__interrupt__")
    assert len(calls) == 1
    assert len(final["human_reviews"]) == 3
    assert final["acceptance"]["research_status"] == "not_achieved"
    assert final["extraction_report"]["evidence_status"] == "unverified"


def test_reject_scope_stops_before_experiment(tmp_path):
    path = tmp_path / "state.sqlite"
    first = _invoke(path, {"allow_network_fetch": False})
    rejected = _invoke(path, _approve(first, "reject"))
    assert rejected["overall_status"] == "REJECTED"
    assert not rejected.get("generated_code")


def test_evidence_review_never_labels_legacy_paper_a_cache_as_paper_b(tmp_path):
    import hashlib
    raw = "Title: Paper B\nDOI:10.1000/paper-b"
    paper = tmp_path / "paper.md"
    paper.write_text(raw, encoding="utf-8")
    cache = tmp_path / "papers" / "auto_fetched" / "paper.fulltext.md"
    cache.parent.mkdir(parents=True)
    cache.write_text("Title: Paper A\nDOI:10.1000/paper-a\nReward Function\n" + "Cached A. " * 200, encoding="utf-8")
    path = tmp_path / "state.sqlite"
    first = _invoke(path, {"paper_path": str(paper), "allow_network_fetch": False})
    second = _invoke(path, _approve(first))
    assert second["paper_text"] == raw
    request = second["__interrupt__"][0].value
    audit = request["payload"]["extraction_report"]["evidence_audit"]
    assert audit["source"]["text_sha256"] == hashlib.sha256(raw.encode()).hexdigest()


def test_wrong_artifact_hash_cannot_approve(tmp_path):
    path = tmp_path / "state.sqlite"
    _invoke(path, {"allow_network_fetch": False})
    with pytest.raises(ValueError, match="review decision"):
        _invoke(path, Command(resume={"stage": "scope", "artifact_hash": "wrong", "decision": "approve", "reviewer": "human"}))


def test_review_requires_persistent_checkpointer(tmp_path):
    with pytest.raises(ValueError, match="checkpointer"):
        build_research_workflow(ResearchRAGStore(project_root=tmp_path), review_required=True)
