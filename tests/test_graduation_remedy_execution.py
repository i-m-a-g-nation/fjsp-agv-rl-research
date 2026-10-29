"""Execution gates use zero-call workers and TEST_ONLY control folders."""
from pathlib import Path
import json
import time
import os
import shutil

import pytest

from experiments import exp_033_graduation_remedy as run
from src.ai_workflow.process_supervisor import supervised_json_process


def test_missing_approval_refuses_before_creating_output_or_budget(tmp_path):
    review=tmp_path/'TEST_ONLY-review';review.mkdir();out=tmp_path/'out'
    with pytest.raises((ValueError,FileNotFoundError)):
        run.run_once(run.PROPOSAL,review,out,review/'not-validation.json')
    assert not out.exists() and not (review/'budget.sqlite').exists()


def test_real_internal_worker_expired_deadline_cannot_solve(tmp_path):
    reply=supervised_json_process(Path(run.__file__).resolve(),{
        'purpose':'APPROVED_REMEDY_ONLY','deadline':time.monotonic()-1,
        'output_dir':str(tmp_path),'review_dir':str(tmp_path),'lease_sha256':'0'*64},15)
    assert reply['status']=='DEADLINE_EXHAUSTED' and reply['attempted_requests']==0


def test_zero_call_partial_attempt_is_settled_and_cannot_restart(tmp_path,monkeypatch):
    review=tmp_path/'TEST_ONLY-review';review.mkdir();out=tmp_path/'out'
    (review/'approval.json').write_bytes(b'{"kind":"TEST_ONLY-not-human"}')
    monkeypatch.setattr(run,'approval',lambda *a,**k:{'kind':'TEST_ONLY-synthetic-decision'})
    monkeypatch.setattr(run,'full_gate',lambda *a,**k:run.scope.materials())
    monkeypatch.setattr(run,'copy_context',lambda *a,**k:None)
    monkeypatch.setattr(run,'review_hashes',lambda *a,**k:{})
    monkeypatch.setattr(run,'old_ledger_sha',lambda:'TEST_ONLY-unchanged-original')
    monkeypatch.setattr(run,'supervised_json_process',lambda *a,**k:{'status':'DEADLINE_EXHAUSTED','attempted_requests':0})
    result=run.run_once(run.PROPOSAL,review,out,review/'TEST_ONLY-validation.json')
    assert result['status']=='DEVELOPMENT_PARTIAL' and result['attempted_requests']==0
    assert result['planned_requests']==14 and result['accepted_for_research'] is False
    snapshot=run.read_budget(review)
    assert snapshot['active_seconds_reserved']==0 and snapshot['active_seconds']>0
    before=(review/'budget.sqlite').read_bytes()
    monkeypatch.setattr(run,'supervised_json_process',lambda *a,**k:pytest.fail('Attempt retried'))
    with pytest.raises((ValueError,FileExistsError)):
        run.run_once(run.PROPOSAL,review,tmp_path/'second-out',review/'TEST_ONLY-validation.json')
    assert (review/'budget.sqlite').read_bytes()==before


def test_unleased_internal_worker_never_dispatches_a_request(tmp_path,monkeypatch):
    monkeypatch.setattr(run,'capture_configured',lambda *a,**k:pytest.fail('Unleased worker solved'))
    reply=run.worker({'purpose':'APPROVED_REMEDY_ONLY','deadline':time.monotonic()+10,
        'output_dir':str(tmp_path/'out'),'review_dir':str(tmp_path/'review'),'lease_sha256':'0'*64})
    assert reply['status']=='DEVELOPMENT_FAILED' and reply['attempted_requests']==0


def test_new_budget_reader_never_initializes_a_missing_ledger(tmp_path):
    with pytest.raises(ValueError):run.read_budget(tmp_path)
    assert not (tmp_path/'budget.sqlite').exists()


@pytest.mark.parametrize('ci',[
    {'headSha':'wrong','conclusion':'success'},
    {'headSha':run.BASE_CI_SHA,'conclusion':'failure'},
])
def test_prior_commit_or_failed_CI_cannot_satisfy_the_gate(ci):
    with pytest.raises(ValueError):run.check_ci(ci)


@pytest.mark.parametrize('receipt',[
    {'status':'CAPTURED','attempted_requests':0},{'status':'CAPTURED','attempted_requests':15},
    {'status':'CAPTURED','attempted_requests':True},{'status':'FORMAL_SUCCESS','attempted_requests':14},
])
def test_false_or_over_cap_native_counts_are_rejected(receipt):
    with pytest.raises(ValueError):run.check_receipt(receipt,14)


def test_historical_result_tree_is_never_used_as_runtime_output(tmp_path):
    with pytest.raises(ValueError):run.guard_paths(tmp_path/'review',run.ROOT/'experiments/results/TEST_ONLY-forbidden')


def test_supervisor_exit_retains_interruption_and_unknown_call_count(tmp_path,monkeypatch):
    review=tmp_path/'TEST_ONLY-killed';review.mkdir();out=tmp_path/'out'
    (review/'approval.json').write_bytes(b'{"kind":"TEST_ONLY-not-human"}')
    monkeypatch.setattr(run,'approval',lambda *a,**k:{'kind':'TEST_ONLY-synthetic-decision'})
    monkeypatch.setattr(run,'full_gate',lambda *a,**k:run.scope.materials())
    monkeypatch.setattr(run,'copy_context',lambda *a,**k:None)
    monkeypatch.setattr(run,'review_hashes',lambda *a,**k:{})
    monkeypatch.setattr(run,'old_ledger_sha',lambda:'TEST_ONLY-unchanged-original')
    def killed(*a,**k):
        state=run.read(out/'state.json');state['rows'][0]['status']='RUNNING';run.write(out/'state.json',state)
        raise RuntimeError('TEST_ONLY-supervisor-exit')
    monkeypatch.setattr(run,'supervised_json_process',killed)
    result=run.run_once(run.PROPOSAL,review,out,review/'TEST_ONLY-validation.json')
    assert result['status']=='DEVELOPMENT_FAILED' and result['planned_requests']==14
    assert run.read(out/'state.json')['rows'][0]['status']=='INTERRUPTED'
    receipt=run.read(out/'worker_receipt.json')
    assert receipt['status']=='SUPERVISOR_ERROR' and receipt['attempted_requests'] is None
    assert run.read_budget(out)==run.read(out/'budget_snapshot.json')


def test_denied_raw_reply_cannot_be_normalized_into_approval(tmp_path,monkeypatch):
    review=tmp_path/'TEST_ONLY-denied';review.mkdir();monkeypatch.setattr(run,'ROOT',tmp_path)
    raw={'questionItemId':'["request_user_input_async","call_abf95b525fbb402ab0a44191fe83cfdf",0]',
         'question':'6f9f88f8','answer':'暂不批准，只保留提案'}
    run.write(review/'raw_authorization.json',raw)
    a={'kind':'ACTUAL_USER_AUTHORIZATION','scope_sha256':run.SCOPE_SHA,
       'scope_approved':True,'new_budget_approved':True,'native_execution_approved':True,
       'packet_manifest_sha256':run.sha(run.PROPOSAL/'manifest.json'),
       'raw_authorization_sha256':run.sha(review/'raw_authorization.json'),'recorded_review_dir':review.name,
       'constraints':{'planned_solver_calls':14,'max_active_seconds':60,'max_time_in_seconds':1.,
           'num_search_workers':1,'random_seed':42,'model_calls':0,'attempts':1,'formal_G3_rerun':False,'RL_training':False}}
    run.write(review/'approval.json',a)
    with pytest.raises(ValueError):run.approval(run.PROPOSAL,review)


def context_fixture(tmp_path,monkeypatch,*,active=False,fresh=False):
    """Explicit TEST_ONLY synthetic authority/logs; never used for native execution."""
    review=tmp_path/'TEST_ONLY-context';review.mkdir();out=tmp_path/'out'
    if not fresh:out.mkdir()
    bundle=run.scope.materials();source_map=run.sources()
    raw={'questionItemId':'["request_user_input_async","call_abf95b525fbb402ab0a44191fe83cfdf",0]',
         'question':'TEST_ONLY fixture for6f9f88f8','answer':'批准该范围与新60秒预算，按条件实施并执行一次'}
    run.write(review/'raw_authorization.json',raw)
    a={'kind':'ACTUAL_USER_AUTHORIZATION','fixture':'TEST_ONLY synthetic; not a real grant',
       'scope_sha256':run.SCOPE_SHA,'scope_approved':True,'new_budget_approved':True,'native_execution_approved':True,
       'packet_manifest_sha256':run.sha(run.PROPOSAL/'manifest.json'),
       'raw_authorization_sha256':run.sha(review/'raw_authorization.json'),'recorded_review_dir':run.review_id(review),
       'constraints':{'planned_solver_calls':14,'max_active_seconds':60,'max_time_in_seconds':1.,
           'num_search_workers':1,'random_seed':42,'model_calls':0,'attempts':1,'formal_G3_rerun':False,'RL_training':False}}
    run.write(review/'approval.json',a)
    if not fresh:
        run.write(review/'attempt.json',{'scope_sha256':run.SCOPE_SHA,'attempt':1,'output_dir':str(out.resolve()),
            'approval_sha256':run.sha(review/'approval.json'),'review_dir':run.review_id(review)})
    run.write(review/'base_ci.json',{'headSha':run.BASE_CI_SHA,'conclusion':'success','status':'completed','fixture':'TEST_ONLY'})
    run.write(review/'code_review.json',{'status':'NO_IMPORTANT_FINDINGS','source_hashes':source_map,'fixture':'TEST_ONLY'})
    log=review/'TEST_ONLY-validation.log';log.write_text('23 passed in 0.01s\n',encoding='utf-8')
    validation=review/'TEST_ONLY-validation.json'
    run.write(validation,{'status':'PASSED','source_hashes':source_map,'exit_code':0,'passed':23,
        'test_hashes':{n:run.sha(run.ROOT/n) for n in run.TESTS},'runtime':run.runtime_identity(),
        'log_name':log.name,'log_sha256':run.sha(log),'fixture':'TEST_ONLY synthetic log; never actual validation'})
    monkeypatch.setattr(run,'old_ledger_sha',lambda:bundle['protocol']['original_locked_ledger_sha256'])
    if fresh:return review,out,validation,None
    budget=run.RunBudget(review/'budget.sqlite',run.LIMITS);segment,_=budget.reserve_active_segment()
    run.write(out/'state.json',run.initial(bundle));run.write(out/'admission.json',{'admitted':True,'validation_record':validation.name})
    run.copy_context(out,run.PROPOSAL,review,validation,bundle)
    if active:
        deadline=time.monotonic()+40
        lease={'parent_pid':os.getppid(),'output_dir':str(out.resolve()),'deadline':deadline,
            'sources':source_map,'runtime':run.runtime_identity(),'approval_sha256':run.sha(review/'approval.json'),
            'ledger_sha256':run.sha(review/'budget.sqlite'),'old_ledger_sha256':run.old_ledger_sha(),'segment':segment,
            'validation_name':validation.name,'admission_sha256':run.sha(out/'admission.json'),
            'review_files':run.review_hashes(review,validation),
            'packet_files':run.read(run.PROPOSAL/'manifest.json')['files_sha256']|{'manifest.json':run.sha(run.PROPOSAL/'manifest.json')}}
        run.write(review/'worker_lease.json',lease)
        monkeypatch.setattr(run.sys,'argv',['worker',str(os.getppid())])
        payload={'purpose':'APPROVED_REMEDY_ONLY','deadline':deadline,'review_dir':str(review),
                 'output_dir':str(out),'lease_sha256':run.sha(review/'worker_lease.json')}
        return review,out,validation,payload
    budget.finish_active_segment(segment,.1);extra,_=budget.reserve_active_segment();budget.finish_active_segment(extra,5.)
    shutil.copyfile(review/'budget.sqlite',out/'budget.sqlite');run.write(out/'budget_snapshot.json',run.read_budget(out))
    receipt={'status':'DEVELOPMENT_FAILED','attempted_requests':0,'error':'TEST_ONLY-stop-before-Solve'}
    run.write(out/'worker_receipt.json',receipt)
    summary=run.collect(out,bundle);summary.update(status='DEVELOPMENT_PARTIAL',attempted_requests=0)
    run.write(out/'summary.json',summary)
    manifest={'status':'DEVELOPMENT_PARTIAL','source_hashes':source_map,
        'files_sha256':{p.relative_to(out).as_posix():run.sha(p) for p in out.rglob('*') if p.is_file()}}
    run.write(out/'manifest.json',manifest)
    return review,out,validation,None


@pytest.mark.parametrize('fault',[None,'sources','review','runtime','budget'])
def test_saved_provenance_is_not_just_a_rehashed_file_list(tmp_path,monkeypatch,fault):
    _,out,_,_=context_fixture(tmp_path,monkeypatch)
    assert run.recheck(out)['captures']==0
    if fault is None:return
    manifest=run.read(out/'manifest.json')
    if fault=='sources':manifest['source_hashes']={}
    elif fault=='review':
        value=run.read(out/'validation/code_review.json');value['source_hashes']={};run.write(out/'validation/code_review.json',value)
    elif fault=='runtime':
        value=run.read(out/'runtime.json');value['python']='0.0.0 TEST_ONLY';run.write(out/'runtime.json',value)
    else:
        value=run.read(out/'budget_snapshot.json');value['active_seconds']=0.;run.write(out/'budget_snapshot.json',value)
    manifest['files_sha256']={p.relative_to(out).as_posix():run.sha(p) for p in out.rglob('*')
        if p.is_file() and p.relative_to(out).as_posix()!='manifest.json'}
    run.write(out/'manifest.json',manifest)
    with pytest.raises(ValueError):run.recheck(out)


@pytest.mark.parametrize('fault',['empty_review_set','changed_review','missing_marker','changed_marker'])
def test_live_lease_cannot_bypass_the_full_conditional_gate(tmp_path,monkeypatch,fault):
    review,out,validation,payload=context_fixture(tmp_path,monkeypatch,active=True)
    monkeypatch.setattr(run,'capture_configured',lambda *a,**k:pytest.fail('Conditional gate was bypassed'))
    lease=run.read(review/'worker_lease.json')
    if fault=='empty_review_set':lease['review_files']={}
    elif fault=='changed_review':
        value=run.read(review/'code_review.json');value['status']='IMPORTANT_FINDINGS';run.write(review/'code_review.json',value)
        lease['review_files']=run.review_hashes(review,validation)
    elif fault=='missing_marker':(review/'attempt.json').unlink()
    else:
        value=run.read(review/'attempt.json');value['attempt']=2;run.write(review/'attempt.json',value)
        lease['review_files']=run.review_hashes(review,validation)
    run.write(review/'worker_lease.json',lease);payload['lease_sha256']=run.sha(review/'worker_lease.json')
    with run._exclusive_lock(review):reply=run.worker(payload)
    assert reply['status']=='DEVELOPMENT_FAILED' and reply['attempted_requests']==0
    assert all(r['status']=='NOT_RUN' for r in run.read(out/'state.json')['rows'])


def test_valid_live_admission_reaches_only_the_test_stop_before_solver(tmp_path,monkeypatch):
    review,out,_,payload=context_fixture(tmp_path,monkeypatch,active=True)
    reached=[]
    def stop(case,mode,presolve):
        reached.append((case['case_id'],mode,presolve));raise RuntimeError('TEST_ONLY-before-real-solver')
    monkeypatch.setattr(run,'capture_configured',stop)
    with run._exclusive_lock(review):reply=run.worker(payload)
    assert reply['status']=='DEVELOPMENT_FAILED' and reply['attempted_requests']==1
    assert len(reached)==1 and reached[0][1:]==('joint',True)


def test_failed_supervisor_receipt_can_be_replayed_without_promoting_a_result(tmp_path,monkeypatch):
    _,out,_,_=context_fixture(tmp_path,monkeypatch)
    state=run.read(out/'state.json');state['status']='DEVELOPMENT_FAILED';state['rows'][0]['status']='INTERRUPTED'
    run.write(out/'state.json',state)
    run.write(out/'worker_receipt.json',{'status':'SUPERVISOR_ERROR','attempted_requests':None,'error':'TEST_ONLY-killed'})
    bundle={k:run.read(out/'approved_scope'/(k+'.json')) for k in ('protocol','inputs','planned_runs')}
    summary=run.collect(out,bundle)
    summary.update(status='DEVELOPMENT_FAILED',attempted_requests=None,error='TEST_ONLY-killed',automatic_retry=False)
    run.write(out/'summary.json',summary)
    m=run.read(out/'manifest.json');m['status']='DEVELOPMENT_FAILED'
    m['files_sha256']={p.relative_to(out).as_posix():run.sha(p) for p in out.rglob('*')
        if p.is_file() and p.relative_to(out).as_posix()!='manifest.json'}
    run.write(out/'manifest.json',m)
    replay=run.recheck(out)
    assert replay['recorded_batch_status']=='DEVELOPMENT_FAILED' and replay['captures']==0
    assert replay['accepted_for_research'] is False and replay['new_solver_calls']==0


@pytest.mark.parametrize('bad',[b'{',b'{}'])
def test_malformed_preflight_validation_still_has_recheckable_zero_call_evidence(tmp_path,monkeypatch,bad):
    review,out,validation,_=context_fixture(tmp_path,monkeypatch,fresh=True)
    validation.write_bytes(bad)
    monkeypatch.setattr(run,'supervised_json_process',lambda *a,**k:pytest.fail('Malformed preflight dispatched'))
    summary=run.run_once(run.PROPOSAL,review,out,validation)
    assert summary['status']=='DEVELOPMENT_FAILED' and summary['attempted_requests']==0
    replay=run.recheck(out)
    assert replay['recorded_batch_status']=='DEVELOPMENT_FAILED' and replay['captures']==0
