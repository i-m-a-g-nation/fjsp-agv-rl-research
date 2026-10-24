from pathlib import Path

import pytest

from src.ai_workflow import LLMConfig, ResearchRAGStore, build_research_workflow
from src.ai_workflow.langgraph_pipeline import _heuristic_extract_paper
from src.ai_workflow.paper_fetcher import detect_content_depth, resolve_paper_content


@pytest.mark.parametrize("kwargs", [{"request_timeout_seconds": float("inf")}, {"max_output_tokens": 0}, {"max_retries": 10}])
def test_model_call_budget_has_hard_bounds(kwargs):
    with pytest.raises(ValueError, match="budget"):
        LLMConfig(**kwargs)


def test_embedding_outage_is_not_silently_hidden(monkeypatch):
    from types import SimpleNamespace
    from src.ai_workflow.rag_store import LocalEmbeddingsProvider

    def fail(**kwargs):
        raise RuntimeError("embedding outage")

    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: SimpleNamespace(embeddings=SimpleNamespace(create=fail)))
    provider = LocalEmbeddingsProvider(LLMConfig(api_key="test", embedding_backend="openai"))
    with pytest.raises(RuntimeError, match="Embedding request failed"):
        provider.embed_texts(["a document"])


def test_long_prose_does_not_prove_full_text():
    assert detect_content_depth("Ordinary prose without methods or equations. " * 120) != "full_text"


@pytest.mark.parametrize("tamper", [False, True])
def test_pdf_cache_preserves_acquisition_provenance_and_checks_integrity(tmp_path, monkeypatch, tamper):
    monkeypatch.setattr("src.ai_workflow.paper_fetcher._fetch_arxiv_abstract", lambda *a, **k: "")
    monkeypatch.setattr("src.ai_workflow.paper_fetcher._download_and_parse_pdf", lambda **k: "Extracted ordinary PDF prose. " * 200)
    kwargs = dict(paper_path=tmp_path / "paper.md", raw_text="arXiv:2305.05119",
                  fallback_title="paper", download_dir=tmp_path / "downloads")
    first = resolve_paper_content(**kwargs, allow_network=True)
    assert first.content_depth == "full_text"
    if tamper:
        first.cached_fulltext_path.write_text("Changed cached prose. " * 200, encoding="utf-8")
    second = resolve_paper_content(**kwargs, allow_network=False)
    assert second.content_depth == ("metadata_only" if tamper else "full_text")


@pytest.mark.parametrize("same_path", [False, True])
def test_title_only_request_cannot_reuse_another_papers_acquisition(tmp_path, monkeypatch, same_path):
    monkeypatch.setattr("src.ai_workflow.paper_fetcher._fetch_doi_or_title_metadata", lambda **k: (None, "Official abstract of paper A. " * 50))
    common = dict(fallback_title="paper", download_dir=tmp_path / "downloads")
    first = resolve_paper_content(paper_path=tmp_path / "a" / "paper.md", raw_text="Title: Paper A", **common, allow_network=True)
    assert first.content_depth == "abstract_only"
    second = resolve_paper_content(paper_path=tmp_path / ("a" if same_path else "b") / "paper.md",
                                   raw_text="Title: Paper B", **common, allow_network=False)
    assert second.resolved_text == "Title: Paper B"
    assert second.content_depth == "metadata_only"


def test_legacy_cache_cannot_replace_a_different_doi(tmp_path):
    cache = tmp_path / "downloads" / "paper.fulltext.md"
    cache.parent.mkdir()
    cache.write_text("Title: Paper A\nDOI:10.1000/paper-a\nReward Function\n" + "Cached paper A. " * 120, encoding="utf-8")
    raw = "Title: Paper B\nDOI:10.1000/paper-b"
    result = resolve_paper_content(paper_path=tmp_path / "paper.md", raw_text=raw,
                                  fallback_title="paper", download_dir=cache.parent, allow_network=False)
    assert result.resolved_text == raw
    assert result.cached_fulltext_path is None


def test_identifier_free_version_one_cache_is_not_sufficiently_bound(tmp_path):
    from src.ai_workflow.paper_fetcher import _write_resolved_cache
    cache = tmp_path / "downloads" / "paper.fulltext.md"
    cache.parent.mkdir()
    _write_resolved_cache(cache, "Previously acquired but unbound paper A.", "full_text", None, None)
    result = resolve_paper_content(paper_path=tmp_path / "paper.md", raw_text="Title: Paper B",
                                  fallback_title="paper", download_dir=cache.parent, allow_network=False)
    assert result.content_depth == "metadata_only"


def test_identifier_bound_version_one_cache_remains_usable(tmp_path):
    from src.ai_workflow.paper_fetcher import _write_resolved_cache
    cache = tmp_path / "downloads" / "paper.fulltext.md"
    cache.parent.mkdir()
    _write_resolved_cache(cache, "Previously acquired PDF body", "full_text", None, "10.1000/paper-a")
    result = resolve_paper_content(paper_path=tmp_path / "paper.md", raw_text="DOI:10.1000/paper-a",
                                  fallback_title="paper", download_dir=cache.parent, allow_network=False)
    assert result.content_depth == "full_text"
    assert result.resolved_text == "Previously acquired PDF body"


@pytest.mark.parametrize("tamper_pdf", [False, True])
def test_bound_pdf_cache_preserves_pages_only_for_its_original_pdf(tmp_path, monkeypatch, tamper_pdf):
    from types import SimpleNamespace
    from src.ai_workflow.evidence_sources import make_source_map
    body = "We minimize makespan. " * 100
    monkeypatch.setattr("src.ai_workflow.paper_fetcher._fetch_doi_or_title_metadata", lambda **k: ("https://example.test/paper.pdf", ""))
    def download(**kwargs):
        kwargs["target_pdf_path"].write_bytes(b"%PDF-original-fixture")
        return body
    monkeypatch.setattr("src.ai_workflow.paper_fetcher._download_and_parse_pdf", download)
    monkeypatch.setattr("pypdf.PdfReader", lambda path: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: body)]))
    kwargs = dict(paper_path=tmp_path / "paper.md", raw_text="Title: Paper A",
                  fallback_title="paper", download_dir=tmp_path / "downloads")
    first = resolve_paper_content(**kwargs, allow_network=True)
    if tamper_pdf:
        first.downloaded_pdf_path.write_bytes(b"%PDF-replacement-fixture")
    second = resolve_paper_content(**kwargs, allow_network=False)
    assert second.content_depth == "full_text"
    if tamper_pdf:
        assert second.downloaded_pdf_path is None
    else:
        mapping = make_source_map(second.resolved_text, source_path=second.cached_fulltext_path, pdf_path=second.downloaded_pdf_path)
        assert mapping["pages"][0]["page"] == 1


def test_offline_extraction_never_invents_paper_formulas():
    report = _heuristic_extract_paper("A paper", "Some text", "full_text", [], "audit", [])
    assert report.math_model.objectives == []
    assert "缺失" in report.rl_formulation.reward_function
    assert report.rl_formulation.network_architecture == ""
    assert report.extraction_method == "unverified_template"
    assert report.missing_warnings


def test_provider_outage_fails_instead_of_silently_using_template(tmp_path: Path, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("simulated outage")

    monkeypatch.setattr("src.ai_workflow.langgraph_pipeline._llm_extract_paper", fail)
    cfg = LLMConfig(api_key="test-placeholder", embedding_backend="hybrid_local")
    graph = build_research_workflow(ResearchRAGStore(project_root=tmp_path, config=cfg), cfg, [])
    with pytest.raises(RuntimeError, match="extraction failed"):
        graph.invoke({"paper_text": "Title: A paper", "allow_network_fetch": False})
