"""The next counterfactual is a bounded proposal, never execution permission."""
import json

import pytest

from experiments import exp_032_graduation_remedy_scope as scope


def test_prepare_keeps_fourteen_requests_and_cannot_call_a_solver(tmp_path,monkeypatch):
    from src.graduation import solver
    monkeypatch.setattr(solver.cp_model,'CpSolver',lambda:pytest.fail('Proposal called solver'))
    out=tmp_path/'proposal'
    receipt=scope.prepare(out)
    assert receipt['status']=='WAITING_SCOPE_AND_NEW_BUDGET'
    protocol=json.loads((out/'protocol.json').read_text(encoding='utf-8'))
    requests=json.loads((out/'planned_runs.json').read_text(encoding='utf-8'))
    assert len(requests)==14
    assert [(r['original_sequence'],r['cp_model_presolve']) for r in requests[:10]]==[
        (167,True),(167,False),(186,True),(186,False),(222,True),(222,False),
        (226,True),(226,False),(229,True),(229,False)]
    assert [(r['mode'],r['cp_model_presolve'],r['expected_tardiness']) for r in requests[10:]]==[
        ('fixed',True,4),('fixed',False,4),('joint',True,0),('joint',False,0)]
    assert protocol['new_budget']['max_active_seconds']==60
    assert protocol['authorization']['native_execution_approved'] is False
    assert protocol['native_solver_calls']==protocol['model_calls']==0
    assert not list(out.glob('*.sqlite'))
    assert scope.recheck(out)['status']=='VERIFIED_UNAPPROVED_PROPOSAL'


def test_original_proposal_is_never_overwritten(tmp_path):
    out=tmp_path/'proposal';scope.prepare(out);before=(out/'manifest.json').read_bytes()
    with pytest.raises(FileExistsError):scope.prepare(out)
    assert (out/'manifest.json').read_bytes()==before


@pytest.mark.parametrize('fault',['approved','omitted_request','input','budget'])
def test_rehashed_material_change_still_fails_against_frozen_proposal(tmp_path,fault):
    out=tmp_path/'proposal';scope.prepare(out)
    name='planned_runs.json' if fault=='omitted_request' else 'inputs.json' if fault=='input' else 'protocol.json'
    value=scope.read(out/name)
    if fault=='approved':value['authorization']['native_execution_approved']=True
    elif fault=='omitted_request':value.pop()
    elif fault=='input':value[-1]['data']['tasks'][0]['processing_time']=3
    else:value['new_budget']['max_active_seconds']=600
    scope.write(out/name,value)
    manifest=scope.read(out/'manifest.json')
    manifest['files_sha256'][name]=scope.sha(out/name);scope.write(out/'manifest.json',manifest)
    with pytest.raises(ValueError):scope.recheck(out)


def test_tiny_control_expectations_match_independent_enumeration():
    from src.graduation.reference_main_results import _data
    from src.graduation.enumeration import enumerate_parallel_maintenance
    control=scope.materials()['inputs'][-1]
    assert enumerate_parallel_maintenance(_data(control),mode='fixed').total_tardiness==4
    assert enumerate_parallel_maintenance(_data(control),mode='joint').total_tardiness==0


def test_cli_has_no_execution_command_or_budget_side_effect(tmp_path):
    out=tmp_path/'not-created'
    with pytest.raises(SystemExit) as stopped:scope.main(['run','--output-dir',str(out)])
    assert stopped.value.code==2 and not out.exists()


@pytest.mark.parametrize('relative',['extra.json','nested/manifest.json'])
def test_unindexed_files_are_rejected_even_when_named_manifest(tmp_path,relative):
    out=tmp_path/'proposal';scope.prepare(out)
    extra=out/relative;extra.parent.mkdir(parents=True,exist_ok=True);extra.write_bytes(b'{}')
    with pytest.raises(ValueError):scope.recheck(out)
