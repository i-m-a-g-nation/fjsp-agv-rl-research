"""Frozen validation-only identifier sensitivity; no training or split selection.

Distributions are compared at the same physical states by replaying mapped
original actions. Separate complete greedy plans describe behavioral effects.
Only selected ``none`` actors and validation inputs/rows are JSON-decoded.
"""

from dataclasses import asdict, replace
import math
from pathlib import Path

import numpy as np

from src.graduation.data import ParallelMaintenanceInstance
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.metrics import calculate_total_tardiness
from src.graduation.neural_policy import MaskedMLP, policy_features
from src.graduation.rl_environment import (
    ACTION_COUNT, MAINTENANCE_OFFSET, MAX_MACHINES, MAX_TASKS, ParallelMaintenanceEnv,
)
from src.graduation.state_encoding import encode_construction_observation
from src.graduation.validation_diagnostics import (
    REQUIRED_SOURCES, ROOT, _decode, _encoded, _instances, _path_inside, _raw_fields,
    _require, _sha, _state_hash,
)

TOLERANCE = 1e-10
PERMUTATIONS = ('identity', 'jobs_reverse', 'machines_reverse', 'both_reverse')
EXPECTED_RUNS = {(mode, seed) for mode in ('fixed', 'joint') for seed in (17, 29)}
EXPECTED_CASES = {(mode, seed, index) for mode, seed in EXPECTED_RUNS for index in range(4)}


def _objects(raw, budget, maximum):
    """Yield opaque object slices from a bounded array, without decoding values."""
    source = raw.strip()
    _require(source.startswith('[') and source.endswith(']'), 'Expected archive array')
    start, depth, quoted, escaped, count = 1, 0, False, False, 0
    for index in range(1, len(source) - 1):
        if index % 4096 == 0:
            budget()
        char = source[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '[{':
            depth += 1
        elif char in ']}':
            depth -= 1
            _require(depth >= 0, 'Malformed archive array')
        elif char == ',' and depth == 0:
            count += 1
            _require(count <= maximum, 'Archive array exceeds expected denominator')
            yield source[start:index].strip()
            start = index + 1
    _require(not quoted and depth == 0, 'Incomplete archive array')
    last = source[start:-1].strip()
    _require(bool(last) and count < maximum, 'Invalid archive array denominator')
    yield last


def _fields(raw, names, budget):
    return {key: _decode(value) for key, value in _raw_fields(raw, set(names), budget).items()}


def _read(archive, budget):
    manifest_bytes = _path_inside(archive, 'manifest.json').read_bytes()
    manifest = _fields(manifest_bytes.decode('utf-8-sig'), (
        'artifacts', 'source_hashes', 'data_sha256', 'config_sha256', 'status', 'purpose', 'decisions'), budget)
    _require(manifest['status'] == 'COMPLETED' and manifest['purpose'] ==
             'validation_only_return_baseline_iteration', 'Expected completed exp026 archive')
    _require(all(manifest['decisions'][mode]['status'] == 'DECIDED' and
                 manifest['decisions'][mode]['selected_method'] == 'none' for mode in ('fixed', 'joint')),
             'Frozen selected method must remain none in both modes')
    artifacts, sources = manifest['artifacts'], manifest['source_hashes']
    _require(type(artifacts) is dict and 'results.json' in artifacts, 'Missing results artifact')
    for relative, digest in artifacts.items():
        budget()
        _require(_sha(_path_inside(archive, relative).read_bytes()) == digest,
                 'Archived artifact hash mismatch: ' + relative)
    required = set(REQUIRED_SOURCES) | {'src/graduation/policy_training.py', 'src/graduation/solver.py',
        'src/graduation/return_baseline.py', 'src/graduation/validation_diagnostics.py',
        'experiments/exp_025_neural_policy_pilot.py', 'experiments/exp_026_validation_iteration.py'}
    _require(type(sources) is dict and required <= sources.keys(), 'Missing original source hashes')
    for relative, digest in sources.items():
        budget()
        _require(_sha(_path_inside(ROOT, relative).read_bytes()) == digest,
                 'Current original source hash mismatch: ' + relative)
    raw = _raw_fields(_path_inside(archive, 'results.json').read_text(encoding='utf-8-sig'),
                      {'training_runs', 'splits', 'validation_rows'}, budget)
    validation_raw = _raw_fields(raw['splits'], {'validation'}, budget)['validation']
    validation_rows = _decode(validation_raw)
    validation, identities = _instances(validation_rows, 4, budget)
    _require(len(validation) == 4, 'Expected complete frozen validation4 denominator')
    runs, rows = {}, {}
    for item in _objects(raw['training_runs'], budget, 8):
        if _fields(item, ('method',), budget)['method'] != 'none':
            continue
        run = _fields(item, ('mode', 'seed', 'status', 'selected_episode', 'episodes_completed'), budget)
        selected_raw = _raw_fields(_raw_fields(item, {'checkpoints'}, budget)['checkpoints'],
                                   {'selected'}, budget)['selected']
        run['selected'] = _decode(selected_raw)
        key = run['mode'], run['seed']
        _require(key in EXPECTED_RUNS and key not in runs and run['status'] == 'COMPLETED',
                 'Invalid/duplicate/incomplete selected actor denominator')
        runs[key] = run
    _require(runs.keys() == EXPECTED_RUNS, 'Missing selected actor denominator')
    for item in _objects(raw['validation_rows'], budget, 80):
        if _fields(item, ('method',), budget)['method'] != 'none':
            continue
        row = _fields(item, ('mode', 'seed', 'validation_index', 'instance_identity', 'actions',
                            'transitions', 'payload', 'validation_status', 'schedule_accepted'), budget)
        key = row['mode'], row['seed'], row['validation_index']
        _require(key in EXPECTED_CASES and key not in rows and row['validation_status'] == 'PASS'
                 and row['schedule_accepted'] is True, 'Invalid selected validation denominator')
        _require(row['instance_identity'] == identities[key[2]], 'Validation identity differs from split')
        rows[key] = row
    _require(rows.keys() == EXPECTED_CASES, 'Missing selected validation denominator')
    return manifest, _sha(manifest_bytes), validation_rows, validation, runs, rows


def _actor(archive, manifest, run, budget):
    budget()
    metadata = run['selected']
    path = _path_inside(archive, metadata['path'])
    meta_relative = path.with_suffix('.json').relative_to(archive).as_posix()
    _require(manifest['artifacts'].get(metadata['path']) == metadata['sha256']
             and meta_relative in manifest['artifacts'], 'Missing selected checkpoint artifact binding')
    _require(_decode(path.with_suffix('.json').read_text(encoding='utf-8-sig')) == metadata,
             'Selected checkpoint metadata mismatch')
    _require(metadata['source_hashes'] == manifest['source_hashes'] and all(
        metadata[key] == manifest[key] for key in ('data_sha256', 'config_sha256')),
        'Selected checkpoint source/data/config hash mismatch')
    _require(type(run['selected_episode']) is int and 0 <= run['selected_episode'] <= run['episodes_completed']
             and metadata['episode'] == run['selected_episode'], 'Selected checkpoint episode mismatch')
    with np.load(path, allow_pickle=False) as saved:
        actor = MaskedMLP.from_state({key: saved[key] for key in saved.files})
    _require(_state_hash(actor.state_dict()) == metadata['state_sha256'], 'Selected checkpoint state hash mismatch')
    return actor


def _permutation(data, name):
    jobs = [len(data.tasks)-1-j if j < len(data.tasks) and name in ('jobs_reverse', 'both_reverse')
            else j for j in range(MAX_TASKS)]
    machines = [data.num_machines-1-m if m < data.num_machines and name in ('machines_reverse', 'both_reverse')
                else m for m in range(MAX_MACHINES)]
    actions = [jobs[j] * MAX_MACHINES + machines[m] for j in range(MAX_TASKS) for m in range(MAX_MACHINES)]
    actions += [MAINTENANCE_OFFSET + machines[m] for m in range(MAX_MACHINES)]
    _require(sorted(actions) == list(range(ACTION_COUNT)), 'Action relabeling is not bijective')
    relabeled = ParallelMaintenanceInstance(tuple(replace(t, job_id=jobs[t.job_id]) for t in data.tasks),
        data.num_machines, tuple(replace(m, machine_id=machines[m.machine_id]) for m in data.maintenance))
    return relabeled, jobs, machines, actions


def _probabilities(actor, observation):
    probabilities = actor.probabilities(encode_construction_observation(observation))
    _require(len(probabilities) == ACTION_COUNT and all(type(p) is float and math.isfinite(p) and p >= 0
        for p in probabilities) and math.isclose(math.fsum(probabilities), 1., abs_tol=1e-12)
        and all(p == 0 for p, legal in zip(probabilities, observation.action_mask) if not legal),
        'Actor distribution violates original masks/normalization')
    return probabilities


def _rollout(actor, data, mode, budget, prefix=None):
    env, actions, rewards, states = ParallelMaintenanceEnv(data, mode=mode), [], [], []
    expected = len(data.tasks) + data.num_machines
    for index in range(expected):
        budget()
        observation = env.observe()
        probabilities = _probabilities(actor, observation)
        action = int(np.argmax(probabilities)) if prefix is None else prefix[index]
        _require(type(action) is int and 0 <= action < ACTION_COUNT and observation.action_mask[action],
                 'Illegal mapped/greedy action')
        states.append((observation, probabilities, env.machine_tails))
        transition = env.step(action)
        _require(not transition.truncated and transition.terminated == (index == expected - 1),
                 'Incomplete original episode termination')
        actions.append(action)
        rewards.append(transition.reward)
    budget()
    result = env.get_result()
    accepted, issues = check_parallel_maintenance_feasibility(result, data, mode=mode)
    _require(accepted, f'Original G1 rejected permutation plan: {issues}')
    tardiness = calculate_total_tardiness(data, result)
    completion = {r.job_id: r.end for r in result.records}
    _require(tardiness == result.total_tardiness == sum(max(0, completion[t.job_id]-t.due_date) for t in data.tasks),
             'Independent total tardiness mismatch')
    _require(math.isclose(math.fsum(rewards), -tardiness / 100, abs_tol=1e-12, rel_tol=1e-12),
             'Original reward/TT mismatch')
    payload = {'records': sorted([asdict(r) for r in result.records], key=lambda r: r['job_id']),
        'maintenance_records': sorted([asdict(r) for r in result.maintenance_records], key=lambda r: r['machine_id']),
        'makespan': result.makespan, 'total_tardiness': tardiness}
    return {'actions': actions, 'rewards': rewards, 'payload': payload, 'G1_accepted': True,
            'plan_sha256': _sha(_encoded(payload))}, states


def _compare(original, mapped, jobs, machines, action_map, budget):
    states = []
    for index, ((a, p, tails), (b, q, relabeled_tails)) in enumerate(zip(original, mapped)):
        budget()
        _require((a.mode, a.status, a.steps, a.scale) == (b.mode, b.status, b.steps, b.scale)
            and all(a.task_features[j] == b.task_features[jobs[j]] for j in range(MAX_TASKS))
            and all(a.machine_features[m] == b.machine_features[machines[m]] for m in range(MAX_MACHINES))
            and all(tails[m] == relabeled_tails[machines[m]] for m in range(len(tails)))
            and all(a.action_mask[i] == b.action_mask[action_map[i]] for i in range(ACTION_COUNT)),
            'Mapped replay differs from the same physical/normalized state')
        back = [q[action_map[i]] for i in range(ACTION_COUNT)]
        errors = [abs(p[i] - back[i]) for i in range(ACTION_COUNT)]
        legal_count = sum(a.action_mask)
        uniform = [float(legal) / legal_count for legal in a.action_mask]
        uniform_back = [float(b.action_mask[action_map[i]]) / sum(b.action_mask) for i in range(ACTION_COUNT)]
        states.append({'step': index, 'same_physical_state': True, 'machine_tails': list(tails),
            'action_mask': list(a.action_mask), 'probabilities': list(p), 'mapped_probabilities': back,
            'max_probability_error': max(errors), 'l1_probability_error': math.fsum(errors),
            'sensitive': max(errors) > TOLERANCE,
            'uniform_max_error': max(abs(x-y) for x, y in zip(uniform, uniform_back)),
            'original_features_sha256': _sha(_encoded(policy_features(encode_construction_observation(a)))),
            'permuted_features_sha256': _sha(_encoded(policy_features(encode_construction_observation(b))))})
    return states


def diagnose_permutations(archive_dir, *, check_budget=None):
    """Return a JSON-safe, complete 16-original/64-permutation diagnostic report."""
    budget = check_budget if check_budget is not None else lambda: None
    budget()
    archive = Path(archive_dir).resolve()
    manifest, manifest_hash, validation_rows, validation, runs, saved_rows = _read(archive, budget)
    cases = []
    for (mode, seed), run in sorted(runs.items()):
        actor = _actor(archive, manifest, run, budget)
        state_hash = _state_hash(actor.state_dict())
        for index, data in enumerate(validation):
            original, original_states = _rollout(actor, data, mode, budget)
            saved = saved_rows[mode, seed, index]
            payload = saved['payload']
            _require(original['actions'] == saved['actions'] and original['rewards'] ==
                [t['reward'] for t in saved['transitions']] and all(original['payload'][key] ==
                (sorted(payload[key], key=lambda r: r['job_id' if key == 'records' else 'machine_id'])
                 if key in ('records', 'maintenance_records') else payload[key]) for key in original['payload']),
                'Saved validation plan/actions/reward differs from original replay')
            for name in PERMUTATIONS:
                transformed, jobs, machines, action_map = _permutation(data, name)
                mapped, mapped_states = _rollout(actor, transformed, mode, budget,
                    [action_map[a] for a in original['actions']])
                states = _compare(original_states, mapped_states, jobs, machines, action_map, budget)
                _require(all(s['uniform_max_error'] == 0 and (name != 'identity' or
                    s['max_probability_error'] == 0) for s in states), 'Uniform/identity control failed')
                greedy, _ = _rollout(actor, transformed, mode, budget)
                _require(mapped['payload']['total_tardiness'] == original['payload']['total_tardiness'],
                         'Mapped physical replay changed total tardiness')
                cases.append({'mode': mode, 'seed': seed, 'validation_index': index, 'permutation': name,
                    'instance_identity': saved['instance_identity'], 'input': asdict(transformed),
                    'original_input': validation_rows[index]['input'], 'checkpoint': run['selected'],
                    'job_map': jobs, 'machine_map': machines, 'action_map': action_map,
                    'original_actions': original['actions'], 'mapped_replay': mapped, 'greedy': greedy,
                    'states': states, 'max_probability_error': max(s['max_probability_error'] for s in states),
                    'l1_probability_error': math.fsum(s['l1_probability_error'] for s in states)})
        _require(_state_hash(actor.state_dict()) == state_hash, 'Frozen actor parameters changed')
    expected_states = 4 * 4 * sum(len(data.tasks) + data.num_machines for data in validation)
    count = sum(len(case['states']) for case in cases)
    _require(len(cases) == 64 and count == expected_states, 'Incomplete permutation/state denominator')
    sensitive = sum(state['sensitive'] for case in cases for state in case['states'])
    budget()
    return {'version': 1, 'kind': 'validation_only_permutation_diagnosis', 'status': 'COMPLETED',
        'research_status': 'not_achieved', 'probe_evaluated': False, 'final_test_evaluated': False,
        'training_performed': False, 'tolerance': TOLERANCE, 'sensitive_states': sensitive,
        'limitation': 'Reused validation and identifier reversals only; no statistical advantage or equivariance proof.',
        'hash_checks': {'all_archived_artifacts_match': True, 'all_current_original_sources_match': True,
            'archived_artifacts': len(manifest['artifacts']), 'current_original_sources': len(manifest['source_hashes']),
            'manifest_sha256': manifest_hash, 'results_sha256': manifest['artifacts']['results.json'],
            'validation_sha256': _sha(_encoded(validation_rows)), 'source_hashes': manifest['source_hashes']},
        'denominators': {'expected_original_cases': 16, 'original_cases': len(saved_rows),
            'expected_permutation_cases': 64, 'permutation_cases': len(cases),
            'expected_state_comparisons': expected_states, 'state_comparisons': count,
            'G1_accepted_greedy_plans': len(cases), 'G1_accepted_mapped_replay_plans': len(cases)},
        'aggregate': {'sensitive_states': sensitive, 'uniform_sensitive_states': sum(s['uniform_max_error'] > TOLERANCE
            for c in cases for s in c['states']), 'max_probability_error': max(c['max_probability_error'] for c in cases)},
        'cases': cases}
