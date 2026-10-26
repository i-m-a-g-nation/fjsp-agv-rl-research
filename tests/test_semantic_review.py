"""Semantic model judgment stays separate from source location and human approval."""
import hashlib
import importlib
import json

import httpx
import pytest

from src.ai_workflow.config import LLMConfig
from src.ai_workflow.runtime_budget import BudgetExceeded, BudgetLimits, RunBudget
from src.ai_workflow.schemas import PaperExtractionReport


TEXT = 'Job features are processing time, due date and family.'


def mapping(text=TEXT, spans=None):
    return {'text_sha256':hashlib.sha256(text.encode()).hexdigest(), 'text_length':len(text),
            'pages':spans or [{'page':12,'start':0,'end':len(text),'source_start':1817,'source_end':1817+len(text)}]}


def report(claim='Jobs have processing time, due date and family.', quote=TEXT):
    return PaperExtractionReport(title='Fixture', problem_type='', math_model={}, codebase_alignment={},
        rl_formulation={'state_space':[claim]}, claim_evidence=[{
            'field':'rl_formulation.state_space','item_index':0,'quote':quote}])


def transport(monkeypatch, tmp_path, answer, reason='stop'):
    import langchain_openai
    original=langchain_openai.ChatOpenAI
    captured=[]
    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200,json={'id':'offline','object':'chat.completion','created':0,
            'model':'deepseek-flash','choices':[{'index':0,'finish_reason':reason,'message':{
                'role':'assistant','content':answer,'reasoning_content':'HIDDEN-SENTINEL'}}],
            'usage':{'prompt_tokens':10,'completion_tokens':100,'total_tokens':110,
                     'completion_tokens_details':{'reasoning_tokens':70}}})
    client=httpx.Client(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(langchain_openai,'ChatOpenAI',lambda **kw:original(http_client=client,**kw))
    budget=RunBudget(tmp_path/'budget.sqlite',BudgetLimits(max_active_seconds=150,max_provider_calls=1,max_output_tokens=8192))
    cfg=LLMConfig(api_key='sk-private-sentinel',thinking_mode='enabled',reasoning_effort='max',
                  max_output_tokens=8192,request_timeout_seconds=60,budget=budget)
    return cfg,captured,client


def review(cfg, **changes):
    module=importlib.import_module('src.ai_workflow.semantic_review')
    args=dict(cfg=cfg,report=report(),paper_text=TEXT,source_map=mapping())
    args.update(changes)
    return module.review_paper_claim(**args)


def test_supported_is_only_model_judgment_and_leaves_original_unchanged(monkeypatch,tmp_path):
    cfg,requests,client=transport(monkeypatch,tmp_path,json.dumps({
        'verdict':'supported','reason':'All three features are explicitly named.','quote':TEXT}))
    original=report()
    before=original.model_dump()
    seen=[]
    with client:
        result=review(cfg,report=original,on_response=seen.append)
    assert result['verdict']=='supported' and result['status']=='model_supported_unreviewed'
    assert result['human_approval'] is False and result['evidence_status']=='unverified'
    assert result['source_text_sha256']==hashlib.sha256(TEXT.encode()).hexdigest()
    assert result['claim']['field']=='rl_formulation.state_space'
    assert result['locations'][0]['page_start']==12 and result['locations'][0]['quote']==TEXT
    assert original.model_dump()==before and len(result['claim_sha256'])==64
    body=requests[0]
    assert body['thinking']=={'type':'enabled'} and body['reasoning_effort']=='max'
    assert body['max_tokens']==8192 and 'max_completion_tokens' not in body
    assert body['response_format']=={'type':'json_object'}
    assert cfg.budget.snapshot()['provider_calls']==1 and seen[0]['finish_reason']=='stop'
    assert 'HIDDEN-SENTINEL' not in json.dumps(seen)
    prompt=json.dumps(body['messages'])
    assert TEXT in prompt and 'codebase_alignment' not in prompt and 'target_contract' not in prompt


@pytest.mark.parametrize('verdict',['partial','unsupported','insufficient_evidence'])
def test_flagged_verdict_cannot_approve_even_with_a_real_located_quote(monkeypatch,tmp_path,verdict):
    cfg,_,client=transport(monkeypatch,tmp_path,json.dumps({
        'verdict':verdict,'reason':'Mandatory maintenance is not stated.','quote':TEXT}))
    with client:
        result=review(cfg,report=report(claim='Every machine has mandatory maintenance.'))
    assert result['status']=='model_flagged_unreviewed' and result['verdict']==verdict
    assert result['human_approval'] is False and result['evidence_status']=='unverified'


@pytest.mark.parametrize('payload,reason',[
    ('','length'), ('{"verdict":"supported"}','length'), ('sk-private-sentinel invalid JSON','stop'),
    (json.dumps({'verdict':'supported','reason':'yes','quote':''}),'stop'),
    (json.dumps({'verdict':'supported','reason':'yes','quote':'invented quote not in paper'}),'stop'),
    (json.dumps({'verdict':'supported','reason':'yes','quote':TEXT,'human_approval':True}),'stop'),
    ('{"verdict":"unsupported","verdict":"supported","reason":"x","quote":""}','stop')])
def test_bad_review_retains_response_and_cannot_create_supported_status(monkeypatch,tmp_path,payload,reason):
    cfg,_,client=transport(monkeypatch,tmp_path,payload,reason)
    seen=[]
    with client,pytest.raises((ValueError,RuntimeError)) as captured:
        review(cfg,on_response=seen.append)
    assert len(seen)==1 and captured.value.model_response['finish_reason']==reason
    assert 'sk-private-sentinel' not in json.dumps(seen) and 'HIDDEN-SENTINEL' not in json.dumps(seen)


@pytest.mark.parametrize('change',['missing_quote','no_claim','two_claims','changed_source'])
def test_unlocated_or_multi_claim_input_stops_before_provider_reservation(monkeypatch,tmp_path,change):
    cfg,requests,client=transport(monkeypatch,tmp_path,'{}')
    original=report()
    args={}
    if change=='missing_quote': original.claim_evidence=[]
    if change=='no_claim': original.rl_formulation.state_space=[]
    if change=='two_claims': original.rl_formulation.state_space.append('Another feature.')
    if change=='changed_source': args['paper_text']='Changed source text'
    with client,pytest.raises(ValueError):
        review(cfg,report=original,**args)
    assert requests==[] and cfg.budget.snapshot()['provider_calls']==0


def test_marker_review_quote_cannot_gain_pdf_provenance(monkeypatch,tmp_path):
    marker='[Physical PDF page 12]'
    text=TEXT+'\n'+marker+'\n'+TEXT
    spans=[{'page':12,'start':0,'end':len(TEXT)},
           {'page':12,'start':len(TEXT)+len(marker)+2,'end':len(text)}]
    original=report()
    original.claim_evidence[0]=original.claim_evidence[0].model_copy(update={'source_start':0})
    cfg,_,client=transport(monkeypatch,tmp_path,json.dumps({'verdict':'supported','reason':'yes','quote':marker}))
    with client,pytest.raises(ValueError):
        review(cfg,report=original,paper_text=text,source_map=mapping(text,spans))


def test_review_does_not_create_a_fresh_budget(monkeypatch,tmp_path):
    cfg,requests,client=transport(monkeypatch,tmp_path,json.dumps({'verdict':'unsupported','reason':'No support.','quote':''}))
    with client:
        review(cfg)
        with pytest.raises(BudgetExceeded): review(cfg)
    assert len(requests)==1


def test_original_marker_citation_is_rejected_before_review_call(monkeypatch,tmp_path):
    marker='[Physical PDF page 12]'
    text=marker+'\n'+TEXT
    spans=[{'page':12,'start':len(marker)+1,'end':len(text)}]
    cfg,requests,client=transport(monkeypatch,tmp_path,'{}')
    with client,pytest.raises(ValueError):
        review(cfg,report=report(quote=marker),paper_text=text,source_map=mapping(text,spans))
    assert requests==[] and cfg.budget.snapshot()['provider_calls']==0
