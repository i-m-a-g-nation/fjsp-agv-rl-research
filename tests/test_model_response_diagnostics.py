"""Incomplete final output must be observable without saving hidden reasoning or keys."""
import json
from types import SimpleNamespace

import pytest

from src.ai_workflow.config import LLMConfig


def invoke(monkeypatch, content, reason='stop', observer=None):
    from src.ai_workflow.langgraph_pipeline import _llm_extract_paper
    class FakeLLM:
        def __init__(self, **kwargs):
            pass
        def invoke(self, messages):
            return SimpleNamespace(content=content, response_metadata={'finish_reason':reason,
                'token_usage':{'completion_tokens':8192,'prompt_tokens':100,'total_tokens':8292,
                    'completion_tokens_details':{'reasoning_tokens':8000}}},
                additional_kwargs={'reasoning_content':'hidden-chain-sentinel'})
    monkeypatch.setattr('langchain_openai.ChatOpenAI',FakeLLM)
    return _llm_extract_paper(LLMConfig(api_key='secret-key-sentinel'), 'Fixture', 'An original source paragraph.',
        'full_text', [], 'goal', [], [], [], on_response=observer)


def test_valid_response_records_only_public_final_text_and_usage(monkeypatch):
    seen=[]
    payload=json.dumps({'title':'Fixture','problem_type':'Unknown','math_model':{},'rl_formulation':{},'codebase_alignment':{}})
    result=invoke(monkeypatch,payload,observer=seen.append)
    assert result.evidence_status=='unverified' and len(seen)==1
    assert seen[0]['finish_reason']=='stop' and seen[0]['usage']['reasoning_tokens']==8000
    assert 'hidden-chain-sentinel' not in json.dumps(seen)


@pytest.mark.parametrize('content,reason', [('', 'length'), ('{"title":"partial', 'length'),
    (json.dumps({'title':'Fixture','problem_type':'Unknown','math_model':{},'rl_formulation':{},'codebase_alignment':{}}),'length')])
def test_empty_or_truncated_response_cannot_be_accepted_even_if_json_is_complete(monkeypatch,content,reason):
    seen=[]
    with pytest.raises(RuntimeError) as captured:
        invoke(monkeypatch,content,reason,seen.append)
    assert seen and seen[0]['finish_reason']=='length'
    assert captured.value.model_response['finish_reason']=='length'


def test_invalid_json_retains_redacted_final_output_for_diagnosis(monkeypatch):
    seen=[]
    with pytest.raises(json.JSONDecodeError) as captured:
        invoke(monkeypatch,'secret-key-sentinel invalid JSON','stop',seen.append)
    assert captured.value.model_response['final_text']=='<redacted> invalid JSON'
    assert 'secret-key-sentinel' not in json.dumps(seen)
    assert 'hidden-chain-sentinel' not in json.dumps(seen)
