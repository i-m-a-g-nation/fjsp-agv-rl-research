import json

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from src.ai_workflow import LLMConfig, ResearchRAGStore, build_research_workflow
from tests.test_graduation_backend import graduation_request
from tests.test_protocol_workflow import approve


def test_graduation_has_three_reviews_real_domain_results_and_no_model_rag_codegen(tmp_path, graduation_request, monkeypatch):
    from src.ai_workflow import langgraph_pipeline as pipeline
    def forbidden(*a, **kw): pytest.fail('Graduation references must bypass RAG/models/codegen')
    monkeypatch.setattr(ResearchRAGStore, 'build_from_workspace', forbidden)
    for name in ('_llm_extract_paper', '_llm_generate_rule_code', '_offline_generate_rule_code'):
        monkeypatch.setattr(pipeline, name, forbidden)
    config = {'configurable': {'thread_id': 'graduation'}}
    with SqliteSaver.from_conn_string(str(tmp_path / 'graph.sqlite')) as saver:
        graph = build_research_workflow(ResearchRAGStore(tmp_path, LLMConfig(api_key='')),
            track='graduation', checkpointer=saver, review_required=True, workspace_index_path=tmp_path / 'rag_index')
        result = graph.invoke({'graduation_request_path': str(graduation_request), 'allow_network_fetch': False}, config)
        for stage in ('scope', 'evidence', 'conclusion'):
            request = result['__interrupt__'][0].value
            assert request['stage'] == stage
            if stage in ('scope', 'evidence'):
                assert request['payload']['graduation_request']['expected_runs'] == 2
                assert request['payload']['graduation_request']['solver']['seed'] == 42
            if stage == 'evidence': assert not (tmp_path / 'graduation_run').exists()
            result = graph.invoke(Command(resume=approve(request)), config)
        assert result['eval_passed'] and result['overall_status'] == 'GRADUATION_REFERENCE'
        assert result['graduation_result']['accepted_runs'] == 2
        assert result['acceptance']['research_status'] == 'not_achieved'
        assert 'fixed_vs_joint_maintenance' in result['acceptance']['unmet_requirements']
        assert 'total_tardiness' in result['acceptance']['verified_capabilities']
        assert len(result['human_reviews']) == 3 and not result.get('generated_code')
        assert not (tmp_path / 'rag_index').exists()


def test_persistent_graduation_resumes_all_gates_with_zero_providers(tmp_path, graduation_request):
    from src.ai_workflow.sessions import run_session
    folder = tmp_path / 'session'
    state = {'graduation_request_path': str(graduation_request), 'allow_network_fetch': False}
    current = run_session(folder, track='graduation', config=LLMConfig(api_key=''), project_root=tmp_path, input_state=state)
    for stage in ('scope', 'evidence', 'conclusion'):
        assert current['status'] == 'WAITING_HUMAN' and current['pending_review']['stage'] == stage
        current = run_session(folder, track='graduation', config=LLMConfig(api_key=''), decision=approve(current['pending_review']))
    assert current['status'] == 'COMPLETED' and current['state']['eval_passed']
    assert current['budget']['provider_calls'] == 0
    assert current['budget']['limits']['max_provider_calls'] == 0
    assert current['state']['acceptance']['research_status'] == 'not_achieved'
    assert json.loads((folder / 'session.json').read_text())['benchmark_paths'] == []


def test_changed_original_request_cannot_inherit_scope_approval(tmp_path, graduation_request):
    from src.ai_workflow.sessions import run_session
    folder = tmp_path / 'session'
    current = run_session(folder, track='graduation', config=LLMConfig(api_key=''), project_root=tmp_path,
        input_state={'graduation_request_path': str(graduation_request)})
    graduation_request.write_bytes(graduation_request.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='changed'):
        run_session(folder, track='graduation', config=LLMConfig(api_key=''), decision=approve(current['pending_review']))
    assert not (folder / 'graduation_run').exists()


@pytest.mark.parametrize('fault', ['reject', 'artifact'])
def test_reject_and_tamper_do_not_complete_a_graduation_run(tmp_path, graduation_request, fault):
    config = {'configurable': {'thread_id': fault}}
    with SqliteSaver.from_conn_string(str(tmp_path / 'graph.sqlite')) as saver:
        graph = build_research_workflow(ResearchRAGStore(tmp_path, LLMConfig(api_key='')), track='graduation',
            checkpointer=saver, review_required=True, workspace_index_path=tmp_path / 'rag_index')
        state = graph.invoke({'graduation_request_path': str(graduation_request)}, config)
        request = state['__interrupt__'][0].value
        if fault == 'reject':
            state = graph.invoke(Command(resume={**approve(request), 'decision': 'reject'}), config)
            assert state['overall_status'] == 'REJECTED' and not (tmp_path / 'graduation_run').exists()
        else:
            for _ in range(2):
                state = graph.invoke(Command(resume=approve(state['__interrupt__'][0].value)), config)
            (tmp_path / 'graduation_run' / 'joint.json').write_text('changed')
            with pytest.raises(ValueError):
                graph.invoke(Command(resume=approve(state['__interrupt__'][0].value)), config)


@pytest.mark.parametrize('fault', ['track', 'mixed', 'live', 'no_review'])
def test_unsupported_routes_reject_before_execution(tmp_path, graduation_request, fault):
    from src.ai_workflow.sessions import run_session
    state = {'graduation_request_path': str(graduation_request)}
    if fault == 'mixed': state['experiment_protocol_path'] = 'other.json'
    if fault == 'no_review':
        graph = build_research_workflow(ResearchRAGStore(tmp_path, LLMConfig(api_key='')), track='graduation')
        with pytest.raises(ValueError): graph.invoke(state)
    else:
        with pytest.raises(ValueError):
            run_session(tmp_path / 'session', track='foundation' if fault == 'track' else 'graduation',
                config=LLMConfig(api_key='placeholder' if fault == 'live' else ''), project_root=tmp_path, input_state=state)
