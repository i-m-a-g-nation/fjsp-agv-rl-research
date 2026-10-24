from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import pytest

from src.ai_workflow import (
    LLMConfig,
    ResearchRAGStore,
    build_research_workflow,
    detect_content_depth,
    evaluate_generated_rule,
    extract_identifiers_from_stub,
    resolve_paper_content,
)
from src.ai_workflow.campus_auth import (
    discover_papers_online,
    download_pdf_with_campus_auth,
    load_campus_cookies,
)
from src.ai_workflow.config import load_dotenv_if_present
from src.ai_workflow.paper_fetcher import (
    _download_and_parse_pdf,
    _fetch_arxiv_abstract,
    _fetch_doi_or_title_metadata,
    _reconstruct_openalex_abstract,
)
from src.ai_workflow.sandbox import validate_generated_code_ast


def test_dotenv_loader_and_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        '# comment\nTEST_CUSTOM_KEY="val123"\nINVALID_LINE\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("TEST_CUSTOM_KEY", raising=False)
    load_dotenv_if_present(env_file)
    import os

    assert os.getenv("TEST_CUSTOM_KEY") == "val123"
    cfg = LLMConfig(api_key="sk-test")
    assert cfg.has_api_key is True


def test_rag_store_build_search_and_persistence(tmp_path: Path) -> None:
    sample_doc = tmp_path / "sample_paper.md"
    sample_doc.write_text(
        "# Dynamic FJSP with AGV and Preventive Maintenance\n"
        "Minimize total tardiness and makespan using PPO and action masking.",
        encoding="utf-8",
    )

    store = ResearchRAGStore(config=LLMConfig(api_key=""))
    count = store.build_from_workspace(extra_paths=[sample_doc])
    assert count > 10

    lit_hits = store.search("AGV preventive maintenance tardiness PPO", top_k=3, category="literature")
    assert len(lit_hits) > 0

    code_hits = store.search("check_feasibility ScheduleResult", top_k=3, category="codebase")
    assert len(code_hits) > 0

    store.add_memory_note("test_mem", "Reward oscillation fixed by potential function", review_status="approved")
    save_dir = tmp_path / "rag_idx"
    store.save(save_dir)

    loaded = ResearchRAGStore.load(save_dir)
    assert len(loaded.chunks) == len(store.chunks)
    mem_hits = loaded.search("potential function reward oscillation", top_k=2, category="experiment_memory")
    assert any(h.title == "test_mem" for h in mem_hits)


def test_paper_fetcher_stub_detection_and_mocked_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_text = (
        "# 论文快速筛选结果\n"
        "- 题目：Flexible Job Shop Scheduling via Dual Attention Network Based Reinforcement Learning\n"
        "- arXiv：https://arxiv.org/abs/2305.05119\n"
        "- DOI/链接：https://doi.org/10.1016/j.cie.2023.109718\n"
    )
    assert detect_content_depth(stub_text) == "metadata_only"
    assert detect_content_depth("word " * 150) == "abstract_only"

    title, arxiv_id, doi = extract_identifiers_from_stub(stub_text, fallback_title="fallback")
    assert "Dual Attention Network" in title
    assert arxiv_id == "2305.05119"
    assert doi == "10.1016/j.cie.2023.109718"

    # Offline guard
    res_offline = resolve_paper_content(
        paper_path=tmp_path / "stub.md",
        raw_text=stub_text,
        fallback_title="stub",
        download_dir=tmp_path / "downloads",
        allow_network=False,
    )
    assert res_offline.content_depth == "metadata_only"

    # Full-text input bypass
    long_text = "# Full Paper\n$$C_{\\max} = \\max C_j$$\nState Space and Reward Function:\n" + ("word " * 800)
    res_full = resolve_paper_content(
        paper_path=tmp_path / "full.md",
        raw_text=long_text,
        fallback_title="full",
        download_dir=tmp_path / "downloads",
        allow_network=False,
    )
    assert res_full.content_depth == "full_text"

    # Mock arXiv abstract + PDF download
    monkeypatch.setattr(
        "src.ai_workflow.paper_fetcher._fetch_arxiv_abstract",
        lambda aid, timeout_sec, logs: "Mocked arXiv abstract about FJSP and DRL.",
    )
    monkeypatch.setattr(
        "src.ai_workflow.paper_fetcher._download_and_parse_pdf",
        lambda url, target_pdf_path, timeout_sec, logs: (
            "Extracted full PDF text with State Space and Reward Function $$C_max$$ " * 80
        ),
    )
    res_arxiv = resolve_paper_content(
        paper_path=tmp_path / "arxiv_stub.md",
        raw_text=stub_text,
        fallback_title="arxiv_stub",
        download_dir=tmp_path / "downloads",
        allow_network=True,
    )
    assert res_arxiv.content_depth == "full_text"

    # Second call hits local cache
    res_cached = resolve_paper_content(
        paper_path=tmp_path / "arxiv_stub.md",
        raw_text=stub_text,
        fallback_title="arxiv_stub",
        download_dir=tmp_path / "downloads",
        allow_network=False,
    )
    assert res_cached.content_depth == "full_text"

    # DOI-only stub hitting Campus Auth full PDF
    doi_only_stub = "- 题目：DOI Paper\n- DOI/链接：https://doi.org/10.1016/j.cie.2023.109718\n"
    monkeypatch.setattr(
        "src.ai_workflow.paper_fetcher.download_pdf_with_campus_auth",
        lambda **kwargs: (True, "Campus PDF Full Text " * 200, ["Campus PDF OK"]),
    )
    res_campus_pdf = resolve_paper_content(
        paper_path=tmp_path / "doi_campus.md",
        raw_text=doi_only_stub,
        fallback_title="doi_campus",
        download_dir=tmp_path / "downloads_campus",
        allow_network=True,
    )
    assert res_campus_pdf.content_depth == "full_text"

    # DOI-only stub with mocked OpenAlex abstract fallback
    monkeypatch.setattr(
        "src.ai_workflow.paper_fetcher.download_pdf_with_campus_auth",
        lambda **kwargs: (False, "", ["No campus PDF"]),
    )
    monkeypatch.setattr(
        "src.ai_workflow.paper_fetcher._fetch_doi_or_title_metadata",
        lambda **kwargs: (None, "Retrieved official abstract text " * 30),
    )
    res_doi_abs = resolve_paper_content(
        paper_path=tmp_path / "doi_stub.md",
        raw_text=doi_only_stub,
        fallback_title="doi_stub",
        download_dir=tmp_path / "downloads2",
        allow_network=True,
    )
    assert res_doi_abs.content_depth == "abstract_only"

    # Reconstruct OpenAlex inverted index helper
    reconstructed = _reconstruct_openalex_abstract({"Flexible": [0], "job": [1], "shop": [2]})
    assert reconstructed == "Flexible job shop"


def test_paper_fetcher_low_level_http_helpers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResp:
        def __init__(self, status_code: int = 200, text: str = "", content: bytes = b"", json_data: Any = None) -> None:
            self.status_code = status_code
            self.text = text
            self.content = content
            self._json = json_data or {}

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError("HTTP error")

        def json(self) -> Any:
            return self._json

    xml_body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        "<entry><summary>Test arXiv summary text.</summary></entry>"
        "</feed>"
    )
    monkeypatch.setattr("requests.get", lambda *a, **kw: FakeResp(200, text=xml_body))
    logs: list[str] = []
    summary = _fetch_arxiv_abstract("2305.05119", timeout_sec=5, logs=logs)
    assert summary == "Test arXiv summary text."

    # Non-PDF response header check
    monkeypatch.setattr("requests.get", lambda *a, **kw: FakeResp(200, content=b"<html>not pdf</html>"))
    pdf_txt = _download_and_parse_pdf("https://example.com/a.pdf", tmp_path / "a.pdf", 5, logs)
    assert pdf_txt == ""

    # OpenAlex + Crossref + SemanticScholar metadata helper
    oa_json = {
        "open_access": {"oa_url": "https://example.com/oa.pdf"},
        "abstract_inverted_index": {"Dynamic": [0], "FJSP": [1]},
    }
    monkeypatch.setattr("requests.get", lambda *a, **kw: FakeResp(200, json_data=oa_json))
    oa_url, abs_txt = _fetch_doi_or_title_metadata("10.1016/test", "Test Title", 5, logs)
    assert oa_url == "https://example.com/oa.pdf"
    assert abs_txt == "Dynamic FJSP"


def test_campus_auth_cookies_download_and_discover(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "cookies": [
                    {"name": "sd_session", "value": "abc", "domain": ".sciencedirect.com", "path": "/"}
                ]
            }
        ),
        encoding="utf-8",
    )
    jar = load_campus_cookies(storage_state_path=state_file, cookies_txt_path=tmp_path / "none.txt")
    assert len(jar) == 1
    assert jar.get("sd_session") == "abc"

    class FakeResp:
        def __init__(self, status_code: int = 200, text: str = "", content: bytes = b"", json_data: Any = None) -> None:
            self.status_code = status_code
            self.text = text
            self.content = content
            self._json = json_data or {}

        def json(self) -> Any:
            return self._json

    # Mock Elsevier API returning a valid PDF
    monkeypatch.setattr("requests.get", lambda *a, **kw: FakeResp(200, content=b"%PDF-1.4 mock"))
    monkeypatch.setattr(
        "src.ai_workflow.campus_auth._extract_pdf_text",
        lambda pdf_path, logs: "Campus full text " * 100,
    )
    ok, text, logs = download_pdf_with_campus_auth(
        doi="10.1016/j.cie.2023.109718",
        title="Test",
        target_pdf_path=tmp_path / "out.pdf",
        elsevier_api_key="test_key",
        storage_state_path=state_file,
    )
    assert ok is True
    assert "Campus full text" in text

    # Mock discover_papers_online
    def fake_discover_get(url: str, **kwargs: Any) -> FakeResp:
        if "crossref" in url:
            return FakeResp(
                200,
                json_data={
                    "message": {
                        "items": [
                            {
                                "title": ["DFJSP with AGV"],
                                "container-title": ["CIE"],
                                "issued": {"date-parts": [[2024]]},
                                "is-referenced-by-count": 42,
                                "DOI": "10.1016/j.cie.2024.1",
                            }
                        ]
                    }
                },
            )
        xml_feed = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            "<entry><title>ArXiv DRL FJSP</title><id>http://arxiv.org/abs/2401.00001v1</id>"
            "<published>2024-01-01T00:00:00Z</published></entry></feed>"
        )
        return FakeResp(200, text=xml_feed)

    monkeypatch.setattr("requests.get", fake_discover_get)
    papers = discover_papers_online("FJSP AGV", max_results=2)
    assert len(papers) == 2
    assert papers[0]["doi"] == "10.1016/j.cie.2024.1"
    assert papers[1]["arxiv_id"] == "2401.00001v1"


def test_sandbox_ast_security_and_evaluation() -> None:
    bad_import_code = """
import os
def ai_select_candidate(candidates, instance, rng=None):
    return candidates[0]
"""
    with pytest.raises(ValueError, match="Disallowed import"):
        validate_generated_code_ast(bad_import_code)

    bad_call_code = """
def ai_select_candidate(candidates, instance, rng=None):
    eval("1+1")
    return candidates[0]
"""
    with pytest.raises(ValueError, match="Disallowed builtin call"):
        validate_generated_code_ast(bad_call_code)

    missing_fn_code = """
def wrong_name(candidates, instance, rng=None):
    return candidates[0]
"""
    with pytest.raises(ValueError, match="must define a function"):
        validate_generated_code_ast(missing_fn_code)

    valid_code = """
def ai_select_candidate(candidates, instance, rng=None):
    return min(candidates, key=lambda c: (c[5], c[6], c[0], c[1], c[2]))
"""
    res = evaluate_generated_rule(valid_code, benchmark_paths=[])
    assert res.passed is True
    assert res.avg_makespan > 0

    runtime_err_code = """
def ai_select_candidate(candidates, instance, rng=None):
    return 1 / 0
"""
    res_err = evaluate_generated_rule(runtime_err_code, benchmark_paths=[])
    assert res_err.passed is False
    assert "Runtime error" in res_err.error_message


def test_langgraph_research_workflow_end_to_end_and_strict_guard(tmp_path: Path) -> None:
    store = ResearchRAGStore(config=LLMConfig(api_key=""))
    store.build_from_workspace()

    workflow = build_research_workflow(
        rag_store=store,
        config=LLMConfig(api_key=""),
        benchmark_paths=[],
    )
    stub_text = "- 题目：Dynamic FJSP with AGV\n- DOI/链接：https://doi.org/10.1016/j.cie.2023.109718\n"

    with pytest.raises(RuntimeError, match="no full PDF text available"):
        workflow.invoke(
            {
                "research_goal": "Test strict guard",
                "paper_title": "stub_paper",
                "paper_text": stub_text,
                "allow_network_fetch": False,
                "strict_require_fulltext": True,
            }
        )

    final_state = workflow.invoke(
        {
            "research_goal": "研究平行机与柔性车间下生产任务、AGV物流与设备维护协同优化及强化学习状态奖励设计",
            "paper_title": "2023_dfjsp_itr_gnn_drl",
            "paper_text": stub_text,
            "allow_network_fetch": False,
            "max_iterations": 2,
        }
    )

    assert final_state["eval_passed"] is True
    assert final_state["content_depth"] == "metadata_only"
    assert "防幻觉审查提示" in final_state["final_summary_markdown"]
    assert "ai_select_candidate" in final_state["generated_code"]
    assert final_state["eval_metrics"]["avg_makespan"] > 0
