"""Synthetic approvals and receipts test evidence gates; no real approval is made."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from src.ai_workflow import graduation_main_evidence as evidence
from src.ai_workflow.graduation_main_budget import read_main_budget
from src.graduation.reference_protocol import encoded


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_bytes(encoded(value))


@pytest.fixture
def unit_review(tmp_path, monkeypatch):
    """Every decision, pytest log, and pilot receipt in this fixture is synthetic."""
    scope = tmp_path / 'synthetic-original-scope'
    shutil.copytree(evidence.ROOT / evidence.SCOPE_ARCHIVE, scope)
    request = read(scope / 'scope_review.json')
    review = tmp_path / 'unit-review'
    review.mkdir()
    approval = {'reviewed_scope_packet': str(scope), 'scope_approved': True,
                'evidence_approved': False, 'conclusion_approved': False,
                'research_status': 'not_achieved',
                'authorization_source': {'kind': 'synthetic_unit_fixture_only'},
                'decision': {'stage': 'scope', 'artifact_hash': request['artifact_hash'],
                             'decision': 'approve', 'reviewer': 'synthetic_test_only',
                             'note': 'Not a human production approval'}}
    write(review / 'scope_approval.json', approval)
    write(review / 'state.json', {'status': 'EVIDENCE_PREPARATION_REQUIRED',
          'scope_review_hash': request['artifact_hash'], 'scope_approved': True,
          'evidence_approved': False, 'conclusion_approved': False,
          'research_status': 'not_achieved', 'solver_calls_executed': 0, 'model_calls': 0})
    sources = {name: 'a' * 64 for name in evidence.SOURCE_PATHS}
    monkeypatch.setattr(evidence, 'backend_source_hashes', lambda: deepcopy(sources))
    test_path = 'tests/test_graduation_main_evidence.py'
    monkeypatch.setattr(evidence, 'REQUIRED_TEST_PATHS', {test_path})
    log = tmp_path / 'synthetic-validation.log'
    log.write_bytes(b'... synthetic unit fixture only ...\n3 passed in 0.10s\n')
    record = {'version': 1, 'status': 'PASSED', 'exit_code': 0, 'passed': 3,
              'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
              'backend_source_hashes': sources,
              'test_hashes': {test_path: evidence._sha(evidence.ROOT / test_path)}}
    pilots = {'run_1': {'synthetic_unit_fixture_only': True},
              'run_2': {'synthetic_unit_fixture_only': True}}
    monkeypatch.setattr(evidence, '_pilot_receipts', lambda check=lambda: None: deepcopy(pilots))
    return {'scope': scope, 'review': review, 'output': tmp_path / 'evidence',
            'log': log, 'record': record, 'sources': sources}


def prepare(unit_review):
    return evidence.prepare_main_evidence(unit_review['review'], unit_review['output'],
                                          unit_review['log'], unit_review['record'])


def approve_evidence_for_unit_test(unit_review):
    request = read(unit_review['output'] / 'evidence_review.json')
    write(unit_review['review'] / 'evidence_approval.json', {
        'decision': {'stage': 'evidence', 'artifact_hash': request['artifact_hash'],
                     'decision': 'approve', 'reviewer': 'synthetic_test_only',
                     'note': 'Synthetic gate test; not real human authorization'}})


def test_real_gate_and_ledger_dispatch_all_mocked_rows_once(unit_review,monkeypatch):
    """Synthetic human decisions; real gate/ledger/finalization, no CP solve."""
    from src.ai_workflow import graduation_main_backend as backend
    from src.graduation import reference_main_worker as worker
    from src.graduation.reference_protocol import digest
    prepare(unit_review)
    approve_evidence_for_unit_test(unit_review)
    monkeypatch.setattr(backend,'backend_source_hashes',lambda:deepcopy(unit_review['sources']))
    dispatches=[]
    def no_schedule(case,mode):
        return {'case_id':case['case_id'],'mode':mode,'input_sha256':digest(case['data']),
            'status':'NO_SCHEDULE','solver_status':'UNKNOWN','metrics':None,'payload':None,
            'error':'GraduationSolverError: CP-SAT returned UNKNOWN; no accepted schedule',
            'solver':{'time_limit':1.0,'num_workers':1,'seed':42}}
    monkeypatch.setattr(worker,'evaluate_row',no_schedule)
    def dispatch(script,payload,timeout):
        context=evidence.execution_context(unit_review['review'],unit_review['output'],allow_running=True)
        assert context['budget_snapshot']['segments'][-1]['finished_seconds'] is None
        dispatches.append(payload)
        return worker.execute_rows(context['cases'],Path(payload['output_dir']),payload['deadline'])
    monkeypatch.setattr(backend,'supervised_json_process',dispatch)
    output=unit_review['review'].parent/'mocked-formal-shaped-output'
    result=backend.run_main(unit_review['review'],unit_review['output'],output)
    assert len(dispatches)==1
    assert result['status']=='COMPLETED' and result['status_counts']['NO_SCHEDULE']==480
    assert result['accepted_runs']==0 and result['planned_calls']==480
    assert backend.recheck_main_run(output,evidence.load_scope_context(unit_review['review'])['cases'])==result
    with pytest.raises(ValueError):
        backend.run_main(unit_review['review'],unit_review['output'],output.parent/'no-second-run')
    assert len(dispatches)==1


def rehash_artifacts(folder):
    manifest = read(folder / 'manifest.json')
    manifest['artifacts'] = {name: evidence._sha(folder / name) for name in sorted(evidence.FILES)}
    write(folder / 'manifest.json', manifest)


def test_backend_source_map_covers_approved_and_execution_sources():
    sources = evidence.backend_source_hashes()
    assert set(sources) == set(evidence.SOURCE_PATHS)
    assert set(evidence.scope._sources()) <= set(sources)
    assert all(len(value) == 64 for value in sources.values())
    assert 'src/ai_workflow/graduation_main_backend.py' in sources
    assert 'src/graduation/reference_main_worker.py' in sources


def test_scope_context_revalidates_the_actual_decision_and_full_denominator(unit_review):
    context = evidence.load_scope_context(unit_review['review'])
    assert context['scope_dir'] == unit_review['scope']
    assert len(context['cases']) == 240 and len(context['planned_rows']) == 480
    assert context['scope_decision']['decision'] == 'approve'
    assert context['scope_hash'] == context['scope_request']['artifact_hash']
    approval = read(unit_review['review'] / 'scope_approval.json')
    approval['decision']['artifact_hash'] = '0' * 64
    write(unit_review['review'] / 'scope_approval.json', approval)
    with pytest.raises(ValueError): evidence.load_scope_context(unit_review['review'])


def test_evidence_preparation_continues_original_budget_without_running_solver(unit_review, monkeypatch):
    import src.graduation.solver as solver
    monkeypatch.setattr(solver, 'solve_parallel_maintenance', lambda *a, **k: pytest.fail('No main solve permitted'))
    before = read_main_budget(unit_review['scope'])
    approval_bytes = (unit_review['review'] / 'scope_approval.json').read_bytes()
    result = prepare(unit_review)
    after = read_main_budget(unit_review['scope'])
    assert result['status'] == 'WAITING_HUMAN_EVIDENCE'
    assert result['research_status'] == 'not_achieved' and result['evidence_approved'] is False
    assert result['solver_calls_executed'] == 0
    assert after['active_seconds'] >= before['active_seconds'] + 5
    assert after['segments'][:2] == before['segments']
    assert len(after['segments']) == 4
    assert not (unit_review['output'] / 'budget.sqlite').exists()
    assert not (unit_review['review'] / 'budget.sqlite').exists()
    assert (unit_review['output'] / 'scope_approval.json').read_bytes() == approval_bytes
    assert read(unit_review['output'] / 'budget_snapshot.json') == after
    request = read(unit_review['output'] / 'evidence_review.json')
    assert request['stage'] == 'evidence' and request['payload']['next_gate'] == 'conclusion'
    assert request['payload']['counts']['planned_solver_calls'] == 480
    assert read(unit_review['review'] / 'state.json')['status'] == 'WAITING_HUMAN_EVIDENCE'
    assert not (unit_review['review'] / 'evidence_approval.json').exists()
    assert '等待evidence人审' in (unit_review['output'] / 'evidence_summary.txt').read_text(encoding='utf-8')


def test_recheck_is_read_only_and_cannot_authorize_execution(unit_review):
    result = prepare(unit_review)
    paths = [*unit_review['scope'].iterdir(), *unit_review['output'].iterdir(), *unit_review['review'].iterdir()]
    before = {str(path): path.read_bytes() for path in paths if path.is_file()}
    checked = evidence.recheck_main_evidence(unit_review['output'])
    assert checked['evidence_hash'] == result['evidence_hash']
    assert checked['current_sources_checked'] is True
    with pytest.raises((ValueError, OSError)):
        evidence.execution_context(unit_review['review'], unit_review['output'])
    assert before == {str(path): path.read_bytes() for path in paths if path.is_file()}


@pytest.mark.parametrize('fault', ['count', 'log', 'exit', 'status', 'source', 'test', 'missing_test'])
def test_invalid_development_receipt_never_leaves_a_ready_packet(unit_review, fault):
    record = unit_review['record']
    if fault == 'count': record['passed'] += 1
    elif fault == 'log': unit_review['log'].write_bytes(b'3 failed in 0.10s\n')
    elif fault == 'exit': record['exit_code'] = 1
    elif fault == 'status': record['status'] = 'FAILED'
    elif fault == 'source': record['backend_source_hashes'] = {}
    elif fault == 'test': record['test_hashes']['tests/test_graduation_main_evidence.py'] = '0' * 64
    else: record['test_hashes'] = {}
    with pytest.raises(ValueError): prepare(unit_review)
    assert read(unit_review['review'] / 'state.json')['status'] == 'STOPPED_EVIDENCE_PREPARATION_FAILED'
    assert not (unit_review['output'] / 'evidence_review.json').exists()


@pytest.mark.parametrize('fault', ['scope_hash', 'reject', 'input'])
def test_scope_or_input_tampering_cannot_inherit_authorization(unit_review, fault):
    if fault == 'input':
        inputs = read(unit_review['scope'] / 'inputs.json')
        inputs[0]['data']['tasks'][0]['processing_time'] += 1
        write(unit_review['scope'] / 'inputs.json', inputs)
    else:
        approval = read(unit_review['review'] / 'scope_approval.json')
        approval['decision']['artifact_hash' if fault == 'scope_hash' else 'decision'] = '0' * 64 if fault == 'scope_hash' else 'reject'
        write(unit_review['review'] / 'scope_approval.json', approval)
    with pytest.raises(ValueError): prepare(unit_review)
    assert not unit_review['output'].exists()


def test_existing_output_is_never_overwritten(unit_review):
    unit_review['output'].mkdir()
    (unit_review['output'] / 'keep.txt').write_text('unit sentinel')
    with pytest.raises(FileExistsError): prepare(unit_review)
    assert (unit_review['output'] / 'keep.txt').read_text() == 'unit sentinel'


@pytest.mark.parametrize('fault', ['summary', 'pilot', 'remaining', 'scope_approval', 'request', 'extra'])
def test_rehashed_receipts_cannot_replace_reconstruction(unit_review, fault):
    prepare(unit_review)
    folder = unit_review['output']
    if fault == 'extra': (folder / 'extra.txt').write_text('unexpected')
    else:
        name = {'summary': 'summary.json', 'pilot': 'pilot_receipts.json', 'remaining': 'budget_snapshot.json',
                'scope_approval': 'scope_approval.json', 'request': 'evidence_review.json'}[fault]
        value = read(folder / name)
        if fault == 'summary': value['solver_calls_executed'] = 480
        elif fault == 'pilot': value['run_1'] = {}
        elif fault == 'remaining': value['remaining_active_seconds'] += 1
        elif fault == 'scope_approval': value['decision']['decision'] = 'reject'
        else: value['payload']['next_gate'] = 'execution_without_review'
        write(folder / name, value)
        rehash_artifacts(folder)
    with pytest.raises(ValueError): evidence.recheck_main_evidence(folder)


def test_stale_backend_sources_reject_by_default_and_portable_check_is_explicit(unit_review, monkeypatch):
    prepare(unit_review)
    changed = deepcopy(unit_review['sources'])
    changed[next(iter(changed))] = 'b' * 64
    monkeypatch.setattr(evidence, 'backend_source_hashes', lambda: changed)
    with pytest.raises(ValueError): evidence.recheck_main_evidence(unit_review['output'])
    assert evidence.recheck_main_evidence(unit_review['output'], require_current_sources=False)['current_sources_checked'] is False


def test_portable_recheck_locates_archive_by_full_scope_hash_without_a_new_budget(unit_review):
    prepare(unit_review)
    shutil.rmtree(unit_review['scope'])
    result = evidence.recheck_main_evidence(unit_review['output'])
    assert result['status'] == 'WAITING_HUMAN_EVIDENCE'
    with pytest.raises(ValueError):
        evidence.load_scope_context(unit_review['review'])
    assert not unit_review['scope'].exists()


def test_windows_origin_reference_can_be_rechecked_from_a_clone(unit_review):
    prepare(unit_review)
    folder = unit_review['output']
    approval = read(folder / 'scope_approval.json')
    approval['reviewed_scope_packet'] = r'Z:\missing-original-host\scope-packet'
    write(folder / 'scope_approval.json', approval)
    reference = read(folder / 'scope_reference.json')
    reference['original_scope_dir'] = 'Z:/missing-original-host/scope-packet'
    write(folder / 'scope_reference.json', reference)
    context = evidence._approved_scope(evidence.ROOT / evidence.SCOPE_ARCHIVE, approval)
    request = evidence._request(folder, context, read(folder / 'backend_sources.json'),
                                read(folder / 'budget_snapshot.json'))
    write(folder / 'evidence_review.json', request)
    manifest = read(folder / 'manifest.json')
    manifest['review_hash'] = request['artifact_hash']
    write(folder / 'manifest.json', manifest)
    rehash_artifacts(folder)
    assert evidence.recheck_main_evidence(folder)['evidence_hash'] == request['artifact_hash']


def test_approved_gate_is_read_only_and_running_gate_is_explicit(unit_review):
    prepare(unit_review)
    approve_evidence_for_unit_test(unit_review)
    context = evidence.execution_context(unit_review['review'], unit_review['output'])
    assert context['scope_dir'] == unit_review['scope']
    assert context['evidence_dir'] == unit_review['output']
    assert context['evidence_decision']['decision'] == 'approve'
    state = read(unit_review['review'] / 'state.json')
    state['status'] = 'RUNNING'
    write(unit_review['review'] / 'state.json', state)
    with pytest.raises(ValueError): evidence.execution_context(unit_review['review'], unit_review['output'])
    with pytest.raises(ValueError):
        evidence.execution_context(unit_review['review'],unit_review['output'],allow_running=True)
    from src.ai_workflow.graduation_main_budget import run_main_phase
    def work(handle):
        return evidence.execution_context(unit_review['review'],unit_review['output'],allow_running=True)['scope_hash']
    assert run_main_phase(unit_review['scope'],unit_review['review'],work,
                          lambda value,snapshot,check:value)==context['scope_hash']


def test_settled_attempt_cannot_reuse_same_evidence(unit_review):
    prepare(unit_review)
    approve_evidence_for_unit_test(unit_review)
    from src.ai_workflow.graduation_main_budget import run_main_phase
    def failed(handle):raise ValueError('Synthetic attempt failed before output initialization')
    with pytest.raises(ValueError):
        run_main_phase(unit_review['scope'],unit_review['review'],failed,lambda *a:None)
    with pytest.raises(ValueError):
        evidence.execution_context(unit_review['review'],unit_review['output'])


def test_stale_evidence_decision_fails_before_any_execution(unit_review):
    prepare(unit_review)
    approve_evidence_for_unit_test(unit_review)
    decision = read(unit_review['review'] / 'evidence_approval.json')
    decision['decision']['artifact_hash'] = '0' * 64
    write(unit_review['review'] / 'evidence_approval.json', decision)
    with pytest.raises(ValueError): evidence.execution_context(unit_review['review'], unit_review['output'])


def test_finalization_failure_retracts_ready_state_and_manifest(unit_review, monkeypatch):
    original = evidence._control_state
    def fail_after_publish(review, status, **fields):
        original(review, status, **fields)
        if status == 'WAITING_HUMAN_EVIDENCE': raise RuntimeError('synthetic final I/O failure')
    monkeypatch.setattr(evidence, '_control_state', fail_after_publish)
    with pytest.raises(RuntimeError): prepare(unit_review)
    assert read(unit_review['review'] / 'state.json')['status'] == 'STOPPED_EVIDENCE_PREPARATION_FAILED'
    assert read(unit_review['output'] / 'manifest.json')['status'] == 'STOPPED_EVIDENCE_PREPARATION_FAILED'
    with pytest.raises(ValueError): evidence.recheck_main_evidence(unit_review['output'])


def test_real_archived_pilot_recheck_runs_no_cp_sat(monkeypatch):
    import src.graduation.reference_pilot as pilot
    monkeypatch.setattr(pilot, 'solve_parallel_maintenance', lambda *a, **k: pytest.fail('Recheck must not solve CP-SAT'))
    receipts = evidence._pilot_receipts()
    assert set(receipts) == {'run_1', 'run_2'}
    assert all(row['summary']['validated_runs'] == 24 for row in receipts.values())


def test_execution_runtime_must_match_the_approved_evidence(unit_review,monkeypatch):
    prepare(unit_review)
    approve_evidence_for_unit_test(unit_review)
    original=evidence.runtime_identity()
    monkeypatch.setattr(evidence,'runtime_identity',lambda:{**original,'ortools':'changed-runtime'})
    assert evidence.recheck_main_evidence(unit_review['output'])['status']=='WAITING_HUMAN_EVIDENCE'
    with pytest.raises(ValueError,match='runtime'):
        evidence.execution_context(unit_review['review'],unit_review['output'])
