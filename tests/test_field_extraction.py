"""Single-field facts use real SDK serialization against an offline transport."""
import hashlib
import importlib
import json

import httpx
import pytest

from src.ai_workflow.config import LLMConfig
from src.ai_workflow.runtime_budget import BudgetExceeded, BudgetLimits, RunBudget


TEXT = 'The constants Rshape and Ropt have values of 1 and 200, respectively.'


def source_map(text=TEXT, pages=None):
    return {'source_kind': 'pdf_backed_text', 'text_length': len(text),
            'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'pages': pages or [{'page': 15, 'start': 0, 'end': len(text),
                               'source_start': 100, 'source_end': 100 + len(text)}]}


def setup_transport(monkeypatch, tmp_path, content, reason='stop', tokens=100):
    import langchain_openai
    original = langchain_openai.ChatOpenAI
    captured = []

    def respond(request):
        captured.append((json.loads(request.content), request.extensions['timeout']))
        return httpx.Response(200, json={'id': 'offline', 'object': 'chat.completion', 'created': 0,
            'model': 'deepseek-flash', 'choices': [{'index': 0, 'finish_reason': reason,
                'message': {'role': 'assistant', 'content': content, 'reasoning_content': 'HIDDEN-SENTINEL'}}],
            'usage': {'prompt_tokens': 20, 'completion_tokens': tokens, 'total_tokens': 20 + tokens,
                      'completion_tokens_details': {'reasoning_tokens': tokens - 20}}})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(langchain_openai, 'ChatOpenAI', lambda **kw: original(http_client=client, **kw))
    budget = RunBudget(tmp_path / 'budget.sqlite', BudgetLimits(max_active_seconds=150,
        max_provider_calls=1, max_output_tokens=8192))
    cfg = LLMConfig(api_key='sk-private-sentinel', thinking_mode='enabled', reasoning_effort='max',
        max_output_tokens=8192, request_timeout_seconds=60, budget=budget)
    return cfg, captured, client


def extract(cfg, **overrides):
    module = importlib.import_module('src.ai_workflow.field_extraction')
    args = dict(cfg=cfg, paper_title='Fixture', paper_text=TEXT, source_map=source_map(),
                field='rl_formulation.reward_function', question='Which reward constants are explicitly stated?')
    args.update(overrides)
    return module.extract_paper_field(**args)


@pytest.mark.parametrize('field', ['rl_formulation.reward_function', 'rl_formulation.action_space'])
def test_one_claim_only_with_source_location_and_official_max_body(monkeypatch, tmp_path, field):
    payload = json.dumps({'status': 'found', 'value': 'Rshape=1; Ropt=200', 'quote': TEXT})
    cfg, captured, client = setup_transport(monkeypatch, tmp_path, payload)
    seen = []
    with client:
        report = extract(cfg, field=field, on_response=seen.append)
    assert report.evidence_status == 'unverified'
    assert report.evidence_audit['summary']['claims_total'] == 1
    assert report.evidence_audit['summary']['all_claims_located'] is True
    claim = report.evidence_audit['claims'][0]
    assert claim['field'] == field and claim['claim'] == 'Rshape=1; Ropt=200'
    assert claim['locations'][0]['page_start'] == 15
    assert report.problem_type == '' and report.codebase_alignment.model_dump() == {
        'reusable_modules': [], 'missing_gaps': [], 'candidate_rule_description': ''}
    body, timeout = captured[0]
    assert body['thinking'] == {'type': 'enabled'} and body['reasoning_effort'] == 'max'
    assert body['max_tokens'] == 8192 and 'max_completion_tokens' not in body
    assert body['response_format'] == {'type': 'json_object'} and timeout['read'] <= 60
    assert cfg.budget.snapshot()['provider_calls'] == 1
    assert seen[0]['usage']['reasoning_tokens'] == 80
    assert 'HIDDEN-SENTINEL' not in json.dumps(seen)
    prompt = json.dumps(body['messages'])
    assert TEXT in prompt and 'codebase_alignment' not in prompt and 'maintenance' not in prompt


def test_missing_stays_empty_and_cannot_pass_evidence(monkeypatch, tmp_path):
    cfg, captured, client = setup_transport(monkeypatch, tmp_path, '{"status":"missing","value":"","quote":""}')
    with client:
        report = extract(cfg)
    assert report.rl_formulation.reward_function == ''
    assert report.evidence_audit['summary']['all_claims_located'] is False
    assert report.missing_warnings and len(captured) == 1


@pytest.mark.parametrize('content,reason', [('', 'length'), ('{"status":"found"}', 'length'),
    ('sk-private-sentinel invalid JSON', 'stop'),
    ('{"status":"found","value":"invented","quote":"too short"}', 'stop'),
    (json.dumps({'status':'found','value':'x','quote':TEXT,'evidence_status':'verified'}), 'stop'),
    ('{"status":"missing","value":"invented","quote":""}', 'stop'),
    ('{"status":"missing","status":"found","value":"","quote":""}', 'stop')])
def test_bad_response_preserved_safely_and_never_certified(monkeypatch, tmp_path, content, reason):
    cfg, _, client = setup_transport(monkeypatch, tmp_path, content, reason)
    seen = []
    with client, pytest.raises((ValueError, RuntimeError)) as raised:
        extract(cfg, on_response=seen.append)
    assert len(seen) == 1 and raised.value.model_response['finish_reason'] == reason
    assert 'sk-private-sentinel' not in json.dumps(seen)
    assert 'HIDDEN-SENTINEL' not in json.dumps(seen)


@pytest.mark.parametrize('change', [dict(field='codebase_alignment.reusable_modules'),
    dict(paper_text='x' * 6001), dict(question='x' * 2001), dict(paper_text='')])
def test_invalid_input_rejected_before_provider_reservation(monkeypatch, tmp_path, change):
    cfg, captured, client = setup_transport(monkeypatch, tmp_path, '{}')
    with client, pytest.raises(ValueError):
        extract(cfg, **change)
    assert captured == [] and cfg.budget.snapshot()['provider_calls'] == 0


def test_excerpt_marker_quote_cannot_gain_pdf_provenance(monkeypatch, tmp_path):
    text = 'first span text\n[Physical PDF page 15]\nsecond span text'
    quote = '[Physical PDF page 15]'
    cfg, _, client = setup_transport(monkeypatch, tmp_path, json.dumps({
        'status': 'found', 'value': 'fake paper fact', 'quote': quote}))
    pages = [{'page':15,'start':0,'end':15,'source_start':0,'source_end':15},
             {'page':15,'start':38,'end':54,'source_start':100,'source_end':116}]
    with client, pytest.raises(ValueError):
        extract(cfg, paper_text=text, source_map=source_map(text, pages))


def test_repeat_call_cannot_reset_budget(monkeypatch, tmp_path):
    cfg, captured, client = setup_transport(monkeypatch, tmp_path, '{"status":"missing","value":"","quote":""}')
    with client:
        extract(cfg)
        with pytest.raises(BudgetExceeded):
            extract(cfg)
    assert len(captured) == 1
