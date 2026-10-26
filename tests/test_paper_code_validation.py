"""Read-only source-to-extraction controller; all network/model calls are fixtures."""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path

import pytest

from src.ai_workflow.config import LLMConfig
from src.ai_workflow.schemas import PaperExtractionReport

TEXT = 'We minimize total tardiness on parallel machines.'
REQUEST = Path(__file__).resolve().parents[1] / 'experiments/requests/paper_code_validation_v1.json'


def setup_driver(monkeypatch, tmp_path, mode='complete'):
    module = importlib.import_module('experiments.exp_023_paper_code_validation')
    request = json.loads(REQUEST.read_text(encoding='utf-8'))
    calls = []
    def acquire(request, folder, **kwargs):
        folder.mkdir(parents=True)
        for file in request['repository']['files']:
            path = folder / 'code' / file['path']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(''.join(f'# source line {n}\n' for n in range(1, 301)), encoding='utf-8')
        return {'status':'COMPLETED', 'repository':request['repository'], 'linkage':{'status':'VERIFIED_TEXT_LINKS'}}
    def context(folder, pages):
        path = folder / ('context-'+'-'.join(map(str,pages))+'.txt')
        path.write_text(TEXT,encoding='utf-8')
        digest=hashlib.sha256(TEXT.encode()).hexdigest()
        return TEXT, {'source_path':str(path),'raw_sha256':digest,'text_sha256':digest,'text_length':len(TEXT),
            'pages':[{'page':pages[0],'start':0,'end':len(TEXT)}],'warnings':['Selected pages only.']}
    def extract(**kwargs):
        kwargs['cfg'].provider_timeout(output_tokens=kwargs['cfg'].max_output_tokens)
        calls.append(kwargs)
        if mode=='repair_error' and kwargs.get('feedback'):
            raise RuntimeError('sk-private-sentinel-private-provider-body')
        complete = mode=='complete' or (mode=='repair' and bool(kwargs.get('feedback')))
        return PaperExtractionReport(title='Fixture',problem_type='Parallel machines',extraction_method='llm',
            math_model={},rl_formulation={},codebase_alignment={},
            claim_evidence=[{'field':'problem_type','quote':TEXT}] if complete else [])
    monkeypatch.setattr(module,'acquire_source_bundle',acquire)
    monkeypatch.setattr(module,'verify_source_bundle',lambda _: {'status':'COMPLETED'})
    monkeypatch.setattr(module,'make_paper_context',context)
    monkeypatch.setattr(module,'_llm_extract_paper',extract)
    return module,request,calls


def live_config(**overrides):
    return LLMConfig(api_key='sk-private-sentinel',thinking_mode='enabled',reasoning_effort='max',
        max_output_tokens=8192,request_timeout_seconds=60,**overrides)


def test_acquisition_only_is_default_and_never_calls_model(monkeypatch,tmp_path):
    module,request,calls=setup_driver(monkeypatch,tmp_path)
    result=module.run_validation(request,tmp_path/'run')
    assert result['status']=='SOURCES_VERIFIED_UNREVIEWED' and calls==[]
    assert result['budget']['provider_calls']==0
    assert all(unit['status']=='NOT_RUN' for unit in result['units'])
    assert result['research_status']=='not_achieved' and result['reproduction_status']=='not_executed'


def test_two_units_save_physical_evidence_pinned_code_and_no_approval(monkeypatch,tmp_path):
    module,request,calls=setup_driver(monkeypatch,tmp_path)
    result=module.run_validation(request,tmp_path/'run',extract=True,config=live_config())
    assert result['status']=='EVIDENCE_READY_UNREVIEWED' and len(calls)==2
    assert result['budget']['provider_calls']==2 and result['budget']['output_tokens_reserved']==16384
    for unit in result['units']:
        assert unit['status']=='COMPLETE' and unit['extraction']['evidence_status']=='unverified'
        assert unit['extraction']['evidence_audit']['claims'][0]['locations'][0]['page_start'] in request['units'][0]['pages']+request['units'][1]['pages']
        assert request['repository']['commit'] in unit['code_context'][0]['source']
        assert all(len(item['content'])<=1200 for item in unit['code_context'])
    assert result['candidate_application_status']=='not_applied'
    assert not list((tmp_path/'run').rglob('*decision*.json'))
    assert 'sk-private-sentinel' not in (tmp_path/'run'/'result.json').read_text(encoding='utf-8')


@pytest.mark.parametrize('mode,expected', [('repair','EVIDENCE_READY_UNREVIEWED'),('incomplete','EVIDENCE_INCOMPLETE')])
def test_one_repair_per_unit_is_bounded_and_preserves_attempts(monkeypatch,tmp_path,mode,expected):
    module,request,calls=setup_driver(monkeypatch,tmp_path,mode)
    result=module.run_validation(request,tmp_path/'run',extract=True,config=live_config())
    assert result['status']==expected and len(calls)==4
    assert result['budget']['provider_calls']==4
    assert all(unit['quality']['attempts']==2 for unit in result['units'])
    assert all(len(unit['quality']['history'])==2 for unit in result['units'])


def test_repair_provider_failure_retains_attempt_and_does_not_run_later_unit(monkeypatch,tmp_path):
    module,request,calls=setup_driver(monkeypatch,tmp_path,'repair_error')
    result=module.run_validation(request,tmp_path/'run',extract=True,config=live_config())
    assert result['status']=='FAILED' and len(calls)==2
    assert len(result['units'][0]['quality']['history'])==1
    assert result['units'][1]['status']=='NOT_RUN'
    saved=(tmp_path/'run'/'result.json').read_text(encoding='utf-8')
    assert 'private-provider-body' not in saved and 'sk-private-sentinel' not in saved


def test_existing_provider_budget_stops_before_an_extra_request(monkeypatch,tmp_path):
    module,request,calls=setup_driver(monkeypatch,tmp_path,'incomplete')
    request['limits']['max_provider_calls']=1
    result=module.run_validation(request,tmp_path/'run',extract=True,config=live_config())
    assert result['status']=='BUDGET_EXHAUSTED' and len(calls)==1
    assert result['budget']['provider_calls']==1 and result['units'][1]['status']=='NOT_RUN'
    assert len(result['units'][0]['quality']['history'])==1


@pytest.mark.parametrize('change', ['no_key','disabled','wrong_effort','short_cap'])
def test_live_profile_preflight_rejects_before_source_or_model_calls(monkeypatch,tmp_path,change):
    from dataclasses import replace
    module,request,calls=setup_driver(monkeypatch,tmp_path)
    cfg=live_config()
    cfg=replace(cfg,**{'no_key':{'api_key':''},'disabled':{'thinking_mode':'disabled'},
        'wrong_effort':{'reasoning_effort':'high'},'short_cap':{'max_output_tokens':4096}}[change])
    with pytest.raises(ValueError):
        module.run_validation(request,tmp_path/'run',extract=True,config=cfg)
    assert calls==[] and not (tmp_path/'run').exists()


def test_source_or_code_range_failure_does_not_call_model(monkeypatch,tmp_path):
    module,request,calls=setup_driver(monkeypatch,tmp_path)
    request['units'][0]['code_ranges'][0].update(start=299,end=350)
    result=module.run_validation(request,tmp_path/'run',extract=True,config=live_config())
    assert result['status']=='FAILED' and calls==[]
    assert result['units'][1]['status']=='NOT_RUN'


def test_existing_output_and_overlarge_budget_are_not_silently_reused(monkeypatch,tmp_path):
    module,request,calls=setup_driver(monkeypatch,tmp_path)
    folder=tmp_path/'run'
    folder.mkdir()
    marker=folder/'marker'
    marker.write_text('keep',encoding='utf-8')
    with pytest.raises(FileExistsError):
        module.run_validation(request,folder)
    assert marker.read_text(encoding='utf-8')=='keep'
    bad=deepcopy(request)
    bad['limits']['max_provider_calls']=5
    with pytest.raises(ValueError):
        module.run_validation(bad,tmp_path/'other',extract=True,config=live_config())
    assert calls==[]


@pytest.mark.parametrize('url', [
    'https://user:private-source-secret@link.springer.com/content/pdf/10.1007/s10845-024-02470-8.pdf',
    'https://link.springer.com/content/pdf/10.1007/s10845-024-02470-8.pdf?key=private-source-secret',
])
def test_rejected_source_credentials_are_never_persisted(monkeypatch,tmp_path,url):
    module,request,calls=setup_driver(monkeypatch,tmp_path)
    request['paper']['pdf_url']=url
    with pytest.raises(ValueError):
        module.run_validation(request,tmp_path/'run')
    assert not (tmp_path/'run').exists() and calls==[]


@pytest.mark.parametrize('extract', [False,True])
def test_deadline_exhaustion_cannot_finalize_a_successful_status(monkeypatch,tmp_path,extract):
    from src.ai_workflow.runtime_budget import BudgetExceeded
    module,request,calls=setup_driver(monkeypatch,tmp_path)
    expired=[False]
    original_budget=module.RunBudget
    class DeadlineBudget(original_budget):
        def remaining_seconds(self):
            if expired[0]:
                raise BudgetExceeded('synthetic deadline exhausted')
            return super().remaining_seconds()
    monkeypatch.setattr(module,'RunBudget',DeadlineBudget)
    if extract:
        original_extract=module._llm_extract_paper
        def late_extract(**kwargs):
            result=original_extract(**kwargs)
            if len(calls)==2:
                expired[0]=True
            return result
        monkeypatch.setattr(module,'_llm_extract_paper',late_extract)
    else:
        def late_verify(folder):
            expired[0]=True
            return {'status':'COMPLETED'}
        monkeypatch.setattr(module,'verify_source_bundle',late_verify)
    result=module.run_validation(request,tmp_path/'run',extract=extract,config=live_config() if extract else None)
    assert result['status']=='BUDGET_EXHAUSTED'
    assert len(calls)==(2 if extract else 0)


def test_explicit_paper_profile_reserves_one_long_call_inside_existing_batch_budget(monkeypatch,tmp_path):
    module,request,calls=setup_driver(monkeypatch,tmp_path)
    request['units']=request['units'][:1]
    request['model_request']={'profile':'paper_excerpt','max_output_tokens':16384,'request_timeout_seconds':120}
    request['limits'].update(max_provider_calls=1,max_output_tokens=16384,max_active_seconds=180)
    result=module.run_validation(request,tmp_path/'run',extract=True,config=live_config())
    assert result['status']=='EVIDENCE_READY_UNREVIEWED'
    assert len(calls)==1 and calls[0]['cfg'].request_profile=='paper_excerpt'
    assert result['budget']['output_tokens_reserved']==16384
    assert result['model_profile']['max_output_tokens']==16384
    assert result['target_contract']['track']=='graduation'
    assert '课题要求' not in calls[0]['goal'], 'Paper fact extraction must not be asked to reproduce the project model.'


@pytest.mark.parametrize('change', [{'profile':'invalid'}, {'max_output_tokens':32768},
    {'request_timeout_seconds':121}])
def test_paper_profile_cannot_expand_the_declared_batch_or_hidden_caps(monkeypatch,tmp_path,change):
    module,request,calls=setup_driver(monkeypatch,tmp_path)
    request['model_request']={'profile':'paper_excerpt','max_output_tokens':16384,'request_timeout_seconds':120,**change}
    with pytest.raises(ValueError):
        module.run_validation(request,tmp_path/'run',extract=True,config=live_config())
    assert calls==[] and not (tmp_path/'run').exists()


def setup_field_driver(monkeypatch, tmp_path, missing=False):
    module, request, legacy_calls = setup_driver(monkeypatch, tmp_path)
    calls = []
    request['model_request'] = {'profile':'bounded', 'max_output_tokens':8192,
        'request_timeout_seconds':60, 'repair_attempts':0}
    for unit in request['units']:
        unit['field'] = 'rl_formulation.reward_function'
        unit['pages'] = [15]
        unit['excerpts'] = [{'page':15, 'start':0, 'end':len(TEXT),
                             'page_sha256':hashlib.sha256(TEXT.encode()).hexdigest()}]
    old_context = module.make_paper_context
    monkeypatch.setattr(module, 'make_paper_excerpt', lambda folder, spans: old_context(folder, [15]))

    def focused(**kwargs):
        kwargs['cfg'].provider_timeout(output_tokens=kwargs['cfg'].max_output_tokens)
        calls.append(kwargs)
        if kwargs.get('on_response'):
            kwargs['on_response']({'finish_reason':'stop', 'usage':{}, 'final_text_characters':2, 'final_text':'{}'})
        return PaperExtractionReport(title='Fixture', problem_type='', extraction_method='llm', math_model={},
            rl_formulation={} if missing else {'reward_function':'Paper fact'}, codebase_alignment={},
            claim_evidence=[] if missing else [{'field':'rl_formulation.reward_function', 'quote':TEXT}])

    monkeypatch.setattr(module, 'extract_paper_field', focused)
    return module, request, calls, legacy_calls


def test_field_preview_is_saved_without_key_or_model_calls(monkeypatch, tmp_path):
    module, request, calls, old = setup_field_driver(monkeypatch, tmp_path)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    result = module.run_validation(request, tmp_path/'run')
    assert result['status'] == 'SOURCES_VERIFIED_UNREVIEWED'
    assert result['budget']['provider_calls'] == 0 and calls == [] and old == []
    assert all(unit['status'] == 'PREVIEW_READY' and unit['field'] == 'rl_formulation.reward_function'
               and unit['source_map']['pages'][0]['page'] == 15 and unit['code_context'] for unit in result['units'])
    assert json.loads((tmp_path/'run'/'result.json').read_text(encoding='utf-8'))['units'][0]['source_map']


def test_field_live_uses_small_prompt_keeps_author_code_separate_and_stays_unverified(monkeypatch, tmp_path):
    module, request, calls, old = setup_field_driver(monkeypatch, tmp_path)
    result = module.run_validation(request, tmp_path/'run', extract=True, config=live_config())
    assert result['status'] == 'EVIDENCE_READY_UNREVIEWED' and old == [] and len(calls) == 2
    assert result['budget']['provider_calls'] == 2 and result['budget']['output_tokens_reserved'] == 16384
    for call, unit in zip(calls, result['units']):
        assert call['paper_text'] == TEXT and call['source_map']['pages'][0]['page'] == 15
        assert 'retrieved_codebase' not in call and 'target_contract' not in call
        assert call['field'] == 'rl_formulation.reward_function'
        assert unit['extraction']['evidence_status'] == 'unverified' and unit['responses'][0]['finish_reason'] == 'stop'
    assert result['research_status'] == 'not_achieved' and result['candidate_application_status'] == 'not_applied'


@pytest.mark.parametrize('change', [dict(field='codebase_alignment.reusable_modules'),
    dict(excerpts=[]), dict(pages=[14]), dict(field=None), dict(goal=''),
    dict(excerpts=[{'page':15,'start':0,'end':2401,'page_sha256':'a'*64}])])
def test_invalid_field_selector_rejected_before_persistence(monkeypatch, tmp_path, change):
    module, request, calls, _ = setup_field_driver(monkeypatch, tmp_path)
    request['units'][0].update(change)
    with pytest.raises(ValueError):
        module.run_validation(request, tmp_path/'run', extract=True, config=live_config())
    assert calls == [] and not (tmp_path/'run').exists()


def test_missing_field_cannot_become_ready_or_silently_fallback(monkeypatch, tmp_path):
    module, request, calls, old = setup_field_driver(monkeypatch, tmp_path, missing=True)
    result = module.run_validation(request, tmp_path/'run', extract=True, config=live_config())
    assert result['status'] == 'EVIDENCE_INCOMPLETE' and len(calls) == 2 and old == []
    assert all(unit['quality']['status'] == 'incomplete' for unit in result['units'])


def test_field_units_share_declared_budget(monkeypatch, tmp_path):
    module, request, calls, old = setup_field_driver(monkeypatch, tmp_path)
    request['limits']['max_provider_calls'] = 1
    result = module.run_validation(request, tmp_path/'run', extract=True, config=live_config())
    assert result['status'] == 'BUDGET_EXHAUSTED' and len(calls) == 1 and old == []
    assert result['units'][0]['status'] == 'COMPLETE' and result['units'][1]['status'] == 'BUDGET_EXHAUSTED'
