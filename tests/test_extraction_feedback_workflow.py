"""Real graph routing with controlled extraction; no provider/network requests."""
import json
from types import SimpleNamespace

import pytest

from src.ai_workflow import LLMConfig, ResearchRAGStore, build_research_workflow
from src.ai_workflow.schemas import PaperExtractionReport

TEXT = 'We study identical parallel machine scheduling.\nWe minimize total tardiness.\n'


def report(complete):
    references = [{'field': 'problem_type', 'quote': 'We study identical parallel machine scheduling.'}]
    if complete:
        references.append({'field': 'math_model.objectives', 'item_index': 0, 'quote': 'We minimize total tardiness.'})
    return PaperExtractionReport(title='Synthetic fixture', problem_type='Identical parallel machines',
        extraction_method='llm', math_model={'objectives': ['Minimize total tardiness']}, rl_formulation={},
        codebase_alignment={}, claim_evidence=references)


def prepare(monkeypatch, tmp_path, *, repaired=False, allow_fallback=False, supervised=False,
            repair_error=None, workspace=None):
    from src.ai_workflow import langgraph_pipeline as pipeline
    from langgraph.checkpoint.memory import InMemorySaver
    calls = []
    def extraction(**kwargs):
        calls.append(kwargs.get('feedback', ''))
        if repair_error is not None and len(calls) > 1:
            raise repair_error
        return report(complete=repaired and len(calls) > 1)
    def forbidden(*args, **kwargs):
        pytest.fail('Citation-incomplete or unreviewed extraction must not generate/evaluate a selector or record an experiment.')
    monkeypatch.setattr(pipeline, 'resolve_paper_content', lambda **_: SimpleNamespace(
        paper_title='Synthetic fixture', resolved_text=TEXT, content_depth='full_text',
        resolution_log=[], cached_fulltext_path=None, downloaded_pdf_path=None))
    monkeypatch.setattr(pipeline, '_llm_extract_paper', extraction)
    monkeypatch.setattr(pipeline, '_llm_generate_rule_code', forbidden)
    monkeypatch.setattr(pipeline, 'evaluate_generated_rule', forbidden)
    cfg = LLMConfig(api_key='test-not-a-real-key', allow_fallback=allow_fallback)
    store = ResearchRAGStore(project_root=tmp_path, config=cfg)
    monkeypatch.setattr(store, 'add_memory_note', forbidden)
    graph = build_research_workflow(store, cfg, [], track='graduation', review_required=supervised,
        checkpointer=InMemorySaver() if supervised else None, workspace_index_path=workspace)
    return graph, calls


@pytest.mark.parametrize('allow_fallback', [False, True])
def test_exhausted_evidence_stops_before_generation_and_preserves_failure(tmp_path, monkeypatch, allow_fallback):
    graph, calls = prepare(monkeypatch, tmp_path, allow_fallback=allow_fallback)
    state = graph.invoke({'paper_text': TEXT, 'allow_network_fetch': False,
        'extraction_quality': {'status': 'complete'}})
    assert len(calls) == 2 and 'math_model.objectives' in calls[1]
    assert state['overall_status'] == 'EVIDENCE_INCOMPLETE' and state['eval_passed'] is False
    assert state['eval_metrics']['execution_status'] == 'not_run'
    assert not state.get('generated_code') and state['acceptance']['research_status'] == 'not_achieved'
    assert state['extraction_quality']['status'] == 'incomplete'
    assert len(state['extraction_quality']['history']) == 2
    assert 'EVIDENCE_INCOMPLETE' in state['final_summary_markdown'] and '未运行' in state['final_summary_markdown']


@pytest.mark.parametrize('repaired', [False, True])
def test_supervised_repair_keeps_human_gate_and_never_invents_approval(tmp_path, monkeypatch, repaired):
    from langgraph.types import Command
    graph, calls = prepare(monkeypatch, tmp_path, repaired=repaired, supervised=True)
    config = {'configurable': {'thread_id': 'synthetic-unit-test'}}
    first = graph.invoke({'paper_text': TEXT, 'allow_network_fetch': False}, config)
    request = first['__interrupt__'][0].value
    assert request['stage'] == 'scope' and calls == []
    decision = {'stage': request['stage'], 'artifact_hash': request['artifact_hash'],
        'decision': 'approve', 'reviewer': 'synthetic unit test reviewer', 'note': 'Test fixture only'}
    state = graph.invoke(Command(resume=decision), config)
    assert len(calls) == 2 and len(state['human_reviews']) == 1
    if repaired:
        pending = state['__interrupt__'][0].value
        assert pending['stage'] == 'evidence'
        assert pending['payload']['extraction_quality']['attempts'] == 2
        assert pending['payload']['extraction_quality']['status'] == 'complete'
        assert state['extraction_report']['evidence_status'] == 'unverified'
    else:
        assert not state.get('__interrupt__')
        assert state['overall_status'] == 'EVIDENCE_INCOMPLETE'


def test_actual_extraction_prompt_contains_bounded_correction_feedback(monkeypatch):
    from src.ai_workflow.langgraph_pipeline import _llm_extract_paper
    seen = []
    class FakeLLM:
        def __init__(self, **kwargs):
            pass
        def invoke(self, messages):
            seen.extend(messages)
            return SimpleNamespace(content=json.dumps(report(True).model_dump()))
    monkeypatch.setattr('langchain_openai.ChatOpenAI', FakeLLM)
    result = _llm_extract_paper(LLMConfig(api_key='test-not-a-real-key'), 'Fixture', TEXT,
        'full_text', [], 'Extraction diagnostic', [], [], [], feedback='missing math_model.objectives item_index=0')
    assert 'missing math_model.objectives item_index=0' in str(seen)
    assert result.evidence_status == 'unverified'


@pytest.mark.parametrize('error_kind', ['provider', 'parse', 'budget'])
def test_completed_attempt_is_on_disk_even_when_repair_aborts_node(tmp_path, monkeypatch, error_kind):
    from src.ai_workflow.runtime_budget import BudgetExceeded
    error = {'provider': RuntimeError('private-provider-body'),
             'parse': json.JSONDecodeError('private-provider-body', '', 0),
             'budget': BudgetExceeded('budget exhausted')}[error_kind]
    index = tmp_path / 'run' / 'rag_index'
    graph, calls = prepare(monkeypatch, tmp_path, repair_error=error, workspace=index)
    with pytest.raises(BudgetExceeded if error_kind == 'budget' else RuntimeError):
        graph.invoke({'paper_text': TEXT, 'allow_network_fetch': False})
    quality = json.loads((index.parent / 'extraction-attempts.json').read_text(encoding='utf-8'))
    assert len(calls) == 2 and quality['attempts'] == 1
    assert quality['repair_error']['type'] == type(error).__name__
    assert quality['history'][0]['report']['evidence_audit']['summary']['all_claims_located'] is False
    assert 'private-provider-body' not in json.dumps(quality)


def test_explicit_degraded_fallback_retains_the_failed_live_attempt(tmp_path, monkeypatch):
    from langgraph.types import Command
    graph, calls = prepare(monkeypatch, tmp_path, supervised=True, allow_fallback=True,
        repair_error=RuntimeError('private-provider-body'))
    config = {'configurable': {'thread_id': 'degraded-synthetic-test'}}
    first = graph.invoke({'paper_text': TEXT, 'allow_network_fetch': False}, config)
    request = first['__interrupt__'][0].value
    state = graph.invoke(Command(resume={'stage': request['stage'], 'artifact_hash': request['artifact_hash'],
        'decision': 'approve', 'reviewer': 'synthetic unit test reviewer'}), config)
    assert len(calls) == 2 and state['execution_mode'] == 'degraded'
    assert state['__interrupt__'][0].value['stage'] == 'evidence'
    previous = state['extraction_quality']['failed_live_extraction']
    assert len(previous['history']) == 1 and previous['status'] == 'incomplete'
    assert state['extraction_report']['extraction_method'] == 'unverified_template'
