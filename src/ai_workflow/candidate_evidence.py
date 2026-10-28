"""Independent structural/replay acceptance of a complete candidate artifact set."""
import math
from pathlib import Path

import numpy as np

from src.ai_workflow.research_tasks import encoded, read_json, sha, _validate_plan
from src.graduation.validation_diagnostics import _path_inside, _raw_fields, _decode, _state_hash


def verify_comparison_evidence(batch, result, *, check_budget=lambda: None):
    from src.ai_workflow.candidate_comparison import trial_layout, comparison_config
    batch = Path(batch).resolve()
    trial = result.get('trial', 'initial')
    prefix, _, kind = trial_layout(trial)
    if result['kind'] != kind:
        raise ValueError('Comparison trial kind differs')
    artifacts = result['artifacts']
    if not {prefix+'/results.json', prefix+'/manifest.json'} <= artifacts.keys():
        raise ValueError('Missing complete comparison training artifacts')
    actual = {}
    for path in sorted((batch / prefix).rglob('*')):
        check_budget()
        if path.is_symlink():
            raise ValueError('Comparison artifacts cannot contain links')
        if path.is_file():
            actual[path.relative_to(batch).as_posix()] = sha(path.read_bytes())
    if artifacts != actual:
        raise ValueError('Incomplete comparison artifact closure')
    saved = read_json(batch / prefix / 'results.json')
    if encoded(saved) != encoded({k: v for k, v in result.items() if k != 'artifacts'}):
        raise ValueError('Comparison summary differs from saved complete results')
    manifest = read_json(batch / prefix / 'manifest.json')
    expected = {k: v for k, v in artifacts.items() if k != prefix+'/manifest.json'}
    if manifest['status'] != 'COMPLETED' or manifest['artifacts'] != expected:
        raise ValueError('Incomplete comparison manifest')
    package = read_json(batch / 'candidate/manifest.json')
    identity = result['source_identity']
    config = comparison_config(identity, trial)
    if encoded(result['config']) != encoded(config) or encoded(read_json(batch/prefix/'config.json')) != encoded(config):
        raise ValueError('Comparison registered configuration differs')
    config_hash = sha(encoded(config))
    if (identity['package_manifest_sha256'] != sha((batch / 'candidate/manifest.json').read_bytes())
            or identity['candidate_source_sha256'] != package['template_sha256']
            or identity['template_sha256'] != package['template_sha256']
            or identity['protected_source_hashes'] != package['protected_source_hashes']):
        raise ValueError('Comparison source identity mismatch')
    spec = read_json(batch / 'spec.json')
    reference = Path(spec['identity']['reference_archive'])
    from src.ai_workflow.candidate_replay import verified_splits, verify_training_replay
    _, _, bound_inputs = verified_splits(reference, check_budget)
    if (read_json(batch/prefix/'inputs.json') != bound_inputs
            or bound_inputs['reference_manifest_sha256'] != spec['input_hashes']['validation/manifest.json']
            or bound_inputs['reference_results_sha256'] != spec['input_hashes']['validation/results.json']):
        raise ValueError('Comparison data identity differs from bound reference')
    data_hash = bound_inputs['data_sha256']
    raw = (reference / 'results.json').read_text(encoding='utf-8-sig')
    split = _raw_fields(_raw_fields(raw, {'splits'}, lambda: None)['splits'], {'validation'}, lambda: None)
    inputs = _decode(split['validation'])
    rows = result['validation_rows']
    keys = [(r['mode'], r['seed'], r['validation_index'], r['method']) for r in rows]
    all_keys = {(m, s, i, method) for m in ('fixed', 'joint') for s in (17, 29) for i in range(4)
                for method in ('none', 'shared_scorer_v1')}
    if (len(keys) != 32 or len(set(keys)) != 32 or set(keys) != all_keys
            or rows != result['candidate_rows'] + result['control_rows']):
        raise ValueError('Incomplete comparison validation denominator')
    for row in rows:
        check_budget()
        if row['validation_status'] != 'PASS' or row['schedule_accepted'] is not True:
            raise ValueError('Unchecked comparison plan')
        _validate_plan(row, inputs[row['validation_index']]['input'], row['mode'])
    for mode in ('fixed', 'joint'):
        means = {method: math.fsum(r['payload']['total_tardiness'] for r in rows
                 if r['mode'] == mode and r['method'] == method)/8 for method in ('none', 'shared_scorer_v1')}
        if means != result['decisions'][mode]['mean_validation_tardiness']:
            raise ValueError('Comparison means differ from checked validation rows')
    runs = result['training_runs']
    if len(runs) != 4 or {(r['mode'], r['seed']) for r in runs} != {(m, s) for m in ('fixed', 'joint') for s in (17, 29)}:
        raise ValueError('Incomplete comparison training denominator')
    for run in runs:
        check_budget()
        if (run['status'] != 'COMPLETED' or run['episodes_completed'] != 64 or run['training_steps'] != 384
                or len(run['logs']) != 64 or [r['episode'] for r in run['logs']] != list(range(1, 65))
                or len(run['interval_checkpoints']) != 5):
            raise ValueError('Incomplete comparison training progress')
        history = run['validation_history']
        if [r['episode'] for r in history] != [0, 16, 32, 48, 64]:
            raise ValueError('Incomplete comparison checkpoint selection')
        best = min(history, key=lambda v: v['validation_mean_tardiness'])
        if run['selected_episode'] != best['episode']:
            raise ValueError('Comparison selected a nonminimal checkpoint')
        log_path = _path_inside(batch, run['progress_log'])
        if not run['progress_log'].startswith(prefix+'/logs/'):
            raise ValueError('Comparison log belongs to another trial')
        events = [_decode(line) for line in log_path.read_text(encoding='utf-8').splitlines()]
        if (sha(log_path.read_bytes()) != run['progress_log_sha256']
                or len(events) != 69 or sum(e['kind'] == 'episode' for e in events) != 64):
            raise ValueError('Incomplete comparison durable log')
        checkpoints = list(run['checkpoints'].values())
        checkpoints += [entry[name] for entry in run['interval_checkpoints'] for name in ('current', 'selected')]
        for checkpoint in checkpoints:
            check_budget()
            if (not checkpoint['path'].startswith(prefix+'/checkpoints/')
                    or checkpoint['config_sha256'] != config_hash or checkpoint['data_sha256'] != data_hash
                    or checkpoint['source_identity'] != identity):
                raise ValueError('Comparison checkpoint configuration/data/trial differs')
            path = _path_inside(batch, checkpoint['path'])
            if (sha(path.read_bytes()) != checkpoint['sha256']
                    or read_json(path.with_suffix('.json')) != checkpoint):
                raise ValueError('Comparison checkpoint identity mismatch')
            with np.load(path, allow_pickle=False) as arrays:
                state = {k: arrays[k] for k in arrays.files}
            if _state_hash(state) != checkpoint['state_sha256']:
                raise ValueError('Comparison checkpoint parameter identity mismatch')
    permutations = result['permutation_cases']
    expected_keys = {(m, s, i, p) for m in ('fixed', 'joint') for s in (17, 29) for i in range(4)
                     for p in ('identity', 'jobs_reverse', 'machines_reverse', 'both_reverse')}
    keys = [(c['mode'], c['seed'], c['validation_index'], c['permutation']) for c in permutations]
    if (len(keys) != 64 or set(keys) != expected_keys or any(len(c['states']) != 6 for c in permutations)
            or any(s['sensitive'] is not False or not 0 <= s['max_probability_error'] <= 1e-10
                   for c in permutations for s in c['states'])):
        raise ValueError('Incomplete comparison equivariance evidence')
    if len(result['rule_rows']) != 48 or len(result['cp_rows']) != 8:
        raise ValueError('Incomplete comparison reference denominator')
    from src.ai_workflow.controlled_candidate import load_candidate
    verify_training_replay(batch, reference, result, load_candidate(batch), check_budget=check_budget)
    if trial != 'initial':
        from src.ai_workflow.candidate_feedback import comparison_feedback
        if result.get('feedback') != comparison_feedback(batch, result, check_budget=check_budget):
            raise ValueError('Comparison feedback decision differs')
