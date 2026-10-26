"""Bounded NumPy REINFORCE engineering pilot; probe data is not a final G3 test."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

# The native CLI sets these before importing NumPy or any graduation policy.
NUMPY_PREIMPORTED = 'numpy' in sys.modules
THREAD_VARIABLES = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                    'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'BLIS_NUM_THREADS')
for _variable in THREAD_VARIABLES:
    os.environ[_variable] = '1'

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.graduation.data import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.metrics import calculate_total_tardiness
from src.graduation.rl_environment import ParallelMaintenanceEnv
from src.graduation.rules import run_maintenance_rule_episode
from src.graduation.solver import solve_parallel_maintenance
from src.graduation.state_encoding import encode_construction_observation

PURPOSE = 'masked_neural_reinforce_engineering_pilot'
LIMITATION = ('NumPy MLP/REINFORCE engineering baseline; no PPO or Transformer reproduction, '
              'innovation claim, guaranteed improvement or final research acceptance. '
              'Probe data is not the final G3 test; comparisons are within each maintenance mode.')
METHODS = ('initial', 'final', 'selected', 'EDD', 'SPT', 'Random')
MODES = ('fixed', 'joint')
TRAINING_SEEDS = (17, 29)
SEEDS = {'training': tuple(range(1001, 1009)), 'validation': tuple(range(2001, 2005)),
         'probe': tuple(range(3001, 3005))}
CERTIFICATE_FIELDS = ('solver_status', 'solver_objective_value', 'solver_objective_bound',
                      'solver_gap', 'solver_wall_time')
SOURCE_FILES = tuple('src/graduation/' + name + '.py' for name in
    ('data', 'result', 'metrics', 'feasibility', '_production', 'rl_environment', 'rules',
     'solver', 'state_encoding', 'neural_policy', 'policy_training')) + (
        'src/scheduling/encoding.py', 'src/scheduling/feasibility.py', 'src/data/instance.py',
        'experiments/exp_025_neural_policy_pilot.py')


class PilotBudgetExceeded(TimeoutError):
    """The shared active-time cap has expired; partial evidence remains on disk."""


def _encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _identity(data):
    return _sha(json.dumps([[task.processing_time, task.due_date] for task in data.tasks],
                           separators=(',', ':')).encode('utf-8'))


def _field_integer(seed, field, low, high):
    """Versioned independent SHA256 fields; rejection sampling avoids modulo bias."""
    width = high - low + 1
    limit = 2**256 - 2**256 % width
    counter = 0
    while True:
        raw = _encoded({'generator': 'neural-pilot-sha256-fields', 'version': 1,
                        'seed': seed, 'field': field, 'counter': counter})
        value = int.from_bytes(hashlib.sha256(raw).digest(), 'big')
        if value < limit:
            return low + value % width
        counter += 1


def build_splits():
    """Return frozen train8/validation4/probe4 inputs and full reproducible metadata."""
    splits = {}
    metadata = {'version': 1, 'purpose': 'engineering_probe_not_final_G3_test',
                'generator': 'neural-pilot-sha256-fields', 'work_definition': 'sum_processing_times'}
    seen = set()
    for name, seeds in SEEDS.items():
        instances, rows = [], []
        for seed in seeds:
            processing = [_field_integer(seed, f'task/{job}/processing_time', 1, 6) for job in range(4)]
            work = sum(processing)
            tasks = tuple(ProductionTask(job, value,
                _field_integer(seed, f'task/{job}/due_date', 0, work)) for job, value in enumerate(processing))
            maintenance = []
            for machine in range(2):
                duration = _field_integer(seed, f'machine/{machine}/duration', 1, 3)
                lower = _field_integer(seed, f'machine/{machine}/window_start', 0, work // 3)
                slack = max(1, work // 2)
                maintenance.append(MaintenanceRequirement(machine, duration, lower,
                    lower + duration + slack, lower + slack // 2))
            data = ParallelMaintenanceInstance(tasks, 2, tuple(maintenance))
            identity = _identity(data)
            if identity in seen:
                raise ValueError('Base processing/due-date tasks overlap across the declared splits')
            seen.add(identity)
            raw = asdict(data)
            rows.append({'seed': seed, 'stream_version': 1,
                'stream_identity': _sha(_encoded({'generator': metadata['generator'], 'version': 1, 'seed': seed})),
                'base_instance_identity': identity, 'total_work': work,
                'input': raw, 'input_sha256': _sha(_encoded(raw))})
            instances.append(data)
        splits[name], metadata[name] = tuple(instances), tuple(rows)
    splits['metadata'] = metadata
    return splits


def _safe(value):
    """Retain rejected evidence without serializing exception text or object reprs."""
    if type(value) is float and not math.isfinite(value):
        return {'invalid_float': 'nan' if math.isnan(value) else ('inf' if value > 0 else '-inf')}
    if isinstance(value, np.ndarray):
        return _safe(value.tolist())
    if isinstance(value, np.generic):
        return _safe(value.item())
    if isinstance(value, dict):
        if any(type(key) is not str for key in value):
            return {'invalid_mapping': [{'key_type': type(key).__name__, 'value': _safe(item)}
                                        for key, item in value.items()]}
        return {key: _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    return {'invalid_type': type(value).__name__}


def _write_json(path, value):
    path.write_bytes(_encoded(_safe(value)))


def _state_hash(state):
    digest = hashlib.sha256()
    for name in sorted(state):
        array = state[name]
        digest.update(_encoded({'name': name, 'dtype': array.dtype.str, 'shape': array.shape}))
        digest.update(array.tobytes(order='C'))
    return digest.hexdigest()


def load_checkpoint(path, *, expected_sha256=None):
    """Load validated float64 arrays only; never enable NumPy pickle loading."""
    from src.graduation.neural_policy import MaskedMLP
    path = Path(path)
    if expected_sha256 is not None and _sha(path.read_bytes()) != expected_sha256:
        raise ValueError('Checkpoint file hash differs from its manifest')
    with np.load(path, allow_pickle=False) as archive:
        state = {key: archive[key] for key in archive.files}
    return MaskedMLP.from_state(state)


def _save_checkpoint(output, relative, state, *, episode, source_hashes, data_hash, config_hash):
    from src.graduation.neural_policy import MaskedMLP
    checked = MaskedMLP.from_state(state).state_dict()
    path = output / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **checked)
    file_hash, state_hash = _sha(path.read_bytes()), _state_hash(checked)
    restored = load_checkpoint(path, expected_sha256=file_hash).state_dict()
    if any(not np.array_equal(checked[key], restored[key]) for key in checked):
        raise ValueError('Checkpoint reload changed parameters')
    metadata = {'path': relative, 'sha256': file_hash, 'state_sha256': state_hash,
        'episode': episode, 'trained': episode > 0, 'label': 'trained' if episode > 0 else 'untrained',
        'format': 'numpy_npz_float64_no_pickle', 'source_hashes': source_hashes,
        'data_sha256': data_hash, 'config_sha256': config_hash}
    _write_json(path.with_suffix('.json'), metadata)
    return metadata


def _plan_payload(result, data, mode, check):
    check['accepted'], issues = check_parallel_maintenance_feasibility(result, data, mode=mode)
    check['issues'] = [asdict(issue) for issue in issues]
    if not check['accepted']:
        raise ValueError('Original G1 checker rejected the plan')
    computed = calculate_total_tardiness(data, result)
    completion = {record.job_id: record.end for record in result.records}
    independent = sum(max(0, completion[task.job_id] - task.due_date) for task in data.tasks)
    if result.total_tardiness != computed or computed != independent:
        raise ValueError('Total tardiness disagrees with independent recomputation')
    return {'total_tardiness': independent, 'makespan': result.makespan,
        'records': sorted([asdict(record) for record in result.records], key=lambda row: row['job_id']),
        'maintenance_records': sorted([asdict(record) for record in result.maintenance_records],
                                      key=lambda row: row['machine_id']),
        **{field: getattr(result, field) for field in CERTIFICATE_FIELDS}}


def _plan_hash(payload):
    return _sha(_encoded({key: payload[key] for key in
        ('total_tardiness', 'makespan', 'records', 'maintenance_records')}))


def _checked_episode(row, episode, data, *, actor, check_budget):
    """Replay every saved action against original masks, clocks, metrics and reward."""
    actions = episode.actions
    row['actions'] = _safe(actions)
    if type(actions) is not tuple or len(actions) != len(data.tasks) + data.num_machines:
        raise ValueError('An accepted episode needs exactly n+m actions')
    env = ParallelMaintenanceEnv(data, mode=row['mode'])
    rewards = []
    rng = np.random.default_rng(row['seed'])
    for action in actions:
        check_budget()
        mask = env.action_masks()
        transition = {'action': action, 'action_mask': mask, 'probabilities': None, 'reward': None}
        row['transitions'].append(transition)
        if type(action) is not int or not 0 <= action < 100 or not mask[action]:
            raise ValueError('Episode contains an illegal action')
        if actor is not None:
            encoded = encode_construction_observation(env.observe())
            probabilities = actor.probabilities(encoded)
            transition['probabilities'] = probabilities
            if actor.select_action(encoded, rng=rng, deterministic=True) != action:
                raise ValueError('Reloaded checkpoint does not predict the saved greedy action')
        step = env.step(action)
        transition['reward'] = step.reward
        rewards.append(step.reward)
        if step.truncated or step.terminated != (len(rewards) == len(actions)):
            raise ValueError('Episode did not terminate at the declared complete bound')
    payload = _plan_payload(episode.result, data, row['mode'], row['check'])
    replay = _plan_payload(env.get_result(), data, row['mode'], row['replay_check'])
    if _encoded(payload) != _encoded(replay):
        raise ValueError('Saved plan differs from independent action replay')
    if any(payload[field] is not None for field in CERTIFICATE_FIELDS):
        raise ValueError('Policy and rule plans cannot claim solver certificates')
    if (type(episode.total_reward) is not float or not math.isfinite(episode.total_reward)
            or not math.isclose(episode.total_reward, sum(rewards), rel_tol=0, abs_tol=1e-12)
            or not math.isclose(episode.total_reward, -payload['total_tardiness']/100, rel_tol=0, abs_tol=1e-12)):
        raise ValueError('Complete episode return differs from negative tardiness / 100')
    if actor is not None and tuple(rewards) != episode.rewards:
        raise ValueError('Policy rewards differ from independent replay')
    payload.update(actions=list(actions), rewards=rewards, total_reward=episode.total_reward)
    row['payload'] = payload
    row['plan_sha256'] = _plan_hash(payload)
    check_budget()


def _digest_outcome(evidence):
    """Keep deterministic outcomes separate from paths, time, runtime and git."""
    runs = []
    for run in evidence['training_runs']:
        runs.append({key: value for key, value in run.items()
            if key not in ('progress_log', 'checkpoints', 'interval_checkpoints')})
        runs[-1]['checkpoint_states'] = {key: value['state_sha256'] for key, value in run['checkpoints'].items()}
    cp_rows = []
    for row in evidence['cp_rows']:
        stable = dict(row)
        stable.pop('solver_wall_time', None)
        if stable['payload'] is not None:
            stable['payload'] = dict(stable['payload'])
            stable['payload'].pop('solver_wall_time', None)
        cp_rows.append(stable)
    return _sha(_encoded(_safe({'config': evidence['config'], 'splits': evidence['splits'],
        'training_runs': runs, 'probe_rows': evidence['probe_rows'], 'cp_rows': cp_rows})))


def run_experiment(output_dir: Path, *, episodes=64, max_active_seconds=120):
    """Run exactly four bounded training configurations and retain all 96 probe rows."""
    if type(episodes) is not int or not 1 <= episodes <= 64:
        raise ValueError('episodes must be an integer in 1..64')
    if (type(max_active_seconds) not in (int, float) or not math.isfinite(max_active_seconds)
            or not 0 < max_active_seconds <= 120):
        raise ValueError('max_active_seconds must be finite, positive and <=120')
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()

    def check_budget():
        if time.monotonic() - start >= max_active_seconds:
            raise PilotBudgetExceeded('Global pilot active-time cap expired')

    config = {'version': 1, 'episodes': episodes, 'validation_every': min(16, episodes),
        'modes': MODES, 'training_seeds': TRAINING_SEEDS, 'hidden_size': 16, 'learning_rate': .01,
        'algorithm': 'REINFORCE', 'input_features': 372, 'output_actions': 100,
        'activation': 'tanh', 'parameter_count': 7668,
        'gamma': 1, 'max_gradient_norm': 1., 'max_active_seconds': max_active_seconds,
        'max_training_steps': 1536, 'cp_time_limit': 1., 'cp_num_workers': 1, 'cp_seed': 42,
        'methods': METHODS, 'probe_purpose': 'engineering_probe_not_final_G3_test',
        'selection': 'minimum_greedy_validation_mean_tardiness_earliest_tie',
        'hyperparameter_search': False, 'network_calls': 0, 'model_api_calls': 0}
    splits = build_splits()
    source_hashes = {name: _sha((ROOT / name).read_bytes()) for name in SOURCE_FILES}
    data_hash, config_hash = _sha(_encoded(splits['metadata'])), _sha(_encoded(config))
    runs = [{'mode': mode, 'seed': seed, 'status': 'NOT_RUN', 'episodes_completed': 0,
        'training_steps': 0, 'selected_episode': None, 'logs': [], 'validation_history': [],
        'checkpoints': {}, 'interval_checkpoints': [], 'error_type': None,
        'progress_log': f'logs/{mode}-seed{seed}.jsonl'} for mode in MODES for seed in TRAINING_SEEDS]
    rows = [{'mode': mode, 'seed': seed, 'probe_index': index, 'method': method,
        'instance_identity': _identity(data), 'validation_status': 'NOT_RUN', 'schedule_accepted': False,
        'actions': None, 'transitions': [], 'payload': None, 'plan_sha256': None, 'error_type': None,
        'check': {'accepted': False, 'issues': []}, 'replay_check': {'accepted': False, 'issues': []},
        'cp_comparison': None} for mode in MODES for seed in TRAINING_SEEDS
        for index, data in enumerate(splits['probe']) for method in METHODS]
    cp_rows = [{'mode': mode, 'probe_index': index, 'instance_identity': _identity(data),
        'validation_status': 'NOT_RUN', 'schedule_accepted': False, 'optimum_certified': False,
        'check': {'accepted': False, 'issues': []}, 'payload': None, 'plan_sha256': None, 'error_type': None,
        **{field: None for field in CERTIFICATE_FIELDS}}
        for mode in MODES for index, data in enumerate(splits['probe'])]
    evidence = {'purpose': PURPOSE, 'limitation': LIMITATION, 'research_status': 'not_achieved',
        'matrix_consuming_policy': True, 'config': config, 'splits': splits['metadata'],
        'training_runs': runs, 'probe_rows': rows, 'cp_rows': cp_rows, 'error_type': None}
    (output / 'logs').mkdir()

    def persist():
        _write_json(output / 'results.json', evidence)

    persist()
    timed_out = False
    try:
        from src.graduation.policy_training import run_policy_episode, train_policy
        for run in runs:
            check_budget()
            mode, seed = run['mode'], run['seed']
            run['status'] = 'RUNNING'
            prefix = f'checkpoints/{mode}-seed{seed}'

            def save(name, state, episode):
                return _save_checkpoint(output, f'{prefix}/{name}.npz', state, episode=episode,
                    source_hashes=source_hashes, data_hash=data_hash, config_hash=config_hash)

            def progress(event):
                # The event describes work that already completed. Archive it
                # before checking the deadline so a boundary stop loses no log.
                if event['kind'] == 'episode':
                    run['logs'].append(_safe(event['log']))
                    run['episodes_completed'] = event['episode']
                    run['training_steps'] = event['training_steps']
                    archived = _safe(event)
                elif event['kind'] == 'validation':
                    episode = event['episode']
                    current = save(f'current-episode-{episode:03d}', event['current_state'], episode)
                    selected = save(f'selected-episode-{episode:03d}', event['selected_state'], event['selected_episode'])
                    run['interval_checkpoints'].append({'episode': episode, 'current': current, 'selected': selected})
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
                with (output / run['progress_log']).open('ab') as handle:
                    handle.write(_encoded(archived) + b'\n')
                persist()
                check_budget()

            try:
                result = train_policy(splits['training'], splits['validation'], mode=mode, seed=seed,
                    episodes=episodes, validation_every=config['validation_every'], learning_rate=.01,
                    hidden_size=16, check_budget=check_budget, on_progress=progress)
                for name in ('initial', 'final', 'selected'):
                    episode = 0 if name == 'initial' else (result['selected_episode'] if name == 'selected'
                                                          else result['episodes_completed'])
                    run['checkpoints'][name] = save(name, result[name + '_state'], episode)
                if (result['episodes_completed'] != episodes or result['training_steps'] != episodes*6
                        or _safe(result['logs']) != run['logs']):
                    raise ValueError('Training completion differs from durable progress evidence')
                run.update(status='COMPLETED', episodes_completed=result['episodes_completed'],
                    training_steps=result['training_steps'], selected_episode=result['selected_episode'])
                check_budget()
            except PilotBudgetExceeded:
                run.update(status='BUDGET_STOP', error_type='PilotBudgetExceeded')
                raise
            except Exception as exc:
                run.update(status='FAILED', error_type=type(exc).__name__)
            persist()

        for row in cp_rows:
            check_budget()
            try:
                remaining = max_active_seconds - (time.monotonic() - start)
                if remaining <= 0:
                    raise PilotBudgetExceeded('Global pilot active-time cap expired')
                result = solve_parallel_maintenance(splits['probe'][row['probe_index']], mode=row['mode'],
                    time_limit=min(1., remaining), num_workers=1, seed=42)
                row.update({field: getattr(result, field) for field in CERTIFICATE_FIELDS})
                row['payload'] = _plan_payload(result, splits['probe'][row['probe_index']], row['mode'], row['check'])
                row['plan_sha256'] = _plan_hash(row['payload'])
                status, objective, bound = row['solver_status'], row['solver_objective_value'], row['solver_objective_bound']
                if (status not in ('OPTIMAL', 'FEASIBLE') or type(objective) not in (int, float)
                        or not math.isfinite(objective) or objective != row['payload']['total_tardiness']
                        or type(bound) not in (int, float) or not math.isfinite(bound) or not 0 <= bound <= objective
                        or (status == 'OPTIMAL' and bound != objective)):
                    raise ValueError('CP certificate is inconsistent with its checked plan')
                row.update(validation_status='PASS', schedule_accepted=True, optimum_certified=status == 'OPTIMAL')
                check_budget()
            except PilotBudgetExceeded:
                row.update(validation_status='BUDGET_STOP', schedule_accepted=False, optimum_certified=False,
                           error_type='PilotBudgetExceeded')
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
            data = splits['probe'][row['probe_index']]
            run = next(item for item in runs if (item['mode'], item['seed']) == (row['mode'], row['seed']))
            try:
                actor = None
                if row['method'] in ('initial', 'final', 'selected'):
                    if run['status'] != 'COMPLETED':
                        raise ValueError('A failed training run cannot supply accepted policy probes')
                    checkpoint = run['checkpoints'][row['method']]
                    actor = load_checkpoint(output / checkpoint['path'], expected_sha256=checkpoint['sha256'])
                    episode = run_policy_episode(data, mode=row['mode'], actor=actor, seed=row['seed'],
                                                 deterministic=True, check_budget=check_budget)
                else:
                    episode = run_maintenance_rule_episode(data, mode=row['mode'], rule=row['method'], seed=row['seed'])
                _checked_episode(row, episode, data, actor=actor, check_budget=check_budget)
                reference = next(item for item in cp_rows if (item['mode'], item['probe_index']) ==
                                 (row['mode'], row['probe_index']))
                if reference['schedule_accepted']:
                    delta = row['payload']['total_tardiness'] - reference['payload']['total_tardiness']
                    row['cp_comparison'] = {'solver_status': reference['solver_status'],
                        'tardiness_difference': delta, 'optimum_certified': reference['optimum_certified']}
                    if reference['optimum_certified'] and delta < 0:
                        raise ValueError('A candidate beat an OPTIMAL CP reference; evidence is inconsistent')
                row.update(validation_status='PASS', schedule_accepted=True)
                check_budget()
            except PilotBudgetExceeded:
                row.update(validation_status='BUDGET_STOP', schedule_accepted=False, error_type='PilotBudgetExceeded')
                raise
            except Exception as exc:
                row.update(validation_status='FAIL', schedule_accepted=False, error_type=type(exc).__name__)
            persist()
        if sum(run['training_steps'] for run in runs) > 1536:
            raise ValueError('Pilot exceeded its maximum declared training steps')
        check_budget()
    except PilotBudgetExceeded:
        timed_out = True
        evidence['error_type'] = 'PilotBudgetExceeded'
    except Exception as exc:
        evidence['error_type'] = type(exc).__name__
    persist()
    artifact_hashes = {path.relative_to(output).as_posix(): _sha(path.read_bytes())
                       for path in sorted(output.rglob('*')) if path.is_file() and path.name != 'manifest.json'}
    completed = sum(run['status'] == 'COMPLETED' for run in runs)
    accepted, cp_accepted = sum(row['schedule_accepted'] for row in rows), sum(row['schedule_accepted'] for row in cp_rows)
    # This check is after the last training/solver/replay/file-hash call, so a slow
    # final call cannot turn an exceeded deadline into a successful experiment.
    try:
        check_budget()
    except PilotBudgetExceeded:
        timed_out = True
        evidence['error_type'] = 'PilotBudgetExceeded'
        persist()
        artifact_hashes['results.json'] = _sha((output / 'results.json').read_bytes())
    status = ('BUDGET_STOP' if timed_out else 'COMPLETED' if completed == 4 and accepted == 96
              and cp_accepted == 8 and evidence['error_type'] is None else 'FAILED')
    manifest = {'version': 1, 'purpose': PURPOSE, 'status': status, 'limitation': LIMITATION,
        'research_status': 'not_achieved', 'matrix_consuming_policy': True,
        'research_targets': {'paper_reproduction': 'not_achieved', 'graduation_research': 'not_achieved'},
        'expected_training_runs': 4, 'completed_training_runs': completed,
        'expected_probe_rows': 96, 'accepted_probe_rows': accepted,
        'expected_cp_rows': 8, 'accepted_cp_rows': cp_accepted,
        'training_steps': sum(run['training_steps'] for run in runs), 'config': config,
        'data_sha256': data_hash, 'config_sha256': config_hash, 'source_hashes': source_hashes,
        'outcome_digest': _digest_outcome(evidence), 'artifacts': artifact_hashes,
        'error_type': evidence['error_type'], 'runtime': {'python': sys.version,
            'python_executable': sys.executable, 'numpy': np.__version__,
            'numpy_preimported': NUMPY_PREIMPORTED, 'threads': {key: os.environ[key] for key in THREAD_VARIABLES},
            'elapsed_seconds': time.monotonic() - start}}
    _write_json(output / 'manifest.json', manifest)
    return json.loads((output / 'manifest.json').read_bytes())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--episodes', type=int, default=64)
    parser.add_argument('--max-active-seconds', type=float, default=120)
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = args.output_dir or ROOT / 'experiments/runs/neural_policy' / stamp
    try:
        manifest = run_experiment(output, episodes=args.episodes, max_active_seconds=args.max_active_seconds)
    except (ValueError, OSError) as exc:
        print(f'Neural policy pilot stopped: {type(exc).__name__}')
        return 1
    print(f"{manifest['status']}: probes={manifest['accepted_probe_rows']}/96; "
          f"CP={manifest['accepted_cp_rows']}/8; {output / 'manifest.json'}")
    print(LIMITATION)
    return 0 if manifest['status'] == 'COMPLETED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
