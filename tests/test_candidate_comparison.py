"""Bounded candidate comparisons retain only complete checked validation evidence."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'experiments/results/exp_026_validation_iteration_phase1_v2'


def _rows(candidate=9, control=10):
    return [dict(method=method, mode=mode, seed=seed, validation_index=index,
                 validation_status='PASS', schedule_accepted=True,
                 payload={'total_tardiness': candidate if method == 'shared_scorer_v1' else control})
            for mode in ('fixed', 'joint') for seed in (17, 29) for index in range(4)
            for method in ('shared_scorer_v1', 'none')]


@pytest.mark.parametrize('candidate,expected', [(9, 'shared_scorer_v1'), (10, 'none'), (11, 'none')])
def test_selection_requires_strict_pooled_improvement(candidate, expected):
    from src.ai_workflow.candidate_comparison import _decisions
    decisions = _decisions(_rows(candidate), complete=True)
    assert all(value['status'] == 'DECIDED' and value['selected_method'] == expected
               for value in decisions.values())


@pytest.mark.parametrize('damage', ['incomplete', 'duplicate', 'rejected', 'nan', 'bool', 'missing'])
def test_no_retention_if_any_denominator_or_checked_row_is_invalid(damage):
    from src.ai_workflow.candidate_comparison import _decisions
    rows = _rows()
    if damage == 'duplicate':
        rows[-1] = deepcopy(rows[-2])
    elif damage == 'rejected':
        rows[-1]['schedule_accepted'] = False
    elif damage == 'nan':
        rows[-1]['payload']['total_tardiness'] = float('nan')
    elif damage == 'bool':
        rows[-1]['payload']['total_tardiness'] = True
    elif damage == 'missing':
        rows.pop()
    assert all(value['status'] == 'STOP' and value['selected_method'] is None
               for value in _decisions(rows, complete=damage != 'incomplete').values())


def test_controller_counts_have_the_exact_declared_schema():
    from src.ai_workflow.candidate_comparison import EXPECTED_COUNTS, _report_counts
    assert _report_counts(EXPECTED_COUNTS) == {'training_runs': 4, 'training_steps': 1536,
        'candidate_validation_plans': 16, 'control_validation_plans': 16,
        'rule_reference_plans': 48, 'cp_reference_plans': 8, 'equivariance_states': 384}


def test_frozen_training_split_is_exact_and_disjoint_without_decoding_probe(monkeypatch):
    from src.ai_workflow import candidate_comparison as module
    original = module._decode

    def guarded(raw):
        assert 'NEVER_DECODE_PROBE' not in raw
        return original(raw)

    monkeypatch.setattr(module, '_decode', guarded)
    raw = (NATIVE / 'results.json').read_text(encoding='utf-8-sig')
    parsed = json.loads(raw)
    parsed['splits']['probe'] = {'NEVER_DECODE_PROBE': True}
    training, identities = module._training_split(json.dumps(parsed),
        [row['base_instance_identity'] for row in parsed['splits']['validation']], lambda: None)
    assert len(training) == len(set(identities)) == 8
    parsed['splits']['training'][0] = deepcopy(parsed['splits']['validation'][0])
    with pytest.raises(ValueError, match='disjoint'):
        module._training_split(json.dumps(parsed),
            [row['base_instance_identity'] for row in parsed['splits']['validation']], lambda: None)


def _batch_actor(batch):
    target = batch / 'candidate/policy.py'
    target.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / 'src/graduation/candidate_templates/shared_scorer.py', target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (target.parent / 'manifest.json').write_text(json.dumps({'version': 1,
        'profile': 'shared_scorer_v1', 'template_sha256': digest,
        'files_sha256': {'policy.py': digest}, 'protected_source_hashes': {}}))
    name = '_test_candidate_' + hashlib.sha256(str(batch).encode()).hexdigest()
    spec = importlib.util.spec_from_file_location(name, target)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.SharedScorer


def test_native_bounded_comparison_has_complete_replay_training_and_artifact_counts(tmp_path):
    from src.ai_workflow.candidate_comparison import run_comparison
    batch = tmp_path / 'batch'
    actor = _batch_actor(batch)
    before = {p: p.stat().st_mtime_ns for p in NATIVE.rglob('*') if p.is_file()}
    report = run_comparison(batch, NATIVE, actor)
    assert report['status'] == 'COMPLETED' and report['kind'] == 'controlled_candidate_comparison'
    assert report['research_status'] == 'not_achieved'
    assert report['network_calls'] == report['model_api_calls'] == 0
    assert report['probe_evaluated'] is report['final_test_evaluated'] is False
    assert report['production_default_changed'] is False
    counts = report['counts']
    assert counts['training_runs'] == 4 and report['denominators']['training_episodes'] == 256
    assert counts['training_steps'] == 1536
    assert counts['candidate_validation_plans'] == counts['control_validation_plans'] == 16
    assert counts['rule_reference_plans'] == 48 and counts['cp_reference_plans'] == 8
    assert counts['equivariance_states'] == 384
    assert report['all_checks_passed'] is True
    assert all(row['hash_matches'] for row in report['control_rows'])
    assert report['reference_reuse']['fresh_control_training'] is False
    assert report['reference_reuse']['fresh_cp_solves'] is False
    assert all(len(run['logs']) == 64 and len(run['validation_history']) == 5
               and run['training_steps'] == 384 for run in report['training_runs'])
    for run in report['training_runs']:
        assert run['checkpoints']['initial']['path'].endswith('/initial.npz')
        history = run['validation_history']
        best = min(history, key=lambda row: row['validation_mean_tardiness'])
        assert run['selected_episode'] == best['episode']
        assert len(run['interval_checkpoints']) == 5
        events = [json.loads(line) for line in (batch / run['progress_log']).read_text().splitlines()]
        assert sum(row['kind'] == 'episode' for row in events) == 64
        assert sum(row['kind'] == 'validation' for row in events) == 5
    for relative, digest in report['artifacts'].items():
        assert relative.startswith('candidate_run/')
        assert hashlib.sha256((batch / relative).read_bytes()).hexdigest() == digest
    assert {p: p.stat().st_mtime_ns for p in before} == before
    with pytest.raises(FileExistsError):
        run_comparison(batch, NATIVE, actor)


def test_tampered_reference_fails_and_preserves_owned_run_directory(tmp_path):
    from src.ai_workflow.candidate_comparison import run_comparison
    archive = tmp_path / 'archive'
    shutil.copytree(NATIVE, archive)
    with (archive / 'results.json').open('ab') as handle:
        handle.write(b' ')
    batch = tmp_path / 'batch'
    with pytest.raises(ValueError, match='hash mismatch'):
        run_comparison(batch, archive, _batch_actor(batch))
    assert (batch / 'candidate_run').is_dir()


def test_deadline_keeps_partial_progress_without_accepting_comparison(tmp_path):
    from src.ai_workflow.candidate_comparison import run_comparison
    batch = tmp_path / 'batch'

    def budget():
        logs = list((batch / 'candidate_run/logs').glob('*.jsonl'))
        if logs and '"kind":"episode"' in logs[0].read_text():
            raise TimeoutError('test cap')

    with pytest.raises(TimeoutError, match='test cap'):
        run_comparison(batch, NATIVE, _batch_actor(batch), check_budget=budget)
    assert list((batch / 'candidate_run/checkpoints').rglob('*.npz'))
    assert list((batch / 'candidate_run/logs').glob('*.jsonl'))
    assert not (batch / 'candidate_run/manifest.json').exists()


@pytest.mark.parametrize('damage', ['hash', 'denominator', 'malformed'])
def test_training_split_rejects_bad_input_before_training(damage):
    from src.ai_workflow.candidate_comparison import _training_split
    parsed = json.loads((NATIVE / 'results.json').read_text())
    if damage == 'hash':
        parsed['splits']['training'][0]['input_sha256'] = '0'*64
    elif damage == 'denominator':
        parsed['splits']['training'].pop()
    else:
        parsed['splits']['training'] = {'not': 'a split'}
    with pytest.raises(ValueError):
        _training_split(json.dumps(parsed), [], lambda: None)


def _alter_reference(tmp_path, alter):
    archive = tmp_path / 'archive'
    shutil.copytree(NATIVE, archive)
    results = json.loads((archive / 'results.json').read_text())
    alter(results)
    raw = json.dumps(results, separators=(',', ':')).encode()
    (archive / 'results.json').write_bytes(raw)
    manifest = json.loads((archive / 'manifest.json').read_text())
    manifest['artifacts']['results.json'] = hashlib.sha256(raw).hexdigest()
    (archive / 'manifest.json').write_text(json.dumps(manifest))
    return archive


@pytest.mark.parametrize('damage', ['rule_action', 'cp_objective', 'cp_gap', 'control_budget', 'training_data'])
def test_rehashed_malformed_reference_is_rejected(tmp_path, damage):
    from src.ai_workflow.candidate_comparison import run_comparison

    def alter(results):
        if damage == 'rule_action':
            next(row for row in results['validation_rows'] if row['method'] == 'EDD')['actions'][0] = 99
        elif damage == 'cp_objective':
            row = results['cp_rows'][0]
            row['solver_objective_value'] = row['payload']['solver_objective_value'] = 999
        elif damage == 'cp_gap':
            row = results['cp_rows'][0]
            row['solver_gap'] = row['payload']['solver_gap'] = 999
        elif damage == 'control_budget':
            next(row for row in results['training_runs'] if row['method'] == 'none')['episodes_completed'] = 63
        else:
            row = results['splits']['training'][0]
            row['input']['maintenance'][0]['window_end'] += 1
            row['input_sha256'] = hashlib.sha256(json.dumps(row['input'], sort_keys=True,
                ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()).hexdigest()

    archive = _alter_reference(tmp_path, alter)
    batch = tmp_path / 'batch'
    with pytest.raises(ValueError):
        run_comparison(batch, archive, _batch_actor(batch))
    assert not list((batch / 'candidate_run').rglob('*.npz'))


def test_original_checker_rejection_propagates_without_retention(tmp_path, monkeypatch):
    from src.ai_workflow import candidate_comparison as module
    monkeypatch.setattr(module, 'check_parallel_maintenance_feasibility', lambda *args, **kwargs: (False, []))
    batch = tmp_path / 'batch'
    with pytest.raises(ValueError, match='Original G1'):
        module.run_comparison(batch, NATIVE, _batch_actor(batch))
    assert not (batch / 'candidate_run/results.json').exists()


def test_incomplete_training_cannot_retain_a_candidate(tmp_path, monkeypatch):
    from src.ai_workflow import candidate_comparison as module
    monkeypatch.setattr(module, 'train_shared_policy', lambda *args, **kwargs:
                        {'episodes_completed': 63, 'training_steps': 378})
    batch = tmp_path / 'batch'
    with pytest.raises(ValueError, match='Incomplete candidate training'):
        module.run_comparison(batch, NATIVE, _batch_actor(batch))
    assert not (batch / 'candidate_run/results.json').exists()


@pytest.mark.parametrize('damage', ['wrong_class_source', 'tampered_source'])
def test_candidate_requires_exact_materialized_template(tmp_path, damage):
    from src.ai_workflow.candidate_comparison import run_comparison
    from src.graduation.candidate_templates.shared_scorer import SharedScorer
    batch = tmp_path / 'batch'
    actor = _batch_actor(batch)
    if damage == 'wrong_class_source':
        actor = SharedScorer
    else:
        with (batch / 'candidate/policy.py').open('ab') as handle:
            handle.write(b'\n# changed\n')
    with pytest.raises(ValueError, match='template|materialized'):
        run_comparison(batch, NATIVE, actor)
