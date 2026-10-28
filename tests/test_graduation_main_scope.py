"""Formal main preparation binds review to real data without executing research."""
import hashlib
import json
import sqlite3

import pytest

from src.ai_workflow import graduation_main_scope as scope
from src.ai_workflow.review import artifact_hash, validate_review_decision
from src.ai_workflow.runtime_budget import BudgetExceeded


@pytest.fixture
def prepared(tmp_path):
    folder = tmp_path/'scope'
    result = scope.prepare_main_scope(folder)
    assert result['status'] == 'WAITING_HUMAN_SCOPE'
    return folder


def test_prepared_materials_cover_every_pair_and_review_gate(prepared):
    result = scope.recheck_main_scope(prepared)
    assert result['paired_requests'] == 240 and result['planned_solver_calls'] == 480
    assert result['primary_pairs'] == 160 and result['sensitivity_pairs'] == 80
    assert result['base_workloads'] == 10
    assert result['solver_calls_executed'] == result['model_calls'] == 0
    assert result['scope_approved'] is False and result['research_status'] == 'not_achieved'
    request = json.loads((prepared/'scope_review.json').read_text(encoding='utf-8'))
    assert request['stage'] == 'scope'
    assert request['artifact_hash'] == artifact_hash({k:v for k,v in request.items() if k != 'artifact_hash'})
    assert request['payload']['next_gate'] == 'evidence'
    assert request['payload']['approval_does_not_start_execution'] is True
    assert 0 < result['preparation_active_seconds'] < 600


def test_no_solver_or_model_is_called(tmp_path, monkeypatch):
    from src.graduation import solver
    def forbidden(*args, **kwargs):
        pytest.fail('Scope preparation must not run a solver')
    monkeypatch.setattr(solver, 'solve_parallel_maintenance', forbidden)
    assert scope.prepare_main_scope(tmp_path/'offline')['solver_calls_executed'] == 0


def test_recheck_is_readonly_and_existing_path_is_not_restarted(prepared):
    before = {p.name:p.read_bytes() for p in prepared.iterdir() if p.is_file()}
    scope.recheck_main_scope(prepared)
    assert before == {p.name:p.read_bytes() for p in prepared.iterdir() if p.is_file()}
    with pytest.raises(FileExistsError):
        scope.prepare_main_scope(prepared)


@pytest.mark.parametrize('name', ['inputs.json','planned_runs.json','aliases.json','summary.json','scope_review.json','protocol.json'])
def test_resigned_material_changes_are_still_rejected(prepared, name):
    path = prepared/name
    value = json.loads(path.read_text(encoding='utf-8'))
    if name == 'inputs.json':
        value[0]['data']['tasks'][0]['due_date'] += 1
    elif name == 'planned_runs.json':
        value[0], value[1] = value[1], value[0]
    elif name == 'aliases.json':
        value.clear()
    elif name == 'summary.json':
        value['base_workloads'] = 240
    elif name == 'scope_review.json':
        value['payload']['budget']['max_active_seconds'] = 900
        value['artifact_hash'] = artifact_hash({k:v for k,v in value.items() if k != 'artifact_hash'})
    else:
        value['solver']['time_limit'] = 10
    path.write_bytes(scope.encoded(value))
    manifest = json.loads((prepared/'manifest.json').read_text(encoding='utf-8'))
    manifest['artifacts'][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (prepared/'manifest.json').write_bytes(scope.encoded(manifest))
    with pytest.raises(ValueError):
        scope.recheck_main_scope(prepared)


def test_missing_budget_is_not_recreated(prepared):
    (prepared/'budget.sqlite').unlink()
    with pytest.raises(ValueError):
        scope.recheck_main_scope(prepared)
    assert not (prepared/'budget.sqlite').exists()


def test_stale_scope_hash_cannot_be_used_for_human_decision(prepared):
    request = json.loads((prepared/'scope_review.json').read_text(encoding='utf-8'))
    with pytest.raises(ValueError):
        validate_review_decision(request, {'stage':'scope','artifact_hash':'0'*64,
            'decision':'approve','reviewer':'human','note':''})


@pytest.mark.parametrize('reservation',[1e9,1e-10])
def test_preparation_reservation_tampering_is_rejected(prepared,reservation):
    db=sqlite3.connect(prepared/'budget.sqlite')
    try:
        db.execute('UPDATE workflow_segments SET reserved_seconds=?',(reservation,))
        db.commit()
    finally:
        db.close()
    with pytest.raises(ValueError):
        scope.recheck_main_scope(prepared)


def test_wal_ledger_is_rejected_without_creating_sidecars(prepared):
    db=sqlite3.connect(prepared/'budget.sqlite')
    try:
        db.execute('PRAGMA journal_mode=WAL').fetchone()
    finally:
        db.close()
    before={p.name:p.read_bytes() for p in prepared.iterdir() if p.is_file()}
    with pytest.raises(ValueError):
        scope.recheck_main_scope(prepared)
    assert before=={p.name:p.read_bytes() for p in prepared.iterdir() if p.is_file()}


@pytest.mark.parametrize('request_call',[1,2,3])
def test_slow_review_material_cannot_escape_preparation_deadline(tmp_path,monkeypatch,request_call):
    original_request,original_clock=scope._request,scope.time.monotonic
    offset,calls=[0],[0]
    def delayed(*args,**kwargs):
        calls[0]+=1
        result=original_request(*args,**kwargs)
        if calls[0]==request_call:
            offset[0]=601
        return result
    monkeypatch.setattr(scope,'_request',delayed)
    monkeypatch.setattr(scope.time,'monotonic',lambda:original_clock()+offset[0])
    with pytest.raises((BudgetExceeded,ValueError)):
        scope.prepare_main_scope(tmp_path/'slow')


def test_boolean_manifest_version_is_rejected(prepared):
    manifest=json.loads((prepared/'manifest.json').read_text(encoding='utf-8'))
    manifest['version']=True
    (prepared/'manifest.json').write_bytes(scope.encoded(manifest))
    with pytest.raises(ValueError):
        scope.recheck_main_scope(prepared)


def test_subdeadline_finalization_time_is_not_refunded(tmp_path,monkeypatch):
    original_request,original_clock=scope._request,scope.time.monotonic
    offset,calls=[0],[0]
    def slow_final(*args,**kwargs):
        calls[0]+=1
        result=original_request(*args,**kwargs)
        if calls[0]==3:
            offset[0]=500
        return result
    monkeypatch.setattr(scope,'_request',slow_final)
    monkeypatch.setattr(scope.time,'monotonic',lambda:original_clock()+offset[0])
    with pytest.raises(BudgetExceeded):
        scope.prepare_main_scope(tmp_path/'slow-final')


def test_initial_source_hashing_is_inside_preparation_budget(tmp_path,monkeypatch):
    original_sources,original_clock=scope._sources,scope.time.monotonic
    offset,calls=[0],[0]
    def slow_sources():
        calls[0]+=1
        result=original_sources()
        if calls[0]==1:
            offset[0]=601
        return result
    monkeypatch.setattr(scope,'_sources',slow_sources)
    monkeypatch.setattr(scope.time,'monotonic',lambda:original_clock()+offset[0])
    with pytest.raises((BudgetExceeded,ValueError)):
        scope.prepare_main_scope(tmp_path/'slow-source')


def test_ledger_settlement_is_inside_prepaid_window(tmp_path,monkeypatch):
    original_budget,original_clock=scope._budget,scope.time.monotonic
    offset=[0]
    def slow_settlement(*args,**kwargs):
        result=original_budget(*args,**kwargs)
        if kwargs.get('before_finalization'):
            offset[0]=500
        return result
    monkeypatch.setattr(scope,'_budget',slow_settlement)
    monkeypatch.setattr(scope.time,'monotonic',lambda:original_clock()+offset[0])
    with pytest.raises(BudgetExceeded):
        scope.prepare_main_scope(tmp_path/'slow-settlement')
