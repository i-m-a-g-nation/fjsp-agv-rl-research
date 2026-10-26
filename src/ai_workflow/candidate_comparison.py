"""One bounded, source-bound shared-scorer comparison on frozen native inputs.

Only candidate_run/ is writable. Archived controls, rules and CP certificates
are replayed/rechecked evidence, never fresh training or optimization. A complete
validation decision is a development artifact and cannot promote a default.
"""
from dataclasses import asdict
import inspect
import math
from pathlib import Path
import time

import numpy as np

from src.graduation.candidate_training import train_shared_policy
from src.graduation.data import to_fjsp_instance
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.metrics import calculate_total_tardiness
from src.graduation.neural_policy import MaskedMLP
from src.graduation.permutation_diagnostics import (
    EXPECTED_CASES, EXPECTED_RUNS, PERMUTATIONS, TOLERANCE, _actor, _compare,
    _fields, _objects, _permutation, _read, _rollout,
)
from src.graduation.policy_training import run_policy_episode
from src.graduation.result import MaintenanceRecord, MaintenanceScheduleResult
from src.graduation.rl_environment import ParallelMaintenanceEnv
from src.graduation.validation_diagnostics import (
    ROOT, _decode, _encoded, _instances, _path_inside, _raw_fields, _require, _sha,
    _state_hash, _training_diagnostics,
)
from src.scheduling.encoding import ScheduleRecord

METHOD = 'shared_scorer_v1'
MODES = ('fixed', 'joint')
SEEDS = (17, 29)
RULES = ('EDD', 'SPT', 'Random')
CERTIFICATES = ('solver_status', 'solver_objective_value', 'solver_objective_bound',
                'solver_gap', 'solver_wall_time')
EXPECTED_COUNTS = {'training_runs': 4, 'training_episodes': 256, 'training_steps': 1536,
    'candidate_validation_rows': 16, 'control_validation_rows': 16,
    'rule_reference_rows': 48, 'cp_reference_rows': 8,
    'permutation_cases': 64, 'equivariance_state_comparisons': 384}


def _report_counts(denominators):
    return {'training_runs': denominators['training_runs'],
        'training_steps': denominators['training_steps'],
        'candidate_validation_plans': denominators['candidate_validation_rows'],
        'control_validation_plans': denominators['control_validation_rows'],
        'rule_reference_plans': denominators['rule_reference_rows'],
        'cp_reference_plans': denominators['cp_reference_rows'],
        'equivariance_states': denominators['equivariance_state_comparisons']}


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(_encoded(value))
    temporary.replace(path)


def _training_split(raw_results, validation_ids, budget):
    raw = _raw_fields(raw_results, {'splits'}, budget)['splits']
    training_raw = _raw_fields(raw, {'training'}, budget)['training']
    training, identities = _instances(_decode(training_raw), 8, budget)
    _require(len(training) == 8 and not set(identities) & set(validation_ids),
             'Frozen training8/validation4 must be complete and disjoint')
    _require(all(len(data.tasks) == 4 and data.num_machines == 2 for data in training),
             'Expected native four-task/two-machine training protocol')
    return tuple(training), identities


def _decisions(rows, *, complete):
    expected = {(mode, seed, index, method) for mode in MODES for seed in SEEDS
                for index in range(4) for method in (METHOD, 'none')}
    decisions = {mode: {'status': 'STOP', 'selected_method': None,
        'mean_validation_tardiness': None, 'per_seed': [], 'development_selection': True}
        for mode in MODES}
    try:
        keys = [(row['mode'], row['seed'], row['validation_index'], row['method']) for row in rows]
        valid = (complete is True and len(rows) == len(set(keys)) == 32 and set(keys) == expected
            and all(row['validation_status'] == 'PASS' and row['schedule_accepted'] is True
                and type(row['payload']['total_tardiness']) in (int, float)
                and math.isfinite(row['payload']['total_tardiness'])
                and row['payload']['total_tardiness'] >= 0 for row in rows))
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        return decisions
    for mode in MODES:
        means = {method: math.fsum(row['payload']['total_tardiness'] for row in rows
            if row['mode'] == mode and row['method'] == method)/8 for method in (METHOD, 'none')}
        decisions[mode].update(status='DECIDED',
            selected_method=METHOD if means[METHOD] < means['none'] else 'none',
            mean_validation_tardiness=means,
            per_seed=[{'seed': seed, 'mean_validation_tardiness': {
                method: math.fsum(row['payload']['total_tardiness'] for row in rows
                    if row['mode'] == mode and row['seed'] == seed and row['method'] == method)/4
                for method in (METHOD, 'none')}} for seed in SEEDS])
    return decisions


def _candidate_identity(batch, actor_class, budget):
    budget()
    _require(isinstance(actor_class, type) and issubclass(actor_class, MaskedMLP)
             and actor_class.policy_kind == METHOD, 'Expected approved shared-scorer actor class')
    source = _path_inside(batch, 'candidate/policy.py')
    _require(Path(inspect.getfile(actor_class)).resolve() == source,
             'Actor class must execute the exact materialized batch template')
    manifest_path = _path_inside(batch, 'candidate/manifest.json')
    raw = manifest_path.read_bytes()
    manifest = _decode(raw.decode('utf-8-sig'))
    digest = _sha(source.read_bytes())
    template = _sha((ROOT / 'src/graduation/candidate_templates/shared_scorer.py').read_bytes())
    _require(manifest['version'] == 1 and manifest['profile'] == METHOD
             and manifest['files_sha256']['policy.py'] == digest
             and manifest['template_sha256'] == digest == template,
             'Candidate template/manifest source hash mismatch')
    for relative, expected in manifest['protected_source_hashes'].items():
        budget()
        _require(_sha(_path_inside(ROOT, relative).read_bytes()) == expected,
                 'Protected candidate source hash mismatch: ' + relative)
    return {'template_sha256': template, 'candidate_source_sha256': digest,
        'package_manifest_sha256': _sha(raw),
        'protected_source_hashes': manifest['protected_source_hashes'],
        'actor_policy_kind': actor_class.policy_kind,
        'training_source_sha256': _sha((ROOT / 'src/graduation/candidate_training.py').read_bytes()),
        'comparison_source_sha256': _sha(Path(__file__).read_bytes())}


def _checkpoint(batch, relative, state, episode, actor_class, identity, data_hash, config_hash, budget):
    budget()
    checked = actor_class.from_state(state).state_dict()
    path = _path_inside(batch, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as handle:
        np.savez_compressed(handle, **checked)
    with np.load(path, allow_pickle=False) as saved:
        restored = actor_class.from_state({key: saved[key] for key in saved.files}).state_dict()
    _require(all(np.array_equal(checked[key], restored[key]) for key in checked),
             'Candidate checkpoint reload changed parameters')
    metadata = {'path': relative, 'sha256': _sha(path.read_bytes()),
        'state_sha256': _state_hash(checked), 'episode': episode, 'trained': episode > 0,
        'format': 'numpy_npz_float64_no_pickle', 'source_identity': identity,
        'data_sha256': data_hash, 'config_sha256': config_hash}
    _write(path.with_suffix('.json'), metadata)
    budget()
    return metadata


def _payload(result, data, mode):
    accepted, issues = check_parallel_maintenance_feasibility(result, data, mode=mode)
    _require(accepted, f'Original G1 rejected candidate/reference plan: {issues}')
    tardiness = calculate_total_tardiness(data, result)
    completion = {record.job_id: record.end for record in result.records}
    independent = sum(max(0, completion[task.job_id]-task.due_date) for task in data.tasks)
    _require(tardiness == independent == result.total_tardiness, 'Independent total tardiness mismatch')
    return {'records': sorted([asdict(record) for record in result.records], key=lambda row: row['job_id']),
        'maintenance_records': sorted([asdict(record) for record in result.maintenance_records],
                                      key=lambda row: row['machine_id']),
        'makespan': result.makespan, 'total_tardiness': tardiness}


def _plan_hash(payload):
    return _sha(_encoded({name: payload[name] for name in
        ('records', 'maintenance_records', 'makespan', 'total_tardiness')}))


def _saved_matches(replayed, saved):
    payload = saved['payload']
    return (replayed['actions'] == saved['actions']
        and replayed['rewards'] == [transition['reward'] for transition in saved['transitions']]
        and all(replayed['payload'][key] == (sorted(payload[key], key=lambda row:
            row['job_id' if key == 'records' else 'machine_id']) if key in
            ('records', 'maintenance_records') else payload[key]) for key in replayed['payload']))


def _replay_rule(data, row, budget):
    env, rewards = ParallelMaintenanceEnv(data, mode=row['mode']), []
    actions = row['actions']
    _require(type(actions) is list and len(actions) == 6, 'Incomplete archived rule action denominator')
    for index, action in enumerate(actions):
        budget()
        _require(type(action) is int and 0 <= action < 100 and env.action_masks()[action],
                 'Illegal archived rule action')
        transition = env.step(action)
        _require(not transition.truncated and transition.terminated == (index == 5),
                 'Incomplete archived rule replay')
        rewards.append(transition.reward)
    payload = _payload(env.get_result(), data, row['mode'])
    replayed = {'actions': actions, 'rewards': rewards, 'payload': payload}
    _require(_saved_matches(replayed, row) and _plan_hash(payload) == row['plan_sha256']
             and math.isclose(math.fsum(rewards), -payload['total_tardiness']/100, abs_tol=1e-12),
             'Archived rule replay/actions/reward/plan hash mismatch')
    _require(all(row['payload'].get(key) is None for key in CERTIFICATES),
             'Archived rule must not claim solver certificates')
    return replayed


def _reference_rows(raw_results, validation, validation_rows, budget):
    fields = _raw_fields(raw_results, {'validation_rows', 'cp_rows', 'config', 'training_runs'}, budget)
    config = _decode(fields['config'])
    _require(config['episodes'] == 64 and config['validation_every'] == 16,
             'Archived controls must have the same native64 training budget')
    control_keys = set()
    for raw in _objects(fields['training_runs'], budget, 8):
        if _fields(raw, ('method',), budget)['method'] != 'none':
            continue
        run = _fields(raw, ('mode', 'seed', 'episodes_completed', 'training_steps'), budget)
        key = run['mode'], run['seed']
        _require(key in EXPECTED_RUNS and key not in control_keys and run['episodes_completed'] == 64
                 and run['training_steps'] == 384, 'Incomplete archived control training budget')
        control_keys.add(key)
    _require(control_keys == EXPECTED_RUNS, 'Incomplete archived control run denominator')
    rules, rule_keys = [], set()
    for raw in _objects(fields['validation_rows'], budget, 80):
        method = _fields(raw, ('method',), budget)['method']
        if method not in RULES:
            continue
        row = _fields(raw, ('method', 'mode', 'seed', 'validation_index', 'instance_identity',
            'actions', 'transitions', 'payload', 'validation_status', 'schedule_accepted', 'plan_sha256'), budget)
        key = row['mode'], row['seed'], row['validation_index'], row['method']
        _require((key[0], key[1], key[2]) in EXPECTED_CASES and key not in rule_keys
            and row['validation_status'] == 'PASS' and row['schedule_accepted'] is True
            and row['instance_identity'] == validation_rows[key[2]]['base_instance_identity'],
            'Invalid archived rule denominator/identity/check status')
        replayed = _replay_rule(validation[key[2]], row, budget)
        rules.append({'method': method, 'mode': key[0], 'seed': key[1], 'validation_index': key[2],
            'instance_identity': row['instance_identity'], 'source_row_sha256': _sha(raw.encode('utf-8')),
            'plan_sha256': row['plan_sha256'], 'payload': replayed['payload'],
            'hash_matches': True, 'G1_accepted': True, 'reference_reused': True, 'fresh_execution': False})
        rule_keys.add(key)
    expected_rules = {(mode, seed, index, rule) for mode, seed, index in EXPECTED_CASES for rule in RULES}
    _require(rule_keys == expected_rules and len(rules) == 48, 'Incomplete archived rule denominator')
    cp, cp_keys = [], set()
    for raw in _objects(fields['cp_rows'], budget, 8):
        budget()
        row = _decode(raw)
        key = row['mode'], row['validation_index']
        _require(key in {(mode, index) for mode in MODES for index in range(4)} and key not in cp_keys
            and row['validation_status'] == 'PASS' and row['schedule_accepted'] is True
            and row['instance_identity'] == validation_rows[key[1]]['base_instance_identity'],
            'Invalid archived CP denominator/identity/check status')
        payload, data = row['payload'], validation[key[1]]
        result = MaintenanceScheduleResult(records=[ScheduleRecord(**record) for record in payload['records']],
            maintenance_records=[MaintenanceRecord(**record) for record in payload['maintenance_records']],
            makespan=payload['makespan'], total_tardiness=payload['total_tardiness'],
            instance=to_fjsp_instance(data), **{name: payload[name] for name in CERTIFICATES})
        checked = _payload(result, data, key[0])
        status, objective, bound = (row[name] for name in CERTIFICATES[:3])
        _require(all(row[name] == payload[name] for name in CERTIFICATES)
            and status in ('OPTIMAL', 'FEASIBLE') and type(objective) in (int, float)
            and math.isfinite(objective) and objective == checked['total_tardiness']
            and type(bound) in (int, float) and math.isfinite(bound) and 0 <= bound <= objective
            and (status != 'OPTIMAL' or objective == bound)
            and type(row['solver_gap']) in (int, float) and math.isfinite(row['solver_gap'])
            and math.isclose(row['solver_gap'], (objective-bound)/max(1., objective), abs_tol=1e-12)
            and type(row['solver_wall_time']) in (int, float)
            and math.isfinite(row['solver_wall_time']) and row['solver_wall_time'] >= 0
            and row['optimum_certified'] is (status == 'OPTIMAL')
            and _plan_hash(checked) == row['plan_sha256'], 'Archived CP certificate/plan hash mismatch')
        cp.append({'mode': key[0], 'validation_index': key[1],
            'instance_identity': row['instance_identity'], 'source_row_sha256': _sha(raw.encode('utf-8')),
            'plan_sha256': row['plan_sha256'], 'payload': payload, 'G1_accepted': True,
            'hash_matches': True, 'reference_reused': True, 'fresh_solve': False,
            'optimum_certified': status == 'OPTIMAL', **{name: row[name] for name in CERTIFICATES}})
        cp_keys.add(key)
    _require(len(cp) == 8, 'Incomplete archived CP denominator')
    return config, rules, cp


def run_comparison(batch_dir, reference_archive, actor_class, *, check_budget=None):
    """Execute exactly four64-episode runs and complete checked native validation.

    Exceptions propagate to the supervising controller; progress and checkpoints
    already written remain in the new owned subtree and cannot be overwritten.
    """
    _require(check_budget is None or callable(check_budget), 'check_budget must be callable or None')
    started = time.monotonic()

    def budget():
        if time.monotonic()-started >= 120:
            raise TimeoutError('Controlled candidate comparison exceeded120 active seconds')
        if check_budget is not None:
            check_budget()

    batch, archive = Path(batch_dir).resolve(), Path(reference_archive).resolve()
    output = batch / 'candidate_run'
    _require(not output.is_relative_to(archive) and not archive.is_relative_to(output),
             'Candidate output must be outside the read-only reference archive')
    output.mkdir(parents=False, exist_ok=False)
    budget()
    identity = _candidate_identity(batch, actor_class, budget)
    manifest, manifest_hash, validation_rows, validation, controls, saved_rows = _read(archive, budget)
    _require(all(len(data.tasks) == 4 and data.num_machines == 2 for data in validation),
             'Expected native validation4/four-task/two-machine protocol')
    raw_results = _path_inside(archive, 'results.json').read_text(encoding='utf-8-sig')
    validation_ids = [row['base_instance_identity'] for row in validation_rows]
    training, training_ids = _training_split(raw_results, validation_ids, budget)
    split_raw = _raw_fields(_raw_fields(raw_results, {'splits'}, budget)['splits'],
        {'version', 'generator', 'work_definition', 'training', 'validation'}, budget)
    data_hash = _sha(_encoded({key: _decode(value) for key, value in split_raw.items()}))
    _require(data_hash == manifest['data_sha256'], 'Frozen training/validation metadata hash mismatch')
    reference_config, rule_rows, cp_rows = _reference_rows(raw_results, validation, validation_rows, budget)
    _require(_sha(_encoded(reference_config)) == manifest['config_sha256'],
             'Archived control configuration hash mismatch')
    config = {'profile': METHOD, 'episodes': 64, 'validation_every': 16,
        'modes': list(MODES), 'seeds': list(SEEDS), 'hidden_size': 16, 'parameter_count': 545,
        'learning_rate': .01, 'max_grad_norm': 1., 'gamma': 1, 'return_baseline': 'none',
        'reward': '-total_tardiness/100', 'max_training_steps': 1536, 'hyperparameter_search': False,
        'selection': 'minimum_greedy_validation_mean_tardiness_earliest_tie',
        'candidate_selection': 'strictly_lower_pooled_validation_mean_else_none',
        'source_identity': identity, 'network_calls': 0, 'model_api_calls': 0}
    config_hash = _sha(_encoded(config))
    _write(output / 'config.json', config)
    _write(output / 'inputs.json', {'training_base_identities': training_ids,
        'validation_base_identities': validation_ids, 'data_sha256': data_hash,
        'reference_manifest_sha256': manifest_hash, 'reference_results_sha256': manifest['artifacts']['results.json']})
    runs, candidate_rows, control_rows, permutations = [], [], [], []
    for mode, seed in sorted(EXPECTED_RUNS):
        budget()
        relative = f'candidate_run/checkpoints/{mode}-seed{seed}'
        log_relative = f'candidate_run/logs/{mode}-seed{seed}.jsonl'
        log_path = _path_inside(batch, log_relative)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        interval = []
        initial_checkpoints = []

        def save(name, state, episode):
            return _checkpoint(batch, relative+'/'+name+'.npz', state, episode,
                               actor_class, identity, data_hash, config_hash, budget)

        def progress(event):
            budget()
            event = dict(event)
            if event['kind'] == 'validation':
                episode = event['episode']
                current = event.pop('current_state')
                selected = event.pop('selected_state')
                current_meta = save(f'current-episode-{episode:03d}', current, episode)
                selected_meta = save(f'selected-episode-{episode:03d}', selected, event['selected_episode'])
                if episode == 0:
                    initial_checkpoints.append(save('initial', current, 0))
                entry = {'episode': episode, 'current': current_meta, 'selected': selected_meta}
                interval.append(entry)
                event['checkpoints'] = entry
            with log_path.open('ab') as handle:
                handle.write(_encoded(event)+b'\n')
                handle.flush()
            budget()

        trained = train_shared_policy(training, tuple(validation), mode=mode, seed=seed,
            episodes=64, validation_every=16, actor_class=actor_class, check_budget=budget, on_progress=progress)
        _require(trained['episodes_completed'] == 64 and trained['training_steps'] == 384,
                 'Incomplete candidate training episode/step denominator')
        diagnostic = _training_diagnostics(trained, training, training_ids, budget)
        history = trained['validation_history']
        _require([row['episode'] for row in history] == [0, 16, 32, 48, 64]
            and len(interval) == 5, 'Incomplete candidate interval validation/checkpoint denominator')
        best = min(history, key=lambda row: row['validation_mean_tardiness'])
        _require(trained['selected_episode'] == best['episode'] and all(
            len(row['validation_rows']) == 4 and row['training_steps'] == row['episode']*6 for row in history),
            'Candidate selected checkpoint is not earliest strict validation minimum')
        checkpoints = {'initial': initial_checkpoints[0],
            'final': save('final', trained['final_state'], 64),
            'selected': save('selected', trained['selected_state'], trained['selected_episode'])}
        _require(checkpoints['selected']['state_sha256'] == next(entry['current']['state_sha256']
            for entry in interval if entry['episode'] == best['episode']),
            'Candidate selected state does not match its selected validation interval')
        selected_path = _path_inside(batch, checkpoints['selected']['path'])
        with np.load(selected_path, allow_pickle=False) as saved:
            actor = actor_class.from_state({name: saved[name] for name in saved.files})
        frozen_hash = _state_hash(actor.state_dict())
        run = {'method': METHOD, 'mode': mode, 'seed': seed, 'status': 'COMPLETED',
            'episodes_completed': 64, 'training_steps': 384, 'selected_episode': best['episode'],
            'logs': trained['logs'], 'validation_history': history, 'training_diagnostics': diagnostic,
            'checkpoints': checkpoints, 'interval_checkpoints': interval, 'progress_log': log_relative,
            'progress_log_sha256': _sha(log_path.read_bytes())}
        runs.append(run)
        reference_actor = _actor(archive, manifest, controls[mode, seed], budget)
        for index, data in enumerate(validation):
            budget()
            original, states = _rollout(actor, data, mode, budget)
            episode = run_policy_episode(data, mode=mode, actor=actor,
                seed=(seed+index) % 2**32, deterministic=True, check_budget=budget)
            selected_validation = best['validation_rows'][index]
            _require(original['actions'] == list(episode.actions) == list(selected_validation['actions'])
                and original['rewards'] == list(episode.rewards) == list(selected_validation['rewards'])
                and original['payload']['total_tardiness'] == selected_validation['total_tardiness'],
                'Reloaded selected actor differs from selected validation/checked original rollout')
            candidate_rows.append({'method': METHOD, 'mode': mode, 'seed': seed, 'validation_index': index,
                'instance_identity': validation_ids[index], 'validation_status': 'PASS',
                'schedule_accepted': True, 'checkpoint': checkpoints['selected'], **original})
            replayed, _ = _rollout(reference_actor, data, mode, budget)
            saved = saved_rows[mode, seed, index]
            saved_plan_hash = _plan_hash(saved['payload'])
            _require(_saved_matches(replayed, saved) and replayed['plan_sha256'] == saved_plan_hash,
                     'Archived control actions/reward/plan replay mismatch')
            control_rows.append({'method': 'none', 'mode': mode, 'seed': seed, 'validation_index': index,
                'instance_identity': validation_ids[index], 'validation_status': 'PASS',
                'schedule_accepted': True, 'checkpoint': controls[mode, seed]['selected'],
                'validated_reference_fields_sha256': _sha(_encoded(saved)),
                'saved_plan_sha256': saved_plan_hash, 'hash_matches': True,
                'reference_reused': True, 'fresh_training': False, **replayed})
            for name in PERMUTATIONS:
                budget()
                relabeled, jobs, machines, action_map = _permutation(data, name)
                mapped, mapped_states = _rollout(actor, relabeled, mode, budget,
                    [action_map[action] for action in original['actions']])
                _require(len(states) == len(mapped_states) == 6, 'Incomplete equivariance state denominator')
                comparisons = _compare(states, mapped_states, jobs, machines, action_map, budget)
                _require(all(not row['sensitive'] and row['uniform_max_error'] == 0 for row in comparisons)
                    and mapped['payload']['total_tardiness'] == original['payload']['total_tardiness'],
                    'Candidate distribution equivariance/physical tardiness check failed')
                permutations.append({'mode': mode, 'seed': seed, 'validation_index': index,
                    'instance_identity': validation_ids[index], 'permutation': name,
                    'action_map': action_map, 'mapped_replay': mapped, 'states': comparisons,
                    'max_probability_error': max(row['max_probability_error'] for row in comparisons)})
        _require(_state_hash(actor.state_dict()) == frozen_hash, 'Selected candidate changed during validation')
        _write(output / f'runs/{mode}-seed{seed}.json', run)
    counts = {'training_runs': len(runs), 'training_episodes': sum(run['episodes_completed'] for run in runs),
        'training_steps': sum(run['training_steps'] for run in runs),
        'candidate_validation_rows': len(candidate_rows), 'control_validation_rows': len(control_rows),
        'rule_reference_rows': len(rule_rows), 'cp_reference_rows': len(cp_rows),
        'permutation_cases': len(permutations),
        'equivariance_state_comparisons': sum(len(case['states']) for case in permutations)}
    complete = counts == EXPECTED_COUNTS
    decisions = _decisions(candidate_rows+control_rows, complete=complete)
    _require(complete and all(value['status'] == 'DECIDED' for value in decisions.values()),
             'Incomplete comparison cannot retain any candidate')
    _require(_candidate_identity(batch, actor_class, budget) == identity,
             'Candidate source identity changed during comparison')
    for relative, digest in manifest['artifacts'].items():
        budget()
        _require(_sha(_path_inside(archive, relative).read_bytes()) == digest,
                 'Reference artifact changed during comparison')
    for relative, digest in manifest['source_hashes'].items():
        budget()
        _require(_sha(_path_inside(ROOT, relative).read_bytes()) == digest,
                 'Original source changed during comparison')
    _require(_sha((archive / 'manifest.json').read_bytes()) == manifest_hash,
             'Reference manifest changed during comparison')
    denominators, counts = counts, _report_counts(counts)
    report = {'version': 1, 'kind': 'controlled_candidate_comparison', 'status': 'COMPLETED',
        'research_status': 'not_achieved', 'network_calls': 0, 'model_api_calls': 0,
        'probe_evaluated': False, 'final_test_evaluated': False, 'production_default_changed': False,
        'training_performed': True, 'all_checks_passed': True, 'config': config,
        'source_identity': identity, 'counts': counts, 'expected_counts': _report_counts(EXPECTED_COUNTS),
        'denominators': denominators, 'expected_denominators': EXPECTED_COUNTS,
        'decisions': decisions, 'training_runs': runs, 'candidate_rows': candidate_rows,
        'validation_rows': candidate_rows+control_rows,
        'control_rows': control_rows, 'rule_rows': rule_rows, 'cp_rows': cp_rows,
        'permutation_cases': permutations, 'equivariance_tolerance': TOLERANCE,
        'reference_reuse': {'fresh_control_training': False, 'fresh_rule_execution': False,
            'fresh_cp_solves': False, 'control_episodes_per_run': 64, 'G1_and_TT_rechecked': True,
            'manifest_sha256': manifest_hash, 'results_sha256': manifest['artifacts']['results.json'],
            'source_hashes': manifest['source_hashes']},
        'limitation': 'Development selection on reused validation only; no independent performance proof or research approval.'}
    stable = {'selected_states': [run['checkpoints']['selected']['state_sha256'] for run in runs],
        'final_states': [run['checkpoints']['final']['state_sha256'] for run in runs],
        'candidate_outcomes': [row['payload'] for row in candidate_rows],
        'control_outcomes': [row['payload'] for row in control_rows], 'decisions': decisions,
        'counts': counts, 'training_logs': [run['logs'] for run in runs]}
    report['outcome_digest'] = _sha(_encoded(stable))
    budget()
    _write(output / 'results.json', report)
    artifacts = {}
    for path in sorted(output.rglob('*')):
        budget()
        if path.is_file():
            artifacts[path.relative_to(batch).as_posix()] = _sha(path.read_bytes())
    _write(output / 'manifest.json', {'version': 1, 'status': 'COMPLETED',
        'kind': report['kind'], 'artifacts': artifacts, 'outcome_digest': report['outcome_digest'],
        'source_identity': identity, 'research_status': 'not_achieved'})
    artifacts['candidate_run/manifest.json'] = _sha((output / 'manifest.json').read_bytes())
    budget()
    return {**report, 'artifacts': artifacts}
