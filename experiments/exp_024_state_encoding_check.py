"""Lossless state transport and saved R2 action replay; no policy or training."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.exp_022_graduation_rule_smoke import CONFIG, build_cases
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.metrics import calculate_total_tardiness
from src.graduation.rl_environment import ConstructionObservation, ParallelMaintenanceEnv
from src.graduation.rules import run_maintenance_rule_episode
from src.graduation.state_encoding import (
    TypedStateEncoding, decode_construction_observation, encode_construction_observation,
)

PURPOSE = 'state_encoding_transport_replay_validation'
RESEARCH_STATUS = 'not_achieved'
LIMITATION = ('Verifies transport and replay of saved R2 actions only; no matrix-consuming '
              'policy, training, performance advantage or research-target achievement.')
CERTIFICATE_FIELDS = ('solver_status', 'solver_objective_value', 'solver_objective_bound',
                      'solver_gap', 'solver_wall_time')


def _encoded(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _rejected_evidence(value):
    """Keep malformed trace evidence JSON-safe without accepting or repairing it."""
    if type(value) is float and not math.isfinite(value):
        return {'invalid_float': 'nan' if math.isnan(value) else ('inf' if value > 0 else '-inf')}
    if isinstance(value, dict):
        if any(type(key) is not str for key in value):
            # Do not stringify arbitrary keys or repair rejected data into an
            # accepted payload. Preserve its shape explicitly as diagnostics.
            return {'invalid_mapping': [
                {'key_type': type(key).__name__, 'key': _rejected_evidence(key),
                 'value': _rejected_evidence(item)} for key, item in value.items()]}
        return {key: _rejected_evidence(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_rejected_evidence(item) for item in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    return {'invalid_type': type(value).__name__}


def _capture(env, snapshot):
    """Retain raw evidence before checking the codec, including on rejection."""
    observation = env.observe()
    if type(observation) is not ConstructionObservation:
        raise ValueError('Expected an original typed observation')
    raw = asdict(observation)
    snapshot['observation'] = raw
    clocks = env.machine_tails
    snapshot['machine_tails'] = clocks
    if (type(clocks) is not tuple or len(clocks) != env.data.num_machines
            or any(type(value) is not int or value < 0 for value in clocks)):
        raise ValueError('Exact machine clocks must remain integer tuples')
    transport = encode_construction_observation(observation)
    if type(transport) is not TypedStateEncoding:
        raise ValueError('Expected a typed state encoding')
    snapshot['encoded'] = asdict(transport)
    # Independent column interpretation catches compensating encoder/decoder mistakes.
    expected_rows = tuple(
        tuple(features) + (0.0,) * 7 + (1.0, 0.0, float(present))
        for features, present in zip(raw['task_features'], raw['task_presence'])) + tuple(
        (0.0,) * 3 + tuple(features) + (0.0, 1.0, float(present))
        for features, present in zip(raw['machine_features'], raw['machine_presence']))
    if _encoded(transport.rows) != _encoded(expected_rows):
        raise ValueError('Encoding differs from the declared literal column mapping')
    if transport.version != 1 or any(
            _encoded(getattr(transport, field)) != _encoded(raw[field])
            for field in ('mode', 'status', 'steps', 'scale', 'action_mask')):
        raise ValueError('Transport changed an auxiliary field')
    restored = decode_construction_observation(transport)
    if type(restored) is not ConstructionObservation or _encoded(asdict(restored)) != _encoded(raw):
        raise ValueError('Observation roundtrip changed features, presences, mask or auxiliary fields')
    if env.machine_tails != clocks:
        raise ValueError('Transport changed exact environment clocks')


def _accepted_payload(result, data, mode, actions, rewards, total_reward, check):
    accepted, issues = check_parallel_maintenance_feasibility(result, data, mode=mode)
    check.update(accepted=accepted, issues=[asdict(issue) for issue in issues])
    if not accepted:
        raise ValueError('Original G1 checker rejected the plan')
    recomputed = calculate_total_tardiness(data, result)
    completions = {record.job_id: record.end for record in result.records}
    independent = sum(max(0, completions[task.job_id] - task.due_date) for task in data.tasks)
    if result.total_tardiness != recomputed or recomputed != independent:
        raise ValueError('Reported tardiness differs from independent recomputation')
    if any(getattr(result, field) is not None for field in CERTIFICATE_FIELDS):
        raise ValueError('Rule plans must not carry solver certificates')
    if type(total_reward) is not float or not math.isfinite(total_reward) or not math.isclose(
            total_reward, -independent / 100, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError('Complete return differs from negative total tardiness / 100')
    if rewards is not None and (any(type(reward) is not float or not math.isfinite(reward) for reward in rewards)
            or not math.isclose(sum(rewards), total_reward, rel_tol=0.0, abs_tol=1e-12)):
        raise ValueError('Per-transition rewards differ from total return')
    payload = {'actions': list(actions), 'rewards': rewards, 'total_reward': total_reward,
        'total_tardiness': result.total_tardiness, 'recomputed_total_tardiness': recomputed,
        'makespan': result.makespan, 'plan': {
            'records': [asdict(record) for record in result.records],
            'maintenance_records': [asdict(record) for record in result.maintenance_records],
            **{field: getattr(result, field) for field in CERTIFICATE_FIELDS}}}
    _encoded(payload)
    return payload


def _run_row(name, data, mode, rule):
    row = {'case': name, 'mode': mode, 'rule': rule, 'seed': CONFIG['seed'],
        'validation_status': 'FAIL', 'schedule_accepted': False, 'actions': None,
        'baseline': None, 'replay': None, 'trace': [],
        'baseline_check': {'accepted': False, 'issues': []},
        'replay_check': {'accepted': False, 'issues': []}, 'error_type': None, 'failure_stage': None}
    stage = 'baseline_episode'
    try:
        episode = run_maintenance_rule_episode(data, mode=mode, rule=rule, seed=CONFIG['seed'])
        if (episode.rule, episode.mode, episode.seed) != (rule, mode, CONFIG['seed']):
            raise ValueError('Rule episode metadata differs from the requested configuration')
        bound = len(data.tasks) + data.num_machines
        if type(episode.actions) is not tuple or len(episode.actions) != bound or any(
                type(action) is not int or not 0 <= action < 100 for action in episode.actions):
            raise ValueError('Saved actions must be exactly n+m integer transitions')
        row['actions'] = list(episode.actions)
        baseline = _accepted_payload(episode.result, data, mode, episode.actions, None,
                                     episode.total_reward, row['baseline_check'])
        baseline_env, replay_env = ParallelMaintenanceEnv(data, mode=mode), ParallelMaintenanceEnv(data, mode=mode)
        baseline_rewards, replay_rewards = [], []
        for index, action in enumerate(episode.actions):
            transition = {'step': index, 'action': action,
                'baseline_before': {}, 'replay_before': {}, 'baseline_after': {}, 'replay_after': {}}
            row['trace'].append(transition)
            stage = 'before_observation'
            _capture(baseline_env, transition['baseline_before'])
            _capture(replay_env, transition['replay_before'])
            if _encoded(transition['baseline_before']) != _encoded(transition['replay_before']):
                raise ValueError('Replay before-state differs from original state')
            if not transition['replay_before']['observation']['action_mask'][action]:
                raise ValueError('Saved action is masked in replay')
            stage = 'transition'
            original_step, replay_step = baseline_env.step(action), replay_env.step(action)
            transition.update(baseline_reward=original_step.reward, replay_reward=replay_step.reward,
                terminated=replay_step.terminated, truncated=replay_step.truncated)
            baseline_rewards.append(original_step.reward)
            replay_rewards.append(replay_step.reward)
            if (original_step.reward != replay_step.reward or original_step.terminated != replay_step.terminated
                    or original_step.truncated != replay_step.truncated or replay_step.truncated
                    or replay_step.terminated != (index == bound - 1)):
                raise ValueError('Replay rewards or termination differ from bounded original transitions')
            stage = 'after_observation'
            _capture(baseline_env, transition['baseline_after'])
            _capture(replay_env, transition['replay_after'])
            if (_encoded(transition['baseline_after']) != _encoded(transition['replay_after'])
                    or _encoded(asdict(original_step.observation)) != _encoded(transition['baseline_after']['observation'])
                    or _encoded(asdict(replay_step.observation)) != _encoded(transition['replay_after']['observation'])):
                raise ValueError('Replay after-state differs from original or returned observation')
        stage = 'terminal_plans'
        raw_replay = _accepted_payload(baseline_env.get_result(), data, mode, episode.actions, baseline_rewards,
                                       sum(baseline_rewards), row['baseline_check'])
        baseline['rewards'] = baseline_rewards
        replay = _accepted_payload(replay_env.get_result(), data, mode, episode.actions, replay_rewards,
                                   sum(replay_rewards), row['replay_check'])
        if _encoded(baseline) != _encoded(raw_replay) or _encoded(baseline) != _encoded(replay):
            raise ValueError('Replay changed accepted actions, rewards, schedule or metrics')
        candidate = dict(row, validation_status='PASS', schedule_accepted=True, baseline=baseline, replay=replay)
        _encoded(candidate)
        return candidate
    except Exception as exc:
        # Never copy arbitrary exception messages (which may contain local/private data).
        row['error_type'] = type(exc).__name__
        row['failure_stage'] = stage
        return _rejected_evidence(row)


def run_experiment(output_dir: Path):
    """Create fresh bounded evidence, retaining all 24 rows including rejections."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    cases = build_cases()
    inputs = {name: asdict(data) for name, data in cases.items()}
    rows = [_run_row(name, data, mode, rule) for name, data in cases.items()
            for mode in CONFIG['modes'] for rule in CONFIG['rules']]
    evidence = {'purpose': PURPOSE, 'research_status': RESEARCH_STATUS, 'matrix_consuming_policy': False,
                'limitation': LIMITATION, 'inputs': inputs, 'config': CONFIG, 'rows': rows}
    results_bytes = _encoded(evidence)
    (output_dir / 'results.json').write_bytes(results_bytes)
    # Paths, time, revision and runtime are excluded from deterministic outcomes.
    outcome = {'inputs': inputs, 'config': CONFIG, 'rows': rows}
    sources = (
        'src/graduation/__init__.py', 'src/graduation/data.py', 'src/graduation/result.py',
        'src/graduation/metrics.py', 'src/graduation/feasibility.py', 'src/graduation/_production.py',
        'src/graduation/rl_environment.py', 'src/graduation/rules.py', 'src/graduation/state_encoding.py',
        'src/scheduling/encoding.py', 'src/scheduling/feasibility.py', 'src/data/instance.py',
        'experiments/exp_022_graduation_rule_smoke.py', 'experiments/exp_024_state_encoding_check.py')
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
        capture_output=True, text=True, check=False).stdout.strip()
    accepted = sum(row['schedule_accepted'] for row in rows)
    manifest = {'version': 1, 'purpose': PURPOSE, 'research_status': RESEARCH_STATUS,
        'matrix_consuming_policy': False, 'limitation': LIMITATION,
        'status': 'COMPLETED' if accepted == 24 and len(rows) == 24 else 'FAILED',
        'expected_runs': 24, 'accepted_runs': accepted, 'config': CONFIG,
        'outcome_digest': _sha(_encoded(outcome)), 'runtime': {
            'git_head': revision, 'python': sys.version, 'python_executable': sys.executable,
            'source_hashes': {relative: _sha((ROOT / relative).read_bytes()) for relative in sources}},
        'artifacts': {'results.json': _sha(results_bytes)}}
    manifest_bytes = _encoded(manifest)
    (output_dir / 'manifest.json').write_bytes(manifest_bytes)
    return json.loads(manifest_bytes)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = args.output_dir or ROOT / 'experiments/runs/state_encoding' / stamp
    try:
        manifest = run_experiment(output)
    except (ValueError, OSError) as exc:
        print(f'State encoding transport validation stopped: {type(exc).__name__}')
        return 1
    print(f"{manifest['status']}: {manifest['accepted_runs']}/{manifest['expected_runs']}; {output / 'manifest.json'}")
    print(f"{LIMITATION} research_status={RESEARCH_STATUS}; digest={manifest['outcome_digest']}")
    return 0 if manifest['status'] == 'COMPLETED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
