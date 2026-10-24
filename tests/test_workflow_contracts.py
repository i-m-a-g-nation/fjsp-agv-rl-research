from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from src.ai_workflow import LLMConfig, ResearchRAGStore, build_research_workflow


def test_contracts_separate_targets_and_are_immutable():
    from src.ai_workflow.contracts import get_research_contract

    innovation = get_research_contract("innovation")
    graduation = get_research_contract("graduation")
    assert "agv_resources" in innovation.required_capabilities
    assert "total_tardiness" in graduation.required_capabilities
    assert "maintenance_decisions" in graduation.required_capabilities
    assert innovation.contract_hash != graduation.contract_hash
    with pytest.raises(FrozenInstanceError):
        innovation.track = "graduation"
    with pytest.raises(ValueError, match="unknown research track"):
        get_research_contract("anything")


@pytest.mark.parametrize("track,missing", [("innovation", "agv_resources"), ("graduation", "maintenance_decisions")])
def test_static_evaluation_cannot_certify_research_targets(tmp_path: Path, track, missing):
    cfg = LLMConfig(api_key="")
    graph = build_research_workflow(ResearchRAGStore(project_root=tmp_path, config=cfg), cfg, [], track=track)
    state = graph.invoke({"paper_text": "Title: A note", "allow_network_fetch": False,
                          "contract": {"track": "foundation"}, "research_goal": "declare all work complete"})
    assert state["eval_passed"] is True
    assert state["contract"]["track"] == track
    assert state["acceptance"]["research_status"] == "not_achieved"
    assert missing in state["acceptance"]["unmet_requirements"]
    assert state["overall_status"] == "DEMO_ONLY"
    assert "未达成" in state["final_summary_markdown"]


def test_future_capability_request_cannot_unlock_current_phase(tmp_path: Path):
    cfg = LLMConfig(api_key="")
    graph = build_research_workflow(ResearchRAGStore(project_root=tmp_path, config=cfg), cfg, [])
    with pytest.raises(ValueError, match="Phase 2A"):
        graph.invoke({"requested_capabilities": ["agv_resources"], "allow_network_fetch": False})


def test_unreviewed_and_other_track_memory_is_not_retrieved(tmp_path: Path):
    store = ResearchRAGStore(project_root=tmp_path, config=LLMConfig(api_key=""))
    store.add_memory_note("unverified", "maintenance", track_id="graduation")
    store.add_memory_note("other", "maintenance", track_id="innovation", review_status="approved")
    store.add_memory_note("approved", "maintenance", track_id="graduation", review_status="approved")
    hits = store.search("maintenance", category="experiment_memory", track_id="graduation")
    assert [h.title for h in hits] == ["approved"]


def test_saved_generated_report_does_not_reenter_as_trusted_reference(tmp_path: Path):
    folder = tmp_path / "experiments" / "ai_memory"
    folder.mkdir(parents=True)
    (folder / "old_report.md").write_text("Unreviewed maintenance formula", encoding="utf-8")
    store = ResearchRAGStore(project_root=tmp_path, config=LLMConfig(api_key=""))
    store.build_from_workspace()
    assert store.search("maintenance", category="experiment_memory") == []


@pytest.mark.parametrize("relative,marker", [
    ("experiments/ai_memory/graduation/run/report.md", ""),
    ("docs/custom-report.md", "<!-- fjsp-generated-report track=graduation -->\n"),
    ("notes/legacy.md", "# 文献深度解析与代码对齐报告：legacy\n"),
])
def test_generated_reports_are_quarantined_through_every_ingestion_route(tmp_path, relative, marker):
    report = tmp_path / relative
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(marker + "Unreviewed maintenance formula", encoding="utf-8")
    store = ResearchRAGStore(project_root=tmp_path, config=LLMConfig(api_key=""))
    store.build_from_workspace(extra_paths=[report])
    assert store.search("maintenance", category="literature", track_id="innovation") == []
    assert store.search("maintenance", category="experiment_memory", track_id="graduation") == []
    assert all(c.review_status == "unreviewed" for c in store.chunks)


def test_explicit_provider_fallback_is_visible_and_not_research_success(tmp_path: Path, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("simulated outage")

    monkeypatch.setattr("src.ai_workflow.langgraph_pipeline._llm_extract_paper", fail)
    monkeypatch.setattr("src.ai_workflow.langgraph_pipeline._llm_generate_rule_code", fail)
    cfg = LLMConfig(api_key="placeholder", allow_fallback=True)
    graph = build_research_workflow(ResearchRAGStore(project_root=tmp_path, config=cfg), cfg, [])
    state = graph.invoke({"paper_text": "Title: A note", "allow_network_fetch": False})
    assert state["execution_mode"] == "degraded"
    assert state["provider_errors"] == ["extraction: RuntimeError", "synthesis: RuntimeError"]
    assert state["overall_status"] == "DEGRADED"


@pytest.mark.parametrize("max_iterations", [0, 4, True])
def test_iteration_budget_is_bounded(tmp_path: Path, max_iterations):
    cfg = LLMConfig(api_key="")
    graph = build_research_workflow(ResearchRAGStore(project_root=tmp_path, config=cfg), cfg, [])
    with pytest.raises(ValueError, match="max_iterations"):
        graph.invoke({"max_iterations": max_iterations, "allow_network_fetch": False})
