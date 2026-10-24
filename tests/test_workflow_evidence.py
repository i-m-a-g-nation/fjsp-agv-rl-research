import pytest

from src.ai_workflow.schemas import CodebaseAlignmentSpec, MathematicalModelSpec, PaperExtractionReport, RLFormulationSpec


def report(**kwargs):
    return PaperExtractionReport(title="Test paper", problem_type="FJSP",
        math_model=MathematicalModelSpec(objectives=["Minimize makespan"]),
        rl_formulation=RLFormulationSpec(), codebase_alignment=CodebaseAlignmentSpec(), **kwargs)


def test_each_claim_requires_its_own_literal_source_reference():
    from src.ai_workflow.evidence import audit_claim_evidence
    text = "Introduction\nWe minimize the makespan.\nConclusion"
    result = audit_claim_evidence(report(claim_evidence=[{"field": "math_model.objectives", "item_index": 0,
                                "quote": "We minimize the makespan."}]), text)
    item = next(item for item in result.evidence_audit["claims"] if item["field"] == "math_model.objectives")
    assert item["status"] == "located_unreviewed"
    assert item["locations"][0]["line_start"] == 2
    assert item["locations"][0]["start"] == text.index("We minimize")
    assert result.evidence_status == "unverified"
    assert next(item for item in result.evidence_audit["claims"] if item["field"] == "problem_type")["status"] == "missing"


@pytest.mark.parametrize("quote,status", [("Invented quotation", "invalid"), ("We minimize makespan.", "ambiguous")])
def test_missing_or_repeated_text_is_not_verified(quote, status):
    from src.ai_workflow.evidence import audit_claim_evidence
    result = audit_claim_evidence(report(claim_evidence=[{"field": "math_model.objectives", "item_index": 0, "quote": quote}]),
                                  "We minimize makespan.\nWe minimize makespan.")
    assert result.evidence_audit["claims"][1]["status"] == status


def test_explicit_offset_disambiguates_and_cannot_be_forged():
    from src.ai_workflow.evidence import audit_claim_evidence
    text = "We minimize makespan.\nWe minimize makespan."
    reference = {"field": "math_model.objectives", "item_index": 0, "quote": "We minimize makespan.", "source_start": 22}
    result = audit_claim_evidence(report(claim_evidence=[reference]), text)
    assert result.evidence_audit["claims"][1]["locations"][0]["line_start"] == 2
    reference["source_start"] = 3
    assert audit_claim_evidence(report(claim_evidence=[reference]), text).evidence_audit["claims"][1]["status"] == "invalid"


def test_flat_quotes_wrong_indices_and_outside_context_cannot_supply_evidence():
    from src.ai_workflow.evidence import audit_claim_evidence
    text = "Prefix text.\nWe minimize makespan."
    flat = audit_claim_evidence(report(source_quotes=["We minimize makespan."]), text)
    assert flat.evidence_audit["claims"][1]["status"] == "missing"
    wrong = audit_claim_evidence(report(claim_evidence=[{"field": "math_model.objectives", "item_index": 5, "quote": "We minimize makespan."}]), text)
    assert wrong.evidence_audit["rejected_references"]
    outside = audit_claim_evidence(report(claim_evidence=[{"field": "math_model.objectives", "item_index": 0, "quote": "We minimize makespan."}]), text, visible_limit=12)
    assert outside.evidence_audit["claims"][1]["status"] == "invalid"


def test_empty_offline_report_is_not_fully_supported():
    from src.ai_workflow.evidence import audit_claim_evidence
    item = report()
    item.problem_type = "[缺失：未核实]"
    item.math_model.objectives = []
    audited = audit_claim_evidence(item, "")
    assert audited.evidence_audit["summary"]["status"] == "no_claims"
    assert not audited.evidence_audit["summary"]["all_claims_located"]


def test_matching_text_does_not_prove_semantic_support_or_trust_model_status():
    from src.ai_workflow.evidence import audit_claim_evidence
    item = report(evidence_status="verified", evidence_audit={"summary": {"all_claims_located": True}},
                  claim_evidence=[{"field": "math_model.objectives", "item_index": 0, "quote": "We maximize energy consumption."}])
    result = audit_claim_evidence(item, "We maximize energy consumption.")
    assert result.evidence_status == "unverified"
    assert not result.evidence_audit["summary"]["all_claims_located"]


def test_physical_pdf_pages_include_empty_pages_and_cache_prefix(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from src.ai_workflow.evidence import audit_claim_evidence
    from src.ai_workflow.evidence_sources import make_source_map
    pages = ["", "We minimize makespan.\nConstraints follow.", "Last physical page."]
    monkeypatch.setattr("pypdf.PdfReader", lambda path: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda value=value: value) for value in pages]))
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-test-fixture")
    text = "Cache metadata\n\n" + "\n\n".join(pages)
    source_map = make_source_map(text, source_path=tmp_path / "cache.md", pdf_path=pdf)
    result = audit_claim_evidence(report(claim_evidence=[{"field": "math_model.objectives", "item_index": 0, "quote": "We minimize makespan."}]), text, source_map=source_map)
    location = result.evidence_audit["claims"][1]["locations"][0]
    assert location["page_start"] == location["page_end"] == 2
    assert location["source_path"] == str(pdf)
    assert source_map["pdf_raw_sha256"]


def test_mismatched_pdf_never_produces_a_physical_page(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from src.ai_workflow.evidence_sources import make_source_map
    monkeypatch.setattr("pypdf.PdfReader", lambda path: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: "Different PDF body")]))
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-test-fixture")
    mapping = make_source_map("Cached text does not match the PDF.", source_path=tmp_path / "cache.md", pdf_path=pdf)
    assert mapping["pages"] == []
    assert mapping["warnings"]


def test_local_pdf_source_keeps_physical_coordinates_without_download_metadata(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from src.ai_workflow.evidence_sources import make_source_map
    text = "We minimize makespan."
    monkeypatch.setattr("pypdf.PdfReader", lambda path: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: text)]))
    pdf = tmp_path / "local.pdf"
    pdf.write_bytes(b"%PDF-local-fixture")
    mapping = make_source_map(text, source_path=pdf)
    assert mapping["pages"] == [{"page": 1, "start": 0, "end": len(text)}]
    assert mapping["pdf_source_path"] == str(pdf)


def test_downloaded_pdf_outer_whitespace_normalization_keeps_page_number(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from src.ai_workflow.evidence import audit_claim_evidence
    from src.ai_workflow.evidence_sources import make_source_map
    pages = ["", "\nWe minimize makespan.\n", ""]
    monkeypatch.setattr("pypdf.PdfReader", lambda path: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda value=value: value) for value in pages]))
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-fixture")
    text = "Downloaded PDF text:\n\n" + "\n\n".join(pages).strip()
    result = audit_claim_evidence(report(claim_evidence=[{"field": "math_model.objectives", "item_index": 0, "quote": "We minimize makespan."}]),
                                  text, source_map=make_source_map(text, pdf_path=pdf))
    assert result.evidence_audit["claims"][1]["locations"][0]["page_start"] == 2


def test_all_located_claims_still_require_semantic_review():
    from src.ai_workflow.evidence import audit_claim_evidence
    text = "This is an FJSP study. We minimize makespan."
    result = audit_claim_evidence(report(claim_evidence=[
        {"field": "problem_type", "quote": "This is an FJSP study."},
        {"field": "math_model.objectives", "item_index": 0, "quote": "We minimize makespan."},
    ]), text)
    assert result.evidence_audit["summary"]["all_claims_located"] is True
    assert result.evidence_status == "unverified"


def test_pdf_prefix_has_no_page_and_cross_page_quote_uses_physical_range(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from src.ai_workflow.evidence import audit_claim_evidence
    from src.ai_workflow.evidence_sources import make_source_map
    pages = ["We minimize", "makespan in the study."]
    monkeypatch.setattr("pypdf.PdfReader", lambda path: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda value=value: value) for value in pages]))
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-fixture")
    prefix = "Extra cached metadata."
    body = "\n\n".join(pages)
    text = prefix + "\n\n" + body
    result = audit_claim_evidence(report(claim_evidence=[
        {"field": "problem_type", "quote": prefix},
        {"field": "math_model.objectives", "item_index": 0, "quote": body},
    ]), text, source_map=make_source_map(text, pdf_path=pdf))
    claims = result.evidence_audit["claims"]
    assert claims[0]["locations"][0]["page_start"] is None
    assert claims[1]["locations"][0]["page_start"] == 1
    assert claims[1]["locations"][0]["page_end"] == 2


def test_source_map_cannot_be_reused_for_different_text():
    from src.ai_workflow.evidence import audit_claim_evidence
    from src.ai_workflow.evidence_sources import make_source_map
    with pytest.raises(ValueError, match="Source map"):
        audit_claim_evidence(report(), "Changed text", source_map=make_source_map("Original text"))


def test_changed_source_file_invalidates_its_recorded_identity(tmp_path):
    from src.ai_workflow.evidence_sources import make_source_map, assert_source_files_unchanged
    source = tmp_path / "paper.md"
    source.write_text("Original text", encoding="utf-8")
    mapping = make_source_map("Original text", source_path=source)
    assert_source_files_unchanged(mapping)
    source.write_text("Changed text", encoding="utf-8")
    with pytest.raises(ValueError, match="Evidence source"):
        assert_source_files_unchanged(mapping)


def test_mocked_llm_requests_per_claim_evidence_and_overwrites_fake_audit(monkeypatch):
    import json
    from types import SimpleNamespace
    from src.ai_workflow import LLMConfig
    from src.ai_workflow.langgraph_pipeline import _llm_extract_paper
    payload = report(claim_evidence=[{"field": "math_model.objectives", "item_index": 0, "quote": "We minimize makespan."}],
                     evidence_status="verified", evidence_audit={"claims": [{"status": "verified"}]}).model_dump()
    messages = []
    class FakeLLM:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
        def invoke(self, value):
            messages.extend(value)
            return SimpleNamespace(content=json.dumps(payload))
    monkeypatch.setattr("langchain_openai.ChatOpenAI", FakeLLM)
    item = _llm_extract_paper(LLMConfig(api_key="test"), "Paper", "We minimize makespan.", "full_text", [], "goal", [], [], [])
    assert "claim_evidence" in str(messages)
    assert item.evidence_audit["claims"][1]["status"] == "located_unreviewed"
    assert item.evidence_status == "unverified"


def test_report_renders_locations_missing_references_and_escaped_quotes():
    from src.ai_workflow.evidence import audit_claim_evidence
    text = "We minimize <script>alert(1)</script> | makespan."
    item = audit_claim_evidence(report(claim_evidence=[{"field": "math_model.objectives", "item_index": 0, "quote": text}]), text)
    md = item.to_markdown()
    assert "逐项原文证据" in md
    assert "located_unreviewed" in md and "missing" in md
    assert "<script>" not in md
    assert "&lt;script&gt;" in md
