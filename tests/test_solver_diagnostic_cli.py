"""Managed development entry, with zero native solve calls in these tests."""
import json
from pathlib import Path
import time

import pytest

from experiments import exp_031_graduation_solver_diagnostics as cli
from src.ai_workflow.process_supervisor import supervised_json_process


def test_audit_does_not_solve_or_create_an_output(monkeypatch,capsys):
    from src.graduation import solver
    monkeypatch.setattr(solver.cp_model,'CpSolver',lambda:pytest.fail('Audit invoked a solver'))
    assert cli.main(['audit'])==0
    value=json.loads(capsys.readouterr().out)
    assert value['solver_calls']==0 and value['selected_error_requests']==5


def test_real_worker_rejects_unknown_payload_before_search():
    reply=supervised_json_process(Path(cli.__file__).resolve(),{'TEST_ONLY-invalid':True},20)
    assert reply['status']=='REJECTED_PAYLOAD'


def test_real_worker_expired_deadline_keeps_all_five_requests_unrun(tmp_path):
    selection=cli.audit_saved_failures(cli.ARCHIVE)
    out=tmp_path/'out';out.mkdir()
    cli.write(out/'state.json',cli.initial_state(selection))
    reply=supervised_json_process(Path(cli.__file__).resolve(),{
        'purpose':'DEVELOPMENT_DIAGNOSIS_ONLY','archive':str(cli.ARCHIVE),'output_dir':str(out),
        'selection_sha256':cli.digest(selection),'source_hashes':cli.source_hashes(),
        'deadline':time.monotonic()-1,'lease_sha256':'0'*64},20)
    assert reply['status']=='DEADLINE_EXHAUSTED' and reply['diagnostic_solver_calls']==0
    assert all(r['status']=='NOT_RUN' for r in cli.read(out/'state.json')['rows'])
    assert not (out/'captures').exists()


def test_six_requests_cannot_be_dispatched(tmp_path,monkeypatch):
    selection=cli.audit_saved_failures(cli.ARCHIVE)
    selection['requests'].append(selection['requests'][0])
    monkeypatch.setattr(cli,'audit_saved_failures',lambda _:selection)
    monkeypatch.setattr(cli,'supervised_json_process',lambda *a,**k:pytest.fail('Over-cap dispatch'))
    with pytest.raises(ValueError):cli.run_development(tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_existing_output_is_not_restarted(tmp_path,monkeypatch):
    out=tmp_path/'out';out.mkdir();(out/'keep.txt').write_bytes(b'keep')
    monkeypatch.setattr(cli,'supervised_json_process',lambda *a,**k:pytest.fail('Restarted'))
    with pytest.raises(FileExistsError):cli.run_development(out)
    assert (out/'keep.txt').read_bytes()==b'keep'


def test_receipt_never_hashes_a_live_controller_lock(tmp_path,monkeypatch):
    """Simulate mandatory Windows byte locking, without a solver or real ledger."""
    import shutil
    from src.ai_workflow.graduation_main_budget import read_main_budget
    from src.ai_workflow.graduation_main_evidence import ROOT,SCOPE_ARCHIVE
    scope=tmp_path/'TEST_ONLY-scope'
    shutil.copytree(ROOT/SCOPE_ARCHIVE,scope)
    monkeypatch.setattr(cli,'load_scope_context',lambda _:{'scope_dir':scope})
    monkeypatch.setattr(cli,'supervised_json_process',lambda *a,**k:{'status':'DEADLINE_EXHAUSTED','diagnostic_solver_calls':0})
    original_sha=cli.sha
    def locked(p):
        if Path(p).name=='controller.lock':raise PermissionError('TEST_ONLY-live locked file')
        return original_sha(p)
    monkeypatch.setattr(cli,'sha',locked)
    result=cli.run_development(tmp_path/'out')
    assert result['status']=='DEVELOPMENT_PARTIAL'
    assert read_main_budget(scope)['active_seconds_reserved']==0
    assert read_main_budget(scope)['remaining_active_seconds']>0


def test_exhausted_original_budget_cannot_dispatch_or_be_recreated(tmp_path,monkeypatch):
    import hashlib
    import shutil
    from src.ai_workflow.graduation_main_evidence import ROOT,SCOPE_ARCHIVE
    from src.ai_workflow.runtime_budget import RunBudget,BudgetLimits
    scope=tmp_path/'TEST_ONLY-exhausted-scope';shutil.copytree(ROOT/SCOPE_ARCHIVE,scope)
    RunBudget(scope/'budget.sqlite',BudgetLimits(600,0,0)).reserve_active_segment()
    before=hashlib.sha256((scope/'budget.sqlite').read_bytes()).hexdigest()
    monkeypatch.setattr(cli,'load_scope_context',lambda _:{'scope_dir':scope})
    monkeypatch.setattr(cli,'supervised_json_process',lambda *a,**k:pytest.fail('Exhausted budget dispatched'))
    result=cli.run_development(tmp_path/'out')
    assert result['status']=='DEVELOPMENT_FAILED'
    assert 'BudgetExceeded' in result['error']
    assert hashlib.sha256((scope/'budget.sqlite').read_bytes()).hexdigest()==before


def test_historical_replay_requires_explicit_captured_source_bytes():
    archive=cli.ROOT/'experiments/results/exp_031_consistency_diagnostic_dev_v1'
    with pytest.raises(ValueError,match='source'):
        cli.recheck_development(archive/'run')
    result=cli.recheck_development(archive/'run',captured_sources=archive/'captured_sources')
    assert result['captures']==result['reproduced_errors']==5 and result['new_solver_calls']==0
    assert 'experiments/exp_031_graduation_solver_diagnostics.py' in result['source_snapshot_files']


@pytest.mark.parametrize('fault',['missing','extra','baseline','snapshot'])
def test_source_map_or_snapshot_tampering_is_rejected(tmp_path,fault):
    import shutil
    archive=cli.ROOT/'experiments/results/exp_031_consistency_diagnostic_dev_v1'
    manifest=cli.read(archive/'run/manifest.json')
    snapshots=tmp_path/'captured_sources';shutil.copytree(archive/'captured_sources',snapshots)
    if fault=='missing':manifest['source_hashes'].pop('src/graduation/solver.py')
    elif fault=='extra':manifest['source_hashes']['TEST_ONLY-extra.py']='0'*64
    elif fault=='baseline':manifest['source_hashes']['src/graduation/solver.py']='0'*64
    else:(snapshots/'exp_031_graduation_solver_diagnostics.py').write_bytes(b'TEST_ONLY-tampered')
    with pytest.raises(ValueError,match='source'):
        cli._recheck_sources(manifest,snapshots)


@pytest.mark.parametrize('key,bad',[
    ('status','FORMAL_SUCCESS'),('accepted_for_research',True),('new_formal_benchmark_calls',1),
    ('model_calls',1),('original_experiment_status','COMPLETED'),('formal_results_modified',True),
    ('research_status','achieved'),('diagnostic_solver_calls',6),
])
def test_replay_never_promotes_a_development_receipt(key,bad):
    derived={'planned_requests':5,'captures':[],'reproduced_errors':0,'complete_captures':0,'uncompleted_requests':5}
    saved={**derived,'status':'DEVELOPMENT_PARTIAL','original_experiment_status':'FAILED',
           'formal_results_modified':False,'accepted_for_research':False,'new_formal_benchmark_calls':0,
           'model_calls':0,'research_status':'not_achieved','diagnostic_solver_calls':0}
    receipt={'status':'DEADLINE_EXHAUSTED','diagnostic_solver_calls':0}
    cli._recheck_summary(saved,derived,receipt)
    saved[key]=bad
    with pytest.raises(ValueError):cli._recheck_summary(saved,derived,receipt)


def test_public_hashes_cannot_dispatch_worker_without_live_parent_lease(tmp_path,monkeypatch):
    selection=cli.audit_saved_failures(cli.ARCHIVE)
    out=tmp_path/'TEST_ONLY-forged-worker';out.mkdir()
    cli.write(out/'state.json',cli.initial_state(selection))
    monkeypatch.setattr(cli,'capture_case',lambda *a,**k:pytest.fail('Unleased worker dispatched'))
    reply=cli.worker({'purpose':'DEVELOPMENT_DIAGNOSIS_ONLY','archive':str(cli.ARCHIVE),
        'output_dir':str(out),'selection_sha256':cli.digest(selection),
        'source_hashes':cli.source_hashes(),'deadline':time.monotonic()+15,'lease_sha256':'0'*64})
    assert reply['status']=='DEVELOPMENT_FAILED' and reply['diagnostic_solver_calls']==0
    assert not (out/'captures').exists()


def test_legacy_public_payload_is_rejected_without_dispatch(tmp_path,monkeypatch):
    selection=cli.audit_saved_failures(cli.ARCHIVE)
    out=tmp_path/'TEST_ONLY-legacy-worker';out.mkdir()
    cli.write(out/'state.json',cli.initial_state(selection))
    monkeypatch.setattr(cli,'capture_case',lambda *a,**k:pytest.fail('Legacy unleased worker dispatched'))
    reply=cli.worker({'purpose':'DEVELOPMENT_DIAGNOSIS_ONLY','archive':str(cli.ARCHIVE),
        'output_dir':str(out),'selection_sha256':cli.digest(selection),
        'source_hashes':cli.source_hashes(),'deadline':time.monotonic()+15})
    assert reply=={'status':'REJECTED_PAYLOAD','diagnostic_solver_calls':0}


@pytest.mark.parametrize('fault',[None,'unlocked','settled','wrong_parent'])
def test_worker_lease_requires_live_lock_parent_and_original_reservation(tmp_path,monkeypatch,fault):
    import os
    import shutil
    from contextlib import nullcontext
    from src.ai_workflow.graduation_main_evidence import ROOT,SCOPE_ARCHIVE
    from src.ai_workflow.runtime_budget import RunBudget,BudgetLimits
    scope=tmp_path/'TEST_ONLY-lease-scope';shutil.copytree(ROOT/SCOPE_ARCHIVE,scope)
    budget=RunBudget(scope/'budget.sqlite',BudgetLimits(600,0,0));segment,_=budget.reserve_active_segment()
    if fault=='settled':budget.finish_active_segment(segment,.01)
    out=tmp_path/'TEST_ONLY-lease-output';control=out.with_name(out.name+'-control');control.mkdir()
    deadline=time.monotonic()+14
    lease={'parent_pid':os.getppid() if fault!='wrong_parent' else -1,'scope_dir':str(scope.resolve()),
           'output_dir':str(out.resolve()),'segment_id':segment,'ledger_sha256':cli.sha(scope/'budget.sqlite'),
           'deadline':deadline,'selection_sha256':'TEST_ONLY-selection','source_hashes':{'TEST_ONLY-source':'bytes'}}
    cli.write(control/'worker_lease.json',lease)
    payload={'output_dir':str(out),'deadline':deadline,'selection_sha256':lease['selection_sha256'],
             'source_hashes':lease['source_hashes'],'lease_sha256':cli.sha(control/'worker_lease.json')}
    monkeypatch.setattr(cli,'load_scope_context',lambda _:{'scope_dir':scope})
    monkeypatch.setattr(cli.sys,'argv',['worker',str(os.getppid())])
    with cli._exclusive_lock(control) if fault!='unlocked' else nullcontext():
        if fault is None:cli._check_worker_lease(payload)
        else:
            with pytest.raises(ValueError):cli._check_worker_lease(payload)
