"""Development controls exercise full denominators without formal main solves."""
import json
from pathlib import Path
import subprocess
import time

import pytest

from src.ai_workflow import graduation_main_backend as backend
from src.graduation.reference_main_protocol import build_main_cases
from src.graduation.reference_protocol import encoded,digest
from src.ai_workflow.review import make_review_request


@pytest.fixture
def unit_context(tmp_path,monkeypatch):
    cases=build_main_cases()
    def snapshot(durations):
        active=0.0;segments=[]
        for i,value in enumerate(durations,1):
            segments.append({'id':i,'reserved_seconds':600-active,'finished_seconds':value})
            active+=value
        return {'limits':{'max_active_seconds':600,'max_provider_calls':0,'max_output_tokens':0},
            'active_seconds':active,'active_seconds_charged':active,'active_seconds_reserved':0,
            'provider_calls':0,'output_tokens_reserved':0,'segments':segments,
            'finalization_prepaid_seconds':5.0,'remaining_active_seconds':600-active}
    context={'scope_dir':tmp_path/'scope','cases':cases,'planned_rows':[],
        'scope_hash':'a'*64,'evidence_hash':'b'*64,'backend_source_hashes':{'test':'c'*64}}
    request=make_review_request('scope',{}, {'material_sha256':{'inputs.json':digest(cases)}})
    evidence=make_review_request('evidence',{}, {'scope_hash':request['artifact_hash'],
        'source_hashes':context['backend_source_hashes'],'budget_snapshot':snapshot((.1,5.,.1,5.))})
    context.update(scope_hash=request['artifact_hash'],evidence_hash=evidence['artifact_hash'],
        scope_request=request,evidence_request=evidence,
        scope_decision={'stage':'scope','artifact_hash':request['artifact_hash'],'decision':'approve','reviewer':'TEST_ONLY'},
        evidence_decision={'stage':'evidence','artifact_hash':evidence['artifact_hash'],'decision':'approve','reviewer':'TEST_ONLY'})
    monkeypatch.setattr(backend,'execution_context',lambda *a,**k:context)
    monkeypatch.setattr(backend,'backend_source_hashes',lambda:{'test':'c'*64})
    class Window:
        def check(self): return 100.0
        def remaining(self): return 100.0
    def phase(scope,control,work,finalize,**kwargs):
        Path(control).mkdir(parents=True,exist_ok=True)
        return finalize(work(Window()),snapshot((.1,5.,.1,5.,.1,5.)),lambda:100.0)
    monkeypatch.setattr(backend,'run_main_phase',phase)
    return context


def test_no_evidence_approval_means_no_output_or_worker(tmp_path,monkeypatch):
    monkeypatch.setattr(backend,'supervised_json_process',lambda *a,**k:pytest.fail('Unauthorized worker'))
    with pytest.raises((ValueError,OSError)):
        backend.run_main(tmp_path/'missing-review',tmp_path/'missing-evidence',tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_worker_timeout_preserves_all480_requests(unit_context,tmp_path,monkeypatch):
    def timeout(*a,**k): raise subprocess.TimeoutExpired('worker',1)
    monkeypatch.setattr(backend,'supervised_json_process',timeout)
    result=backend.run_main(tmp_path/'control',tmp_path/'evidence',tmp_path/'out')
    assert result['status']=='BUDGET_EXHAUSTED'
    assert result['planned_calls']==480 and result['accepted_runs']==result['completed_pairs']==0
    assert result['status_counts']['NOT_RUN']==480


def test_worker_claim_without_receipts_never_completes(unit_context,tmp_path,monkeypatch):
    monkeypatch.setattr(backend,'supervised_json_process',lambda *a,**k:{'status':'WORKER_FINISHED','completed_rows':480})
    result=backend.run_main(tmp_path/'control',tmp_path/'evidence',tmp_path/'out')
    assert result['status']=='FAILED'
    assert result['status_counts']['NOT_RUN']==480


def test_interrupted_row_retains_null_metrics(unit_context,tmp_path,monkeypatch):
    def interrupted(script,payload,timeout):
        folder=Path(payload['output_dir'])
        state=json.loads((folder/'state.json').read_text(encoding='utf-8'))
        state['rows'][0]['status']='RUNNING'
        (folder/'state.json').write_bytes(encoded(state))
        raise subprocess.TimeoutExpired('worker',timeout)
    monkeypatch.setattr(backend,'supervised_json_process',interrupted)
    result=backend.run_main(tmp_path/'control',tmp_path/'evidence',tmp_path/'out')
    assert result['status_counts']['INTERRUPTED']==1 and result['status_counts']['NOT_RUN']==479
    assert result['accepted_runs']==0 and result['completed_pairs']==0


def test_mocked_unknown_matrix_accounts_every_row_without_solver(unit_context,tmp_path,monkeypatch):
    from src.graduation import reference_main_worker as worker
    def unknown(case,mode):
        return {'case_id':case['case_id'],'mode':mode,'input_sha256':digest(case['data']),
            'status':'NO_SCHEDULE','solver_status':'UNKNOWN','metrics':None,'payload':None,
            'error':'GraduationSolverError: CP-SAT returned UNKNOWN; no accepted schedule',
            'solver':{'time_limit':1.0,'num_workers':1,'seed':42}}
    monkeypatch.setattr(worker,'evaluate_row',unknown)
    def mocked(script,payload,timeout):
        return worker.execute_rows(unit_context['cases'],Path(payload['output_dir']),time.monotonic()+100)
    monkeypatch.setattr(backend,'supervised_json_process',mocked)
    result=backend.run_main(tmp_path/'control',tmp_path/'evidence',tmp_path/'out')
    assert result['status']=='COMPLETED'
    assert result['status_counts']['NO_SCHEDULE']==480
    assert result['accepted_runs']==0 and result['completed_pairs']==0
    assert result['research_status']=='not_achieved'
    before={p.relative_to(tmp_path/'out'):p.read_bytes() for p in (tmp_path/'out').rglob('*') if p.is_file()}
    checked=backend.recheck_main_run(tmp_path/'out',unit_context['cases'],require_current_sources=True)
    assert checked['planned_calls']==480 and checked['accepted_runs']==0
    assert before=={p.relative_to(tmp_path/'out'):p.read_bytes() for p in (tmp_path/'out').rglob('*') if p.is_file()}
    with pytest.raises(ValueError):
        backend.run_main(tmp_path/'control',tmp_path/'evidence',tmp_path/'out')


def test_worker_self_deadline_is_budget_exhaustion(unit_context,tmp_path,monkeypatch):
    monkeypatch.setattr(backend,'supervised_json_process',lambda *a,**k:{'status':'BUDGET_EXHAUSTED'})
    result=backend.run_main(tmp_path/'control',tmp_path/'evidence',tmp_path/'out')
    assert result['status']=='BUDGET_EXHAUSTED'


def test_resigned_csv_cannot_contradict_checked_rows(unit_context,tmp_path,monkeypatch):
    monkeypatch.setattr(backend,'supervised_json_process',lambda *a,**k:{'status':'WORKER_FINISHED','completed_rows':480})
    folder=tmp_path/'out'
    backend.run_main(tmp_path/'control',tmp_path/'evidence',folder)
    (folder/'raw.csv').write_text('forged performance table\n',encoding='utf-8')
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    manifest['artifacts']['raw.csv']=backend._sha(folder/'raw.csv')
    (folder/'manifest.json').write_bytes(encoded(manifest))
    with pytest.raises(ValueError):
        backend.recheck_main_run(folder,unit_context['cases'])


def test_completed_output_carries_bound_scope_and_evidence_decisions(unit_context,tmp_path,monkeypatch):
    monkeypatch.setattr(backend,'supervised_json_process',lambda *a,**k:{'status':'WORKER_FINISHED','completed_rows':480})
    folder=tmp_path/'out'
    backend.run_main(tmp_path/'control',tmp_path/'evidence',folder)
    approval=json.loads((folder/'authorization.json').read_text(encoding='utf-8'))
    assert approval['scope_decision']['artifact_hash']==unit_context['scope_hash']
    assert approval['evidence_decision']['artifact_hash']==unit_context['evidence_hash']


def test_altered_state_scope_cannot_rebind_a_run(unit_context,tmp_path,monkeypatch):
    def altered(script,payload,timeout):
        path=Path(payload['output_dir'])/'state.json'
        state=json.loads(path.read_text(encoding='utf-8'))
        state['scope_hash']='0'*64
        path.write_bytes(encoded(state))
        return {'status':'WORKER_FINISHED','completed_rows':480,'input_set_sha256':digest(unit_context['cases'])}
    monkeypatch.setattr(backend,'supervised_json_process',altered)
    folder=tmp_path/'out'
    assert backend.run_main(tmp_path/'control',tmp_path/'evidence',folder)['status']=='FAILED'
    state=json.loads((folder/'state.json').read_text(encoding='utf-8'))
    assert state['scope_hash']==unit_context['scope_hash']


def test_stale_gate_after_lock_cannot_dispatch_or_overwrite_control(unit_context,tmp_path,monkeypatch):
    calls=[0]
    def gate(*a,**k):
        calls[0]+=1
        if calls[0]==1:return unit_context
        raise ValueError('Approval/control changed while acquiring the lock')
    monkeypatch.setattr(backend,'execution_context',gate)
    monkeypatch.setattr(backend,'supervised_json_process',lambda *a,**k:pytest.fail('Stale gate dispatched'))
    control=tmp_path/'control';control.mkdir()
    before=encoded({'status':'COMPLETED','owner':'other invocation'})
    (control/'state.json').write_bytes(before)
    with pytest.raises(ValueError):
        backend.run_main(control,tmp_path/'evidence',tmp_path/'out')
    assert not (tmp_path/'out').exists()
    assert (control/'state.json').read_bytes()==before


def test_main_output_cannot_pollute_frozen_scope(unit_context,tmp_path,monkeypatch):
    monkeypatch.setattr(backend,'supervised_json_process',lambda *a,**k:pytest.fail('Overlapping output dispatched'))
    folder=unit_context['scope_dir']/'inside-scope'
    with pytest.raises(ValueError):
        backend.run_main(tmp_path/'control',tmp_path/'evidence',folder)
    assert not folder.exists()


def test_managed_tiny_development_worker_matches_independent_oracle(tmp_path):
    from src.ai_workflow.process_supervisor import supervised_json_process
    from src.graduation.reference_main_results import recheck_row,_data
    from src.graduation.enumeration import enumerate_parallel_maintenance
    script=Path(__file__).parent/'fixtures/g3_tiny_worker.py'
    folder=tmp_path/'managed-development'
    reply=supervised_json_process(script,{'output_dir':str(folder)},30)
    assert reply=={'status':'DEVTEST_COMPLETED','actual_tiny_cp_calls':4,'formal_main_executed':False}
    cases=json.loads((folder/'cases.json').read_text(encoding='utf-8'))
    totals=[]
    for index in range(4):
        case,mode=cases[index//2],('fixed','joint')[index%2]
        trace=json.loads((folder/'rows'/f'{index:04d}.json').read_text(encoding='utf-8'))
        metrics=recheck_row(case,mode,trace)
        oracle=enumerate_parallel_maintenance(_data(case),mode=mode)
        assert trace['solver_status']=='OPTIMAL'
        assert metrics['total_tardiness']==oracle.total_tardiness
        totals.append(metrics['total_tardiness'])
    assert totals==[4,0,6,0]


def test_empty_failed_run_cannot_be_resigned_as_completed(unit_context,tmp_path,monkeypatch):
    monkeypatch.setattr(backend,'supervised_json_process',lambda *a,**k:{'status':'WORKER_FINISHED','completed_rows':480})
    folder=tmp_path/'out'
    backend.run_main(tmp_path/'control',tmp_path/'evidence',folder)
    for name in ('state.json','summary.json','manifest.json'):
        value=json.loads((folder/name).read_text(encoding='utf-8'))
        value['status']='COMPLETED'
        (folder/name).write_bytes(encoded(value))
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    for name in ('state.json','summary.json'):manifest['artifacts'][name]=backend._sha(folder/name)
    (folder/'manifest.json').write_bytes(encoded(manifest))
    with pytest.raises(ValueError):backend.recheck_main_run(folder,unit_context['cases'])


def test_extra_nested_manifest_is_not_an_unchecked_artifact(unit_context,tmp_path,monkeypatch):
    monkeypatch.setattr(backend,'supervised_json_process',lambda *a,**k:{'status':'WORKER_FINISHED','completed_rows':480})
    folder=tmp_path/'out'
    backend.run_main(tmp_path/'control',tmp_path/'evidence',folder)
    (folder/'diagnostics').mkdir(exist_ok=True)
    (folder/'diagnostics/manifest.json').write_bytes(b'{"invented_result":true}')
    with pytest.raises(ValueError):backend.recheck_main_run(folder,unit_context['cases'])


def test_resigned_budget_cannot_refund_execution_time(unit_context,tmp_path,monkeypatch):
    monkeypatch.setattr(backend,'supervised_json_process',lambda *a,**k:{'status':'WORKER_FINISHED','completed_rows':480})
    folder=tmp_path/'out';backend.run_main(tmp_path/'control',tmp_path/'evidence',folder)
    receipt=json.loads((folder/'budget_snapshot.json').read_text(encoding='utf-8'))
    receipt['active_seconds']=0
    receipt['active_seconds_charged']=0
    receipt['remaining_active_seconds']=600
    (folder/'budget_snapshot.json').write_bytes(encoded(receipt))
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    manifest['artifacts']['budget_snapshot.json']=backend._sha(folder/'budget_snapshot.json')
    (folder/'manifest.json').write_bytes(encoded(manifest))
    with pytest.raises(ValueError):backend.recheck_main_run(folder,unit_context['cases'])
