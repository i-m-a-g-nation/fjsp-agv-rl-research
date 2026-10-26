"""Read-only diagnosis of an archived policy on its declared validation split.

Probe/CP subtrees are skipped at JSON boundaries without decoding them. The
original actor, exact integer-clock environment, EDD rule and G1 checker perform
all inference; this module supplies neither training targets nor policy updates.
"""

from collections import Counter
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
import time
from typing import Callable

import numpy as np

from src.graduation.data import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.metrics import calculate_total_tardiness
from src.graduation.neural_policy import MaskedMLP
from src.graduation.rl_environment import MAINTENANCE_OFFSET, MAX_MACHINES, ParallelMaintenanceEnv
from src.graduation.rules import _priority_action
from src.graduation.state_encoding import encode_construction_observation


ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_TRAINER = 'src/graduation/policy_training.py'
REQUIRED_SOURCES = tuple('src/graduation/' + name + '.py' for name in (
    'data', 'result', 'metrics', 'feasibility', '_production', 'rl_environment',
    'rules', 'state_encoding', 'neural_policy',
)) + ('src/scheduling/encoding.py', 'src/scheduling/feasibility.py', 'src/data/instance.py')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _path_inside(root, relative):
    _require(type(relative) is str and relative and '\\' not in relative
             and not PureWindowsPath(relative).drive
             and all(part not in ('', '.', '..') for part in relative.split('/')),
             'Artifact/source path must be a normalized relative path')
    path = (root / relative).resolve()
    _require(path.is_relative_to(root), 'Artifact/source path escapes its archive/root')
    return path


def _raw_fields(source, names, budget):
    """Decode object keys only; skip unwanted values without JSON-decoding them."""
    decoder = json.JSONDecoder()

    def whitespace(index):
        while index < len(source) and source[index].isspace():
            index += 1
        return index

    def skip(index):
        start = index
        stack, quoted, escaped = [], False, False
        while index < len(source):
            if (index - start) % 4096 == 0:
                budget()
            char = source[index]
            if quoted:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif char == '"':
                    quoted = False
                    if not stack and source[start] == '"':
                        return index + 1
            elif char == '"':
                quoted = True
            elif char in '[{':
                stack.append(char)
            elif char in ']}':
                if not stack:
                    return index
                _require(stack.pop() == ('[' if char == ']' else '{'), 'Malformed JSON boundary')
                if not stack:
                    return index + 1
            elif char == ',' and not stack:
                return index
            index += 1
        _require(not stack and not quoted and index > start, 'Incomplete JSON value')
        return index

    result, seen = {}, set()
    index = whitespace(0)
    _require(index < len(source) and source[index] == '{', 'Expected a JSON object')
    index = whitespace(index + 1)
    while index < len(source) and source[index] != '}':
        budget()
        key, end = decoder.raw_decode(source, index)
        _require(type(key) is str and key not in seen, 'Duplicate/nonstring JSON key')
        seen.add(key)
        index = whitespace(end)
        _require(index < len(source) and source[index] == ':', 'Malformed JSON object')
        start = whitespace(index + 1)
        _require(start < len(source), 'Incomplete JSON object')
        end = skip(start)
        if key in names:
            result[key] = source[start:end]
        index = whitespace(end)
        _require(index < len(source) and source[index] in ',}', 'Malformed JSON object')
        if source[index] == '}':
            break
        index = whitespace(index + 1)
        _require(index < len(source) and source[index] != '}', 'Trailing JSON comma')
    _require(index < len(source) and source[index] == '}'
             and whitespace(index + 1) == len(source), 'Malformed JSON object end')
    _require(names <= result.keys(), 'Missing required archive JSON fields')
    return result


def _decode(raw):
    def refuse(value):
        raise ValueError('Nonfinite JSON number')
    return json.loads(raw, parse_constant=refuse)


def _instances(rows, maximum, budget):
    _require(type(rows) is list and 1 <= len(rows) <= maximum, 'Invalid bounded archive split')
    result, identities = [], []
    for row in rows:
        budget()
        raw = row['input']
        _require(_sha(_encoded(raw)) == row['input_sha256'], 'Split input hash mismatch')
        data = ParallelMaintenanceInstance(tuple(ProductionTask(**v) for v in raw['tasks']),
            raw['num_machines'], tuple(MaintenanceRequirement(**v) for v in raw['maintenance']))
        identity = _sha(json.dumps([[t.processing_time, t.due_date] for t in data.tasks],
                                   separators=(',', ':')).encode('utf-8'))
        _require(identity == row['base_instance_identity'], 'Split base identity hash mismatch')
        _require(_integer(row['seed']), 'Split seed must be an integer')
        # The original environment validates the complete supported numeric domain.
        ParallelMaintenanceEnv(data, mode='fixed')
        ParallelMaintenanceEnv(data, mode='joint')
        result.append(data)
        identities.append(identity)
    _require(len(set(identities)) == len(identities), 'Duplicate split base identity')
    return result, identities


def _state_hash(state):
    digest = hashlib.sha256()
    for name in sorted(state):
        array = state[name]
        digest.update(_encoded({'name': name, 'dtype': array.dtype.str, 'shape': array.shape}))
        digest.update(array.tobytes(order='C'))
    return digest.hexdigest()


def _checked(env, data, mode, rewards, budget):
    budget()
    result = env.get_result()
    accepted, issues = check_parallel_maintenance_feasibility(result, data, mode=mode)
    _require(accepted, f'Original G1 rejected validation plan: {issues}')
    tardiness = calculate_total_tardiness(data, result)
    _require(result.total_tardiness == tardiness, 'Independent validation tardiness differs')
    _require(math.isclose(math.fsum(rewards), -tardiness / 100, rel_tol=1e-12, abs_tol=1e-12),
             'Validation replay return differs from original reward')
    return int(tardiness)


def _continuation(data, mode, prefix, budget):
    env, actions, rewards = ParallelMaintenanceEnv(data, mode=mode), [], []
    expected = len(data.tasks) + data.num_machines
    for index in range(expected):
        budget()
        legal = [a for a, valid in enumerate(env.action_masks()) if valid]
        action = prefix[index] if index < len(prefix) else _priority_action(env, legal, 'EDD')
        _require(type(action) is int and action in legal, 'Illegal validation prefix/EDD action')
        step = env.step(action)
        _require(not step.truncated and step.terminated == (index == expected - 1),
                 'Prefix replay did not terminate at its complete bound')
        actions.append(action)
        rewards.append(step.reward)
    return _checked(env, data, mode, rewards, budget), actions


def _divergence(action, edd):
    if action == edd:
        return 'same'
    if action < MAINTENANCE_OFFSET and edd < MAINTENANCE_OFFSET:
        return 'production_order' if action // MAX_MACHINES != edd // MAX_MACHINES else 'production_assignment'
    if action >= MAINTENANCE_OFFSET and edd >= MAINTENANCE_OFFSET:
        return 'maintenance_machine'
    return 'production_vs_maintenance'


def _training_diagnostics(run, data, identities, budget):
    logs = run['logs']
    _require(type(logs) is list and 1 <= len(logs) <= 64
             and run['episodes_completed'] == len(logs), 'Incomplete bounded training logs')
    norms, returns, coefficients, steps = [], [], [], 0
    for index, log in enumerate(logs):
        budget()
        train_index = log['training_index']
        _require(_integer(train_index) and train_index < len(data)
                 and train_index == index % len(data), 'Training log split order mismatch')
        count = len(data[train_index].tasks) + data[train_index].num_machines
        _require(log['episode'] == index + 1 and len(log['actions']) == count
                 and len(log['rewards']) == count and log['update']['samples'] == count,
                 'Training log incomplete episode/sample count')
        _require(log['instance_identity'] == identities[train_index], 'Training log identity mismatch')
        _require(all(_finite(r) and r <= 0 for r in log['rewards'])
                 and _finite(log['total_reward']) and _integer(log['total_tardiness']),
                 'Invalid original training rewards/tardiness')
        _require(math.isclose(math.fsum(log['rewards']), log['total_reward'], abs_tol=1e-12)
                 and math.isclose(log['total_reward'], -log['total_tardiness']/100, abs_tol=1e-12),
                 'Training log reward/tardiness mismatch')
        norm, applied = log['update']['gradient_norm'], log['update']['applied_gradient_norm']
        _require(_finite(norm) and norm >= 0 and _finite(applied)
                 and math.isclose(applied, min(norm, 1.), rel_tol=1e-12, abs_tol=1e-12)
                 and type(log['update']['changed']) is bool, 'Invalid training gradient diagnostics')
        steps += count
        norms.append(norm)
        returns.append(log['total_reward'])
        coefficients.extend(math.fsum(log['rewards'][k:]) for k in range(count))
    _require(run['training_steps'] == steps, 'Training log step count mismatch')
    return {'episodes': len(logs), 'changed_updates': sum(x['update']['changed'] for x in logs),
        'clip_count': sum(x > 1. for x in norms), 'gradient_norm_min': min(norms),
        'gradient_norm_mean': math.fsum(norms)/len(norms), 'gradient_norm_max': max(norms),
        'applied_gradient_norm_max': max(x['update']['applied_gradient_norm'] for x in logs),
        'return_min': min(returns), 'return_mean': math.fsum(returns)/len(returns),
        'return_max': max(returns), 'zero_episode_returns': sum(x == 0 for x in returns),
        'reward_to_go_negative': sum(x < 0 for x in coefficients),
        'reward_to_go_zero': sum(x == 0 for x in coefficients),
        'reward_to_go_positive': sum(x > 0 for x in coefficients)}


def _summary(validation):
    states = [s for v in validation for s in v['states']]
    flexible = [s for s in states if s['legal_count'] > 1]
    prefixes = [p for v in validation for p in v['prefix_EDD_continuations']]
    interior = [p for v in validation for p in v['prefix_EDD_continuations']
                if 0 < p['prefix_length'] < len(v['greedy_actions'])]
    mean = lambda items: math.fsum(items)/len(items) if items else None
    report = {'action_agreement': sum(s['divergence'] == 'same' for s in states), 'states': len(states),
        'flexible_action_agreement': sum(s['divergence'] == 'same' for s in flexible),
        'flexible_states': len(flexible), 'divergence_counts': dict(Counter(s['divergence'] for s in states)),
        'mean_probability_EDD': mean([s['probability_EDD'] for s in states]),
        'flexible_mean_probability_EDD': mean([s['probability_EDD'] for s in flexible]),
        'flexible_uniform_probability_EDD': mean([s['probability_uniform_EDD'] for s in flexible]),
        'greedy_mean_TT': mean([v['greedy_total_tardiness'] for v in validation]),
        'EDD_mean_TT': mean([v['EDD_total_tardiness'] for v in validation]),
        'selected_greedy_G1_accepted': len(validation), 'prefix_continuation_G1_accepted': len(prefixes)}
    for name, values, field in (('prefix', prefixes, 'delta_vs_greedy'),
                                ('interior_prefix', interior, 'delta_vs_greedy'),
                                ('validation_vs_EDD', validation, 'delta_vs_EDD')):
        for sign, predicate in (('improves', lambda x: x < 0), ('equal', lambda x: x == 0),
                                ('worse', lambda x: x > 0)):
            report[name + '_TT_' + sign] = sum(predicate(v[field]) for v in values)
    return report


def diagnose_validation(archive_dir: Path, *, check_budget: Callable[[], None] | None = None) -> dict:
    """Verify a native archive, then replay only selected validation trajectories.

    This function never writes or updates a model. A caller deadline propagates
    immediately; there is also a 120 second internal cap. No partial diagnosis is
    returned as accepted. The archived trainer hash remains historical because
    inference depends only on the unchanged actor/core source hashes.
    """
    _require(check_budget is None or callable(check_budget), 'check_budget must be callable or None')
    started = time.monotonic()

    def budget():
        if time.monotonic() - started >= 120:
            raise TimeoutError('Validation diagnostic exceeded its 120 second budget')
        if check_budget is not None:
            check_budget()

    budget()
    archive = Path(archive_dir).resolve()
    manifest = {key: _decode(raw) for key, raw in _raw_fields(
        _path_inside(archive, 'manifest.json').read_text(encoding='utf-8-sig'),
        {'artifacts', 'source_hashes', 'data_sha256', 'config_sha256'}, budget).items()}
    artifacts = manifest['artifacts']
    _require(type(artifacts) is dict and 'results.json' in artifacts, 'Missing native results artifact')
    for relative, digest in artifacts.items():
        budget()
        path = _path_inside(archive, relative)
        _require(path.is_file(), f'Missing native artifact: {relative}')
        _require(_sha(path.read_bytes()) == digest, f'Native artifact hash mismatch: {relative}')
    sources = manifest['source_hashes']
    _require(type(sources) is dict and set(REQUIRED_SOURCES) <= sources.keys(),
             'Missing original actor/core source hashes')
    current_sources = {}
    for relative, digest in sources.items():
        budget()
        if relative != HISTORICAL_TRAINER:
            _require(_sha(_path_inside(ROOT, relative).read_bytes()) == digest,
                     f'Original source hash mismatch: {relative}')
            current_sources[relative] = digest
    raw = _raw_fields(_path_inside(archive, 'results.json').read_text(encoding='utf-8-sig'),
                      {'training_runs', 'splits'}, budget)
    runs = _decode(raw['training_runs'])
    split_raw = _raw_fields(raw['splits'], {'training', 'validation'}, budget)
    splits = {key: _decode(value) for key, value in split_raw.items()}
    training, training_ids = _instances(splits['training'], 16, budget)
    validation, validation_ids = _instances(splits['validation'], 4, budget)
    _require(not set(training_ids) & set(validation_ids), 'Training/validation identity overlap')
    _require(type(runs) is list and 1 <= len(runs) <= 4, 'Invalid bounded archived training runs')
    report = {'version': 1, 'kind': 'validation_only_policy_diagnosis',
        'probe_evaluated': False, 'cp_evaluated': False,
        'hash_checks': {'archived_artifacts': len(artifacts), 'all_archived_artifacts_match': True,
            'current_original_sources_except_trainer': len(current_sources),
            'all_current_original_sources_match': True,
            'excluded_current_source_hashes': [HISTORICAL_TRAINER],
            'historical_trainer_source_sha256': sources.get(HISTORICAL_TRAINER),
            'checkpoint_safety': 'allow_pickle=False; finite float64 actor parameters'},
        'limitation': 'Validation development diagnosis; no causal or scientific superiority claim.', 'runs': []}
    identities = set()
    for run in runs:
        budget()
        mode, seed = run['mode'], run['seed']
        _require(mode in ('fixed', 'joint') and _integer(seed) and seed < 2**32
                 and (mode, seed) not in identities and run['status'] == 'COMPLETED',
                 'Invalid/incomplete archived run')
        identities.add((mode, seed))
        metadata = run['checkpoints']['selected']
        path = _path_inside(archive, metadata['path'])
        meta_relative = path.with_suffix('.json').relative_to(archive).as_posix()
        _require(metadata['path'] in artifacts and meta_relative in artifacts,
                 'Missing selected checkpoint/metadata artifact')
        _require(_sha(path.read_bytes()) == metadata['sha256'], 'Selected checkpoint file hash mismatch')
        _require(_decode(path.with_suffix('.json').read_text(encoding='utf-8-sig')) == metadata,
                 'Selected checkpoint metadata differs from training run')
        _require(metadata['source_hashes'] == sources, 'Selected checkpoint source hashes differ')
        _require(metadata['data_sha256'] == manifest['data_sha256']
                 and metadata['config_sha256'] == manifest['config_sha256'],
                 'Selected checkpoint data/config hashes differ')
        _require(_integer(run['selected_episode']) and run['selected_episode'] <= run['episodes_completed']
                 and metadata['episode'] == run['selected_episode'], 'Selected checkpoint episode mismatch')
        with np.load(path, allow_pickle=False) as saved:
            actor = MaskedMLP.from_state({name: saved[name] for name in saved.files})
        _require(_state_hash(actor.state_dict()) == metadata['state_sha256'], 'Selected checkpoint state hash mismatch')
        stats = _training_diagnostics(run, training, training_ids, budget)
        history = run['validation_history']
        _require(type(history) is list and history and history[0]['episode'] == 0
                 and all(_finite(v['validation_mean_tardiness']) for v in history), 'Invalid validation history')
        selected = min(history, key=lambda v: (v['validation_mean_tardiness'], v['episode']))
        _require(selected['episode'] == run['selected_episode']
                 and len(selected['validation_rows']) == len(validation), 'Validation checkpoint selection mismatch')
        rr = {'mode': mode, 'seed': seed, 'selected_episode': run['selected_episode'],
            'selected_checkpoint_sha256': metadata['sha256'], 'training_diagnostics': stats,
            'validation_history': [[v['episode'], v['validation_mean_tardiness']] for v in history],
            'validation': []}
        for index, data in enumerate(validation):
            budget()
            env, actions, rewards, states = ParallelMaintenanceEnv(data, mode=mode), [], [], []
            rng = np.random.default_rng(seed)
            expected = len(data.tasks) + data.num_machines
            for step_index in range(expected):
                budget()
                legal = [a for a, valid in enumerate(env.action_masks()) if valid]
                edd = _priority_action(env, legal, 'EDD')
                encoded = encode_construction_observation(env.observe())
                probabilities = actor.probabilities(encoded)
                action = actor.select_action(encoded, rng=rng, deterministic=True)
                _require(type(action) is int and action in legal and edd in legal,
                         'Selected actor/EDD produced an illegal validation action')
                _require(all(_finite(p) and p >= 0 for p in probabilities)
                         and math.isclose(math.fsum(probabilities), 1., abs_tol=1e-12)
                         and all(p == 0 for a, p in enumerate(probabilities) if a not in legal),
                         'Actor probabilities violate the original mask')
                states.append({'step': step_index, 'prefix': actions.copy(),
                    'machine_tails': list(env.machine_tails), 'legal_count': len(legal),
                    'greedy_action': action, 'legal_EDD_action': edd,
                    'divergence': _divergence(action, edd), 'probability_EDD': probabilities[edd],
                    'probability_greedy': probabilities[action], 'probability_uniform_EDD': 1/len(legal)})
                transition = env.step(action)
                _require(not transition.truncated and transition.terminated == (step_index == expected - 1),
                         'Greedy validation did not terminate at its complete bound')
                actions.append(action)
                rewards.append(transition.reward)
            tardiness = _checked(env, data, mode, rewards, budget)
            saved_row = selected['validation_rows'][index]
            _require(saved_row['validation_index'] == index and saved_row['actions'] == actions
                     and saved_row['total_tardiness'] == tardiness,
                     'Selected checkpoint replay differs from saved validation')
            _require(saved_row['instance_identity'] == validation_ids[index],
                     'Saved validation identity differs from its split')
            _require(saved_row['rewards'] == rewards and _finite(saved_row['total_reward'])
                     and math.isclose(saved_row['total_reward'], math.fsum(rewards), abs_tol=1e-12),
                     'Saved validation rewards differ from original replay')
            prefixes = []
            for length in range(expected + 1):
                budget()
                tt, path_actions = _continuation(data, mode, actions[:length], budget)
                prefixes.append({'prefix_length': length, 'prefix': actions[:length],
                    'total_tardiness': tt, 'delta_vs_greedy': tt - tardiness,
                    'actions': path_actions, 'G1_accepted': True})
            rr['validation'].append({'validation_index': index,
                'validation_seed': splits['validation'][index]['seed'], 'greedy_actions': actions,
                'EDD_actions': prefixes[0]['actions'], 'greedy_total_tardiness': tardiness,
                'EDD_total_tardiness': prefixes[0]['total_tardiness'],
                'delta_vs_EDD': tardiness - prefixes[0]['total_tardiness'], 'G1_accepted': True,
                'states': states, 'prefix_EDD_continuations': prefixes})
        _require(math.isclose(math.fsum(v['greedy_total_tardiness'] for v in rr['validation'])/len(validation),
                              selected['validation_mean_tardiness'], abs_tol=1e-12),
                 'Selected validation mean differs from replay')
        rr['summary'] = _summary(rr['validation'])
        report['runs'].append(rr)
    report['aggregate'] = _summary([v for r in report['runs'] for v in r['validation']])
    report['aggregate']['training_episodes'] = sum(r['training_diagnostics']['episodes'] for r in report['runs'])
    report['aggregate']['clip_count'] = sum(r['training_diagnostics']['clip_count'] for r in report['runs'])
    for sign in ('negative', 'zero', 'positive'):
        key = 'reward_to_go_' + sign
        report['aggregate'][key] = sum(r['training_diagnostics'][key] for r in report['runs'])
    budget()
    return report
