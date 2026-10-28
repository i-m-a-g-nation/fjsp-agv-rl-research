"""Independent numerical replay of saved shared-scorer training evidence.

This does not call the trainer or its optimizer. It evaluates one forward pass
per state and independently derives masked REINFORCE gradients and updates.
Only successful verifications are memoized in this process, after hashing actual
checkpoint bytes; no persisted receipt can populate this cache.
"""
from collections import OrderedDict
import inspect
import math
from pathlib import Path

import numpy as np

from src.ai_workflow.research_tasks import encoded, read_json, sha
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.metrics import calculate_total_tardiness
from src.graduation.neural_policy import masked_probabilities, policy_features
from src.graduation.permutation_diagnostics import _rollout
from src.graduation.rl_environment import ParallelMaintenanceEnv
from src.graduation.state_encoding import encode_construction_observation as encode
from src.graduation.validation_diagnostics import _decode, _raw_fields, _instances, _path_inside, _require, _state_hash

_VERIFIED = OrderedDict()


def verified_splits(reference, check_budget=lambda: None):
    check_budget()
    reference = Path(reference).resolve()
    manifest_bytes = (reference/'manifest.json').read_bytes()
    manifest = _decode(manifest_bytes.decode('utf-8-sig'))
    raw = (reference/'results.json').read_bytes()
    _require(manifest['status'] == 'COMPLETED' and sha(raw) == manifest['artifacts']['results.json'],
             'Replay reference results identity mismatch')
    split_raw = _raw_fields(_raw_fields(raw.decode('utf-8-sig'), {'splits'}, check_budget)['splits'],
        {'version', 'generator', 'work_definition', 'training', 'validation'}, check_budget)
    split = {k:_decode(v) for k,v in split_raw.items()}
    data_hash = sha(encoded(split))
    _require(data_hash == manifest['data_sha256'], 'Replay reference split identity mismatch')
    train, train_ids = _instances(split['training'], 8, check_budget)
    validation, val_ids = _instances(split['validation'], 4, check_budget)
    _require(len(train) == 8 and len(validation) == 4 and not set(train_ids) & set(val_ids)
        and all(len(d.tasks) == 4 and d.num_machines == 2 for d in train+validation),
        'Replay requires disjoint native train8/validation4')
    return train, validation, {'training_base_identities': train_ids, 'validation_base_identities': val_ids,
        'data_sha256': data_hash, 'reference_manifest_sha256': sha(manifest_bytes),
        'reference_results_sha256': sha(raw)}


def _same_state(actual, expected):
    # Same floating-point algebra, with tolerance for BLAS/platform rounding.
    return set(actual) == set(expected) and all(
        actual[k].shape == expected[k].shape and actual[k].dtype == expected[k].dtype
        and np.allclose(actual[k], expected[k], rtol=1e-12, atol=1e-13) for k in actual)


def _verify_validation(run, validation, identities, checkpoints, candidates, actor_class, check_budget):
    """Reproduce checkpoint selection and attributed plans, including the retry."""
    history, intervals = run['validation_history'], run['interval_checkpoints']
    _require([h['episode'] for h in history] == [0,16,32,48,64], 'Replay validation intervals differ')
    best, best_mean, plans_by_episode = 0, math.inf, {}
    for h, interval in zip(history, intervals):
        check_budget()
        ep = h['episode']
        _require(h['training_steps'] == ep*6 and len(h['validation_rows']) == 4,
                 'Replay validation denominator differs')
        actor = actor_class.from_state(checkpoints[interval['current']['path']])
        plans = []
        for i, data in enumerate(validation):
            plan, _ = _rollout(actor, data, run['mode'], check_budget)
            saved = h['validation_rows'][i]
            _require(saved['validation_index'] == i and saved['instance_identity'] == identities[i]
                and saved['seed'] == (run['seed']+i)%2**32
                and encoded(plan['actions']) == encoded(saved['actions'])
                and encoded(plan['rewards']) == encoded(saved['rewards'])
                and plan['payload']['total_tardiness'] == saved['total_tardiness']
                and math.isclose(math.fsum(plan['rewards']), saved['total_reward'], abs_tol=1e-12),
                'Replay validation plan differs from checkpoint')
            plans.append(plan)
        mean = math.fsum(p['payload']['total_tardiness'] for p in plans)/4
        if mean < best_mean:
            best, best_mean = ep, mean
        _require(h['validation_mean_tardiness'] == mean and h['selected_episode'] == best
            and interval['selected']['episode'] == best,
            'Replay validation mean/earliest selection differs')
        plans_by_episode[ep] = plans
    _require(run['selected_episode'] == best and run['checkpoints']['selected']['episode'] == best,
             'Replay selected checkpoint differs')
    for i, plan in enumerate(plans_by_episode[best]):
        matches = [r for r in candidates if (r['mode'],r['seed'],r['validation_index']) ==
                   (run['mode'],run['seed'],i)]
        _require(len(matches) == 1, 'Replay selected plan denominator differs')
        row = matches[0]
        _require(row['checkpoint'] == run['checkpoints']['selected']
            and row['instance_identity'] == identities[i]
            and encoded(row['payload']) == encoded(plan['payload'])
            and encoded(row['actions']) == encoded(plan['actions'])
            and encoded(row['rewards']) == encoded(plan['rewards'])
            and row['plan_sha256'] == plan['plan_sha256'],
            'Replay selected plan differs from selected actor')


def _verify_references(reference, comparison, validation, check_budget):
    """Bind reused controls and certificates to the actual frozen reference rows."""
    from src.ai_workflow.candidate_comparison import _reference_rows, _saved_matches, _plan_hash
    from src.graduation.permutation_diagnostics import _objects, _fields
    raw = (Path(reference)/'results.json').read_text(encoding='utf-8-sig')
    fields = _raw_fields(raw, {'splits', 'validation_rows', 'training_runs'}, check_budget)
    split = _decode(_raw_fields(fields['splits'], {'validation'}, check_budget)['validation'])
    _, rules, cp = _reference_rows(raw, validation, split, check_budget)
    _require(encoded(comparison['rule_rows']) == encoded(rules)
        and encoded(comparison['cp_rows']) == encoded(cp), 'Replay frozen rule/CP reference differs')
    selected, controls = {}, {}
    for item in _objects(fields['training_runs'], check_budget, 8):
        if _fields(item, ('method',), check_budget)['method'] == 'none':
            run = _fields(item, ('mode', 'seed', 'checkpoints'), check_budget)
            selected[run['mode'], run['seed']] = run['checkpoints']['selected']
    for item in _objects(fields['validation_rows'], check_budget, 80):
        if _fields(item, ('method',), check_budget)['method'] == 'none':
            row = _fields(item, ('mode', 'seed', 'validation_index', 'instance_identity', 'actions',
                'transitions', 'payload', 'validation_status', 'schedule_accepted'), check_budget)
            controls[row['mode'], row['seed'], row['validation_index']] = row
    rows = comparison['control_rows']
    keys = [(r['mode'], r['seed'], r['validation_index']) for r in rows]
    _require(len(rows) == len(set(keys)) == len(controls) == 16 and set(keys) == set(controls),
             'Replay frozen control denominator differs')
    for key, row in zip(keys, rows):
        check_budget()
        saved = controls[key]
        _require(row['method'] == 'none' and row['instance_identity'] == saved['instance_identity']
            and row['checkpoint'] == selected[key[:2]] and _saved_matches(row, saved)
            and row['validated_reference_fields_sha256'] == sha(encoded(saved))
            and row['plan_sha256'] == row['saved_plan_sha256'] == _plan_hash(saved['payload'])
            and row['reference_reused'] is True and row['fresh_training'] is False,
            'Replay frozen none control differs')


def _replay_episode(actor, data, mode, seed, rate, check_budget):
    env = ParallelMaintenanceEnv(data, mode=mode)
    rng = np.random.Generator(np.random.PCG64(seed))
    parameters = actor.state_dict()
    actions, rewards, gradients, logps = [], [], [], []
    for index in range(6):
        check_budget()
        observation = env.observe()
        x, hidden, logits = actor._forward(policy_features(encode(observation)))
        p = masked_probabilities(logits, observation.action_mask)
        action = int(rng.choice(len(p), p=p))
        legal = logits[np.asarray(observation.action_mask, dtype=bool)]
        maximum = float(np.max(legal))
        logps.append(float(logits[action]-maximum-np.log(np.exp(legal-maximum).sum())))
        dz = -p
        dz[action] += 1.
        dh = dz[:, None]*parameters['w2'][None, :]*(1.-hidden*hidden)
        gradients.append({'w1': x.T@dh, 'b1': dh.sum(axis=0), 'w2': hidden.T@dz,
                          'b2': np.asarray([dz.sum()], dtype=np.float64)})
        transition = env.step(action)
        _require(not transition.truncated and transition.terminated == (index == 5),
                 'Replay did not complete the original episode')
        actions.append(action)
        rewards.append(transition.reward)
    result = env.get_result()
    accepted, _ = check_parallel_maintenance_feasibility(result, data, mode=mode)
    tardiness = calculate_total_tardiness(data, result)
    _require(accepted and tardiness == result.total_tardiness
        and math.isclose(math.fsum(rewards), -tardiness/100, rel_tol=1e-12, abs_tol=1e-12),
        'Replay training plan/reward rejected by original G1')
    combined = {k:np.zeros_like(v) for k,v in parameters.items()}
    loss = 0.
    for index, gradient in enumerate(gradients):
        weight = math.fsum(rewards[index:])
        loss -= weight*logps[index]/6
        for key in combined:
            combined[key] += (weight/6)*gradient[key]
    norm = math.sqrt(math.fsum(float(np.sum(g*g)) for g in combined.values()))
    factor = min(1., 1./norm) if norm else 1.
    next_state = {k:v+rate*factor*combined[k] for k,v in parameters.items()}
    changed = any(not np.array_equal(parameters[k], next_state[k]) for k in parameters)
    update = {'loss': float(loss), 'gradient_norm': norm, 'applied_gradient_norm': norm*factor,
              'changed': changed, 'samples': 6}
    return next_state, actions, rewards, tardiness, update


def verify_training_replay(batch, reference, comparison, actor_class, *, check_budget=lambda: None):
    check_budget()
    batch = Path(batch).resolve()
    train, validation, inputs = verified_splits(reference, check_budget)
    prefix = 'candidate_step_run' if comparison.get('trial') == 'larger_step_v1' else 'candidate_run'
    _require(read_json(batch/prefix/'inputs.json') == inputs, 'Replay data identity differs from bound reference')
    rate = comparison['config']['learning_rate']
    _require(type(rate) is float and rate in (.01, .1), 'Replay step size is not registered')
    runs = comparison['training_runs']
    _require(len(runs) == 4 and {(r['mode'], r['seed']) for r in runs} ==
             {(m,s) for m in ('fixed', 'joint') for s in (17, 29)}, 'Replay run denominator differs')
    checkpoints, hashes = {}, {}
    for run in runs:
        check_budget()
        log_path = _path_inside(batch, run['progress_log'])
        log_bytes = log_path.read_bytes()
        events = [_decode(line) for line in log_bytes.decode('utf-8').splitlines()]
        _require(sha(log_bytes) == run['progress_log_sha256'] and len(events) == 69
            and encoded([e['log'] for e in events if e['kind'] == 'episode']) == encoded(run['logs']),
            'Replay durable training log differs')
        validation_events = [e for e in events if e['kind'] == 'validation']
        _require(len(validation_events) == len(run['validation_history']) == 5,
                 'Replay durable validation denominator differs')
        for event, h, interval in zip(validation_events, run['validation_history'], run['interval_checkpoints']):
            _require(encoded({k:event[k] for k in h}) == encoded(h) and event['checkpoints'] == interval,
                     'Replay durable validation log differs')
        metadata = list(run['checkpoints'].values()) + [entry[k] for entry in run['interval_checkpoints']
                                                       for k in ('current', 'selected')]
        for meta in metadata:
            path = _path_inside(batch, meta['path'])
            blob = path.read_bytes()
            _require(sha(blob) == meta['sha256'] and meta['data_sha256'] == inputs['data_sha256']
                and read_json(path.with_suffix('.json')) == meta, 'Replay checkpoint identity mismatch')
            hashes[meta['path']] = sha(blob)
            with np.load(path, allow_pickle=False) as arrays:
                state = {k: arrays[k] for k in arrays.files}
            _require(_state_hash(state) == meta['state_sha256'], 'Replay checkpoint parameters differ')
            checkpoints[meta['path']] = state
    key = sha(encoded({'runs': runs, 'rate': rate, 'inputs': inputs, 'checkpoints': hashes,
        'candidate_rows': comparison['candidate_rows'],
        'references': {k:comparison[k] for k in ('control_rows', 'rule_rows', 'cp_rows')},
        'source_identity': comparison['source_identity'], 'verifier': sha(Path(__file__).read_bytes()),
        'actor_source': sha(Path(inspect.getfile(actor_class)).read_bytes())}))
    check_budget()
    if key in _VERIFIED:
        return
    _verify_references(reference, comparison, validation, check_budget)
    for run in runs:
        actor = actor_class(seed=run['seed'], hidden_size=16)
        _require(_same_state(actor.state_dict(), checkpoints[run['checkpoints']['initial']['path']]),
                 'Replay seed initialization differs')
        _require(len(run['logs']) == 64 and [c['episode'] for c in run['interval_checkpoints']] == [0,16,32,48,64],
                 'Replay training/checkpoint denominator differs')
        states = {0: actor.state_dict()}
        for ep, log in enumerate(run['logs'], 1):
            check_budget()
            index, seed = (ep-1)%8, (run['seed']+ep)%2**32
            _require((log['episode'], log['training_index'], log['seed'], log['instance_identity']) ==
                (ep, index, seed, inputs['training_base_identities'][index]), 'Replay training order/seed differs')
            state, actions, rewards, tt, update = _replay_episode(actor, train[index], run['mode'], seed, rate, check_budget)
            # Native trainer tuples and JSON-restored lists describe the same trajectory.
            _require(list(log['actions']) == actions and list(log['rewards']) == rewards and log['total_tardiness'] == tt
                and math.isclose(log['total_reward'], math.fsum(rewards), abs_tol=1e-12),
                'Replay training actions/rewards differ')
            _require(set(log['update']) == set(update) and type(log['update']['changed']) is bool
                and log['update']['changed'] == update['changed'] and log['update']['samples'] == 6
                and all(type(log['update'][k]) in (int,float) and math.isfinite(log['update'][k])
                        and math.isclose(log['update'][k], update[k], rel_tol=1e-11, abs_tol=1e-13)
                        for k in ('loss', 'gradient_norm', 'applied_gradient_norm')),
                'Replay gradient/update evidence differs')
            actor = actor_class.from_state(state)
            if ep % 16 == 0:
                states[ep] = state
        for entry in run['interval_checkpoints']:
            _require(_same_state(states[entry['episode']], checkpoints[entry['current']['path']])
                and _same_state(states[entry['selected']['episode']], checkpoints[entry['selected']['path']]),
                'Replay interval parameter state differs')
        _require(_same_state(states[64], checkpoints[run['checkpoints']['final']['path']])
            and _same_state(states[run['selected_episode']], checkpoints[run['checkpoints']['selected']['path']]),
            'Replay final/selected parameter state differs')
        _verify_validation(run, validation, inputs['validation_base_identities'], checkpoints,
                           comparison['candidate_rows'], actor_class, check_budget)
    check_budget()
    _VERIFIED[key] = True
    while len(_VERIFIED) > 8:
        _VERIFIED.popitem(last=False)
