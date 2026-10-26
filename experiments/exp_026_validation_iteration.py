"""One bounded return-baseline comparison using frozen validation data only."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import time


NUMPY_PREIMPORTED = 'numpy' in sys.modules
THREAD_VARIABLES = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                    'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'BLIS_NUM_THREADS')
for _variable in THREAD_VARIABLES:
    os.environ[_variable] = '1'

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import exp_025_neural_policy_pilot as pilot
from src.graduation.validation_diagnostics import diagnose_validation, _raw_fields, _decode, _path_inside, _instances


DEFAULT_REFERENCE = ROOT / 'experiments/results/exp_025_neural_policy_v1'
PLAN_FILE = 'docs/superpowers/plans/2026-10-26-validation-baseline-iteration.md'
PURPOSE = 'validation_only_return_baseline_iteration'
LIMITATION = ('Development selection on reused validation data; no independent performance proof, '
              'guaranteed improvement, production default change or scientific approval. '
              'Paper reproduction and graduation research acceptance remain incomplete.')
METHODS = ('none', 'running_mean')
RULES = ('EDD', 'SPT', 'Random')
MODES = ('fixed', 'joint')
TRAINING_SEEDS = (17, 29)
CERTIFICATE_FIELDS = pilot.CERTIFICATE_FIELDS
SOURCE_FILES = pilot.SOURCE_FILES + ('src/graduation/return_baseline.py',
    'src/graduation/validation_diagnostics.py', 'experiments/exp_026_validation_iteration.py')

# These helpers retain the original safety checks and never choose a data split.
_encoded, _sha, _safe = pilot._encoded, pilot._sha, pilot._safe
_write_json, _state_hash = pilot._write_json, pilot._state_hash
_save_checkpoint, load_checkpoint = pilot._save_checkpoint, pilot.load_checkpoint
_plan_payload, _plan_hash, _checked_episode = pilot._plan_payload, pilot._plan_hash, pilot._checked_episode
run_maintenance_rule_episode = pilot.run_maintenance_rule_episode
solve_parallel_maintenance = pilot.solve_parallel_maintenance


class IterationBudgetExceeded(TimeoutError):
    """The one shared active-time cap expired; persisted progress is retained."""


def build_splits(reference=None, *, check_budget=None):
    """Restore only verified archived training8/validation4, without generating inputs."""
    budget = check_budget if check_budget is not None else lambda: None
    reference = reference if reference is not None else _read_reference(DEFAULT_REFERENCE, budget)
    metadata = {key: reference['splits'][key] for key in
                ('version', 'generator', 'work_definition', 'training', 'validation')}
    training, train_ids = _instances(metadata['training'], 8, budget)
    validation, valid_ids = _instances(metadata['validation'], 4, budget)
    if len(training) != 8 or len(validation) != 4 or set(train_ids) & set(valid_ids):
        raise ValueError('Frozen training8/validation4 must have disjoint base identities')
    return {'training': tuple(training), 'validation': tuple(validation), 'metadata': metadata}


def _read_reference(archive_dir, check_budget):
    """Read whitelisted archive fields without decoding any probe examples."""
    archive = Path(archive_dir).resolve()
    check_budget()
    manifest_path = _path_inside(archive, 'manifest.json')
    manifest = {key: _decode(value) for key, value in _raw_fields(manifest_path.read_text(encoding='utf-8-sig'),
                {'artifacts', 'source_hashes', 'data_sha256', 'config_sha256'}, check_budget).items()}
    result_path = _path_inside(archive, 'results.json')
    raw_result = result_path.read_bytes()
    if _sha(raw_result) != manifest['artifacts'].get('results.json'):
        raise ValueError('Reference results hash mismatch')
    raw = _raw_fields(raw_result.decode('utf-8-sig'), {'training_runs', 'splits', 'config'}, check_budget)
    split_fields = _raw_fields(raw['splits'],
        {'version', 'generator', 'work_definition', 'training', 'validation'}, check_budget)
    runs = _decode(raw['training_runs'])
    expected = {(mode, seed) for mode in MODES for seed in TRAINING_SEEDS}
    if (type(runs) is not list or len(runs) != 4 or
            {(run['mode'], run['seed']) for run in runs} != expected or
            any(run['status'] != 'COMPLETED' for run in runs)):
        raise ValueError('Reference must contain all four completed frozen controls')
    config = _decode(raw['config'])
    if _sha(_encoded(config)) != manifest['config_sha256']:
        raise ValueError('Reference config hash mismatch')
    check_budget()
    return {'archive': archive, 'manifest': manifest, 'runs': runs,
            'splits': {key: _decode(value) for key, value in split_fields.items()}, 'config': config,
            'manifest_sha256': _sha(manifest_path.read_bytes()), 'results_sha256': _sha(raw_result)}


def _control_check(run, reference, *, episodes, check_budget):
    """Compare parameter states, including selected/final at the native budget."""
    old = next(item for item in reference['runs'] if
               (item['mode'], item['seed']) == (run['mode'], run['seed']))
    control = run['method'] == 'none'
    native = control and episodes == reference['config']['episodes'] == 64
    report = {'status': ('PASS' if native else 'SKIPPED_DIFFERENT_BUDGET') if control else 'NOT_CONTROL',
              'initial_match': False,
              'selected_match': None, 'final_match': None, 'reference_episodes': reference['config']['episodes']}
    for name in ('initial', 'selected', 'final') if native else ('initial',):
        check_budget()
        saved = old['checkpoints'][name]
        path = _path_inside(reference['archive'], saved['path'])
        if reference['manifest']['artifacts'].get(saved['path']) != saved['sha256']:
            raise ValueError('Archived control checkpoint binding mismatch')
        state = load_checkpoint(path, expected_sha256=saved['sha256']).state_dict()
        expected = _state_hash(state)
        report[name + '_match'] = saved['state_sha256'] == expected == run['checkpoints'][name]['state_sha256']
        if not report[name + '_match']:
            raise ValueError('Frozen control ' + name + ' parameter state mismatch')
    if native and run['selected_episode'] != old['selected_episode']:
        raise ValueError('Frozen control selected episode mismatch')
    check_budget()
    return report


def _decisions(rows, *, complete):
    """Strict pooled validation improvement only; any missing denominator stops both modes."""
    expected = {(mode, seed, index, method) for mode in MODES for seed in TRAINING_SEEDS
                for index in range(4) for method in METHODS}
    policy = [row for row in rows if row['method'] in METHODS]
    keys = [(row['mode'], row['seed'], row['validation_index'], row['method']) for row in policy]
    valid = (complete and len(policy) == 32 and len(set(keys)) == 32 and set(keys) == expected and
             all(row['validation_status'] == 'PASS' and row['schedule_accepted'] and
                 row['payload'] is not None and type(row['payload']['total_tardiness']) in (int, float) and
                 math.isfinite(row['payload']['total_tardiness']) and row['payload']['total_tardiness'] >= 0
                 for row in policy))
    decisions = {mode: {'status': 'STOP', 'selected_method': None, 'mean_validation_tardiness': None,
                        'per_seed': [], 'development_selection': True} for mode in MODES}
    if not valid:
        return decisions
    for mode in MODES:
        means = {method: math.fsum(row['payload']['total_tardiness'] for row in policy
                                  if row['mode'] == mode and row['method'] == method) / 8 for method in METHODS}
        per_seed = [{'seed': seed, 'mean_validation_tardiness': {
            method: math.fsum(row['payload']['total_tardiness'] for row in policy
                if (row['mode'], row['seed'], row['method']) == (mode, seed, method)) / 4
            for method in METHODS}} for seed in TRAINING_SEEDS]
        decisions[mode].update(status='DECIDED', selected_method=(
            'running_mean' if means['running_mean'] < means['none'] else 'none'),
            mean_validation_tardiness=means, per_seed=per_seed)
    return decisions


def _digest_outcome(evidence):
    """Exclude runtime, paths, archive packaging and solver wall time."""
    runs = []
    for run in evidence['training_runs']:
        stable = {key: value for key, value in run.items() if key not in (
            'progress_log', 'progress_log_sha256', 'checkpoints', 'interval_checkpoints')}
        stable['checkpoint_states'] = {key: item['state_sha256'] for key, item in run['checkpoints'].items()}
        runs.append(stable)
    cp_rows = []
    for row in evidence['cp_rows']:
        stable = {key: value for key, value in row.items() if key != 'solver_wall_time'}
        if stable['payload'] is not None:
            stable['payload'] = {key: value for key, value in stable['payload'].items() if key != 'solver_wall_time'}
        cp_rows.append(stable)
    return _sha(_encoded(_safe({'config': evidence['config'], 'splits': evidence['splits'],
        'diagnosis_sha256': evidence['diagnosis_sha256'], 'training_runs': runs,
        'validation_rows': evidence['validation_rows'], 'cp_rows': cp_rows,
        'decisions': evidence['decisions'], 'error_type': evidence['error_type']})))


def run_experiment(output_dir: Path, *, episodes=64, max_active_seconds=120, reference_archive=None):
    """Diagnose the archive, run one paired comparison and retain every denominator."""
    if type(episodes) is not int or not 1 <= episodes <= 64:
        raise ValueError('episodes must be an integer in 1..64')
    if (type(max_active_seconds) not in (int, float) or not math.isfinite(max_active_seconds)
            or not 0 < max_active_seconds <= 120):
        raise ValueError('max_active_seconds must be finite, positive and <=120')
    output = Path(output_dir)
    reference_archive = Path(reference_archive or DEFAULT_REFERENCE).resolve()
    if output.resolve().is_relative_to(reference_archive):
        raise ValueError('Output must be outside the read-only reference archive')
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()

    def check_budget():
        if time.monotonic() - started >= max_active_seconds:
            raise IterationBudgetExceeded('Shared validation iteration active-time cap expired')

    config = {'version': 1, 'episodes': episodes, 'validation_every': min(16, episodes),
        'training_methods': METHODS, 'rule_methods': RULES, 'modes': MODES, 'training_seeds': TRAINING_SEEDS,
        'hidden_size': 16, 'learning_rate': .01, 'algorithm': 'REINFORCE', 'input_features': 372,
        'output_actions': 100, 'activation': 'tanh', 'parameter_count': 7668, 'gamma': 1,
        'max_gradient_norm': 1., 'max_active_seconds': max_active_seconds, 'max_training_steps': 3072,
        'planned_training_steps': 8 * episodes * 6, 'cp_time_limit': 1., 'cp_num_workers': 1, 'cp_seed': 42,
        'selection': 'minimum_greedy_validation_mean_tardiness_earliest_tie',
        'candidate_selection': 'strictly_lower_pooled_validation_mean_else_none',
        'hyperparameter_search': False, 'network_calls': 0, 'model_api_calls': 0,
        'exact_resume_supported': False, 'production_default_changed': False}
    runs = [{'method': method, 'mode': mode, 'seed': seed, 'status': 'NOT_RUN',
        'episodes_completed': 0, 'training_steps': 0, 'selected_episode': None,
        'logs': [], 'validation_history': [], 'checkpoints': {}, 'interval_checkpoints': [],
        'control_check': {'status': 'NOT_CHECKED' if method == 'none' else 'NOT_CONTROL'},
        'error_type': None, 'progress_log': f'logs/{method}-{mode}-seed{seed}.jsonl',
        'progress_log_sha256': None} for method in METHODS for mode in MODES for seed in TRAINING_SEEDS]
    rows = [{'method': method, 'mode': mode, 'seed': seed, 'validation_index': index,
        'instance_identity': None, 'validation_status': 'NOT_RUN', 'schedule_accepted': False,
        'actions': None, 'transitions': [], 'payload': None, 'plan_sha256': None, 'error_type': None,
        'check': {'accepted': False, 'issues': []}, 'replay_check': {'accepted': False, 'issues': []},
        'cp_comparison': None} for mode in MODES for seed in TRAINING_SEEDS for index in range(4)
        for method in (*METHODS, *RULES)]
    cp_rows = [{'mode': mode, 'validation_index': index, 'instance_identity': None,
        'validation_status': 'NOT_RUN', 'schedule_accepted': False, 'optimum_certified': False,
        'check': {'accepted': False, 'issues': []}, 'payload': None, 'plan_sha256': None,
        'error_type': None, **{field: None for field in CERTIFICATE_FIELDS}}
        for mode in MODES for index in range(4)]
    evidence = {'version': 1, 'purpose': PURPOSE, 'limitation': LIMITATION,
        'research_status': 'not_achieved', 'probe_evaluated': False, 'final_test_evaluated': False,
        'config': config, 'splits': {}, 'training_runs': runs, 'validation_rows': rows, 'cp_rows': cp_rows,
        'diagnosis_status': 'NOT_RUN', 'diagnosis_sha256': None, 'reference': None,
        'decisions': _decisions(rows, complete=False), 'error_type': None}
    source_hashes, data_hash, diagnosis_hash = {}, None, None
    config_hash = _sha(_encoded(config))
    plan_hash = None
    (output / 'logs').mkdir()

    def persist():
        _write_json(output / 'results.json', evidence)

    persist()
    timed_out = False
    try:
        check_budget()
        # Read-only diagnosis is a required gate, before data use or any update.
        diagnosis = diagnose_validation(Path(reference_archive or DEFAULT_REFERENCE), check_budget=check_budget)
        if (diagnosis.get('version') != 1 or diagnosis.get('kind') != 'validation_only_policy_diagnosis'
                or diagnosis.get('probe_evaluated') is not False or diagnosis.get('cp_evaluated') is not False
                or diagnosis['hash_checks'].get('all_archived_artifacts_match') is not True
                or diagnosis['hash_checks'].get('all_current_original_sources_match') is not True):
            raise ValueError('Required validation-only diagnosis did not pass')
        _write_json(output / 'diagnosis.json', diagnosis)
        diagnosis_hash = _sha((output / 'diagnosis.json').read_bytes())
        evidence.update(diagnosis_status='PASS', diagnosis_sha256=diagnosis_hash)
        check_budget()
        reference = _read_reference(reference_archive or DEFAULT_REFERENCE, check_budget)
        splits = build_splits(reference, check_budget=check_budget)
        if (len(splits['training']) != 8 or len(splits['validation']) != 4 or any(
                _encoded(splits['metadata'][name]) != _encoded(reference['splits'][name])
                for name in ('training', 'validation'))):
            raise ValueError('Training/validation data differ from the frozen pilot')
        evidence['splits'] = splits['metadata']
        evidence['reference'] = {key: reference[key] for key in ('manifest_sha256', 'results_sha256')}
        data_hash = _sha(_encoded(splits['metadata']))
        source_hashes = {name: _sha((ROOT / name).read_bytes()) for name in SOURCE_FILES}
        plan_hash = _sha((ROOT / PLAN_FILE).read_bytes())
        for row in (*rows, *cp_rows):
            row['instance_identity'] = pilot._identity(splits['validation'][row['validation_index']])
        persist()
        check_budget()
        from src.graduation.policy_training import run_policy_episode, train_policy

        for run in runs:
            check_budget()
            mode, seed, method = run['mode'], run['seed'], run['method']
            run['status'] = 'RUNNING'
            prefix = f'checkpoints/{method}-{mode}-seed{seed}'

            def save(name, state, episode):
                return _save_checkpoint(output, f'{prefix}/{name}.npz', state, episode=episode,
                    source_hashes=source_hashes, data_hash=data_hash, config_hash=config_hash)

            def progress(event):
                # Archive just-completed work before a boundary budget check.
                if event['kind'] == 'episode':
                    run['logs'].append(_safe(event['log']))
                    run['episodes_completed'], run['training_steps'] = event['episode'], event['training_steps']
                    archived = _safe(event)
                elif event['kind'] == 'validation':
                    episode = event['episode']
                    current = save(f'current-episode-{episode:03d}', event['current_state'], episode)
                    selected = save(f'selected-episode-{episode:03d}', event['selected_state'], event['selected_episode'])
                    interval = {'episode': episode, 'current': current, 'selected': selected}
                    if 'baseline_state' in event:
                        interval['baseline_state'] = _safe(event['baseline_state'])
                    if method == 'running_mean' and 'baseline_state' not in event:
                        raise ValueError('Candidate validation must retain its baseline state')
                    run['interval_checkpoints'].append(interval)
                    if episode == 0:
                        run['checkpoints']['initial'] = save('initial', event['current_state'], 0)
                    run['checkpoints']['current'] = current
                    run['checkpoints']['selected'] = save('selected', event['selected_state'], event['selected_episode'])
                    run['selected_episode'] = event['selected_episode']
                    archived = {key: _safe(value) for key, value in event.items()
                                if key not in ('current_state', 'selected_state')}
                    run['validation_history'].append(archived)
                    archived = dict(archived, current_checkpoint=current, selected_checkpoint=selected)
                else:
                    raise ValueError('Unknown training progress event')
                log_path = output / run['progress_log']
                with log_path.open('ab') as handle:
                    handle.write(_encoded(archived) + b'\n')
                run['progress_log_sha256'] = _sha(log_path.read_bytes())
                persist()
                check_budget()

            try:
                result = train_policy(splits['training'], splits['validation'], mode=mode, seed=seed,
                    episodes=episodes, validation_every=config['validation_every'], learning_rate=.01,
                    hidden_size=16, check_budget=check_budget, on_progress=progress, return_baseline=method)
                for name in ('initial', 'final', 'selected'):
                    episode = 0 if name == 'initial' else (result['selected_episode'] if name == 'selected'
                                                          else result['episodes_completed'])
                    run['checkpoints'][name] = save(name, result[name + '_state'], episode)
                if (result['episodes_completed'] != episodes or result['training_steps'] != episodes * 6
                        or _safe(result['logs']) != run['logs'] or len(run['logs']) != episodes):
                    raise ValueError('Training completion differs from durable progress evidence')
                run.update(episodes_completed=result['episodes_completed'], training_steps=result['training_steps'],
                           selected_episode=result['selected_episode'])
                run['control_check'] = _control_check(run, reference, episodes=episodes, check_budget=check_budget)
                run['status'] = 'COMPLETED'
                check_budget()
            except IterationBudgetExceeded:
                run.update(status='BUDGET_STOP', error_type='IterationBudgetExceeded')
                raise
            except Exception as exc:
                run.update(status='FAILED', error_type=type(exc).__name__)
            persist()

        for row in cp_rows:
            check_budget()
            data = splits['validation'][row['validation_index']]
            try:
                remaining = max_active_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    raise IterationBudgetExceeded('Shared validation iteration active-time cap expired')
                result = solve_parallel_maintenance(data, mode=row['mode'], time_limit=min(1., remaining),
                                                    num_workers=1, seed=42)
                row.update({field: getattr(result, field) for field in CERTIFICATE_FIELDS})
                row['payload'] = _plan_payload(result, data, row['mode'], row['check'])
                row['plan_sha256'] = _plan_hash(row['payload'])
                status, objective, bound = row['solver_status'], row['solver_objective_value'], row['solver_objective_bound']
                if (status not in ('OPTIMAL', 'FEASIBLE') or type(objective) not in (int, float)
                        or not math.isfinite(objective) or objective != row['payload']['total_tardiness']
                        or type(bound) not in (int, float) or not math.isfinite(bound) or not 0 <= bound <= objective
                        or (status == 'OPTIMAL' and bound != objective)):
                    raise ValueError('CP certificate is inconsistent with its checked plan')
                row.update(validation_status='PASS', schedule_accepted=True, optimum_certified=status == 'OPTIMAL')
                check_budget()
            except IterationBudgetExceeded:
                row.update(validation_status='BUDGET_STOP', schedule_accepted=False, optimum_certified=False,
                           error_type='IterationBudgetExceeded')
                raise
            except Exception as exc:
                if row['solver_status'] is None:
                    for status in ('UNKNOWN', 'INFEASIBLE', 'MODEL_INVALID'):
                        if f'CP-SAT returned {status}' in str(exc):
                            row['solver_status'] = status
                row.update(validation_status='FAIL', schedule_accepted=False, optimum_certified=False,
                           error_type=type(exc).__name__)
            persist()

        for row in rows:
            check_budget()
            data = splits['validation'][row['validation_index']]
            try:
                actor = None
                if row['method'] in METHODS:
                    run = next(item for item in runs if (item['mode'], item['seed'], item['method']) ==
                               (row['mode'], row['seed'], row['method']))
                    if run['status'] != 'COMPLETED':
                        raise ValueError('A failed training run cannot supply accepted validation plans')
                    checkpoint = run['checkpoints']['selected']
                    actor = load_checkpoint(output / checkpoint['path'], expected_sha256=checkpoint['sha256'])
                    episode = run_policy_episode(data, mode=row['mode'], actor=actor, seed=row['seed'],
                                                 deterministic=True, check_budget=check_budget)
                else:
                    episode = run_maintenance_rule_episode(data, mode=row['mode'], rule=row['method'], seed=row['seed'])
                _checked_episode(row, episode, data, actor=actor, check_budget=check_budget)
                reference_row = next(item for item in cp_rows if (item['mode'], item['validation_index']) ==
                                     (row['mode'], row['validation_index']))
                if reference_row['schedule_accepted']:
                    delta = row['payload']['total_tardiness'] - reference_row['payload']['total_tardiness']
                    row['cp_comparison'] = {'solver_status': reference_row['solver_status'],
                        'tardiness_difference': delta, 'optimum_certified': reference_row['optimum_certified']}
                    if reference_row['optimum_certified'] and delta < 0:
                        raise ValueError('A candidate beat an OPTIMAL CP reference; evidence is inconsistent')
                row.update(validation_status='PASS', schedule_accepted=True)
                check_budget()
            except IterationBudgetExceeded:
                row.update(validation_status='BUDGET_STOP', schedule_accepted=False, error_type='IterationBudgetExceeded')
                raise
            except Exception as exc:
                row.update(validation_status='FAIL', schedule_accepted=False, error_type=type(exc).__name__)
            persist()
        if sum(run['training_steps'] for run in runs) > 3072:
            raise ValueError('Iteration exceeded its maximum declared training steps')
        check_budget()
    except IterationBudgetExceeded:
        timed_out = True
        evidence['error_type'] = 'IterationBudgetExceeded'
    except Exception as exc:
        evidence['error_type'] = type(exc).__name__

    completed = sum(run['status'] == 'COMPLETED' for run in runs)
    accepted = sum(row['schedule_accepted'] for row in rows)
    cp_accepted = sum(row['schedule_accepted'] for row in cp_rows)
    complete = completed == 8 and accepted == 80 and cp_accepted == 8 and evidence['error_type'] is None
    evidence['decisions'] = _decisions(rows, complete=complete and not timed_out)
    persist()

    def artifacts():
        return {path.relative_to(output).as_posix(): _sha(path.read_bytes())
                for path in sorted(output.rglob('*')) if path.is_file() and path.name != 'manifest.json'}

    artifact_hashes = artifacts()
    try:
        check_budget()
    except IterationBudgetExceeded:
        timed_out = True
        evidence['error_type'] = 'IterationBudgetExceeded'
        evidence['decisions'] = _decisions(rows, complete=False)
        persist()
        artifact_hashes = artifacts()
    status = 'BUDGET_STOP' if timed_out else 'COMPLETED' if complete else 'FAILED'
    manifest = {'version': 1, 'purpose': PURPOSE, 'status': status, 'limitation': LIMITATION,
        'research_status': 'not_achieved', 'probe_evaluated': False, 'final_test_evaluated': False,
        'research_targets': {'paper_reproduction': 'not_achieved', 'graduation_research': 'not_achieved'},
        'expected_training_runs': 8, 'completed_training_runs': completed,
        'expected_validation_rows': 80, 'accepted_validation_rows': accepted,
        'expected_policy_validation_rows': 32, 'expected_rule_validation_rows': 48,
        'expected_cp_rows': 8, 'accepted_cp_rows': cp_accepted,
        'training_steps': sum(run['training_steps'] for run in runs), 'config': config,
        'data_sha256': data_hash, 'config_sha256': config_hash, 'source_hashes': source_hashes,
        'plan_sha256': plan_hash, 'diagnosis_sha256': diagnosis_hash, 'reference': evidence['reference'],
        'decisions': evidence['decisions'], 'outcome_digest': _digest_outcome(evidence),
        'artifacts': artifact_hashes, 'error_type': evidence['error_type'],
        'runtime': {'python': sys.version, 'python_executable': sys.executable, 'numpy': np.__version__,
            'numpy_preimported': NUMPY_PREIMPORTED, 'threads': {key: os.environ[key] for key in THREAD_VARIABLES},
            'elapsed_seconds': time.monotonic() - started}}
    _write_json(output / 'manifest.json', manifest)
    # The last write is work too: an expired finalization cannot claim success.
    try:
        check_budget()
    except IterationBudgetExceeded:
        evidence['error_type'] = 'IterationBudgetExceeded'
        evidence['decisions'] = _decisions(rows, complete=False)
        persist()
        manifest.update(status='BUDGET_STOP', error_type='IterationBudgetExceeded',
                        decisions=evidence['decisions'], outcome_digest=_digest_outcome(evidence), artifacts=artifacts())
        manifest['runtime']['elapsed_seconds'] = time.monotonic() - started
        _write_json(output / 'manifest.json', manifest)
    return json.loads((output / 'manifest.json').read_bytes())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--episodes', type=int, default=64)
    parser.add_argument('--max-active-seconds', type=float, default=120)
    parser.add_argument('--reference-archive', type=Path)
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = args.output_dir or ROOT / 'experiments/runs/validation_iteration' / stamp
    try:
        manifest = run_experiment(output, episodes=args.episodes, max_active_seconds=args.max_active_seconds,
                                  reference_archive=args.reference_archive)
    except (ValueError, OSError) as exc:
        print(f'Validation iteration stopped: {type(exc).__name__}')
        return 1
    print(f"{manifest['status']}: validation={manifest['accepted_validation_rows']}/80; "
          f"CP={manifest['accepted_cp_rows']}/8; {output / 'manifest.json'}")
    print(LIMITATION)
    return 0 if manifest['status'] == 'COMPLETED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
