"""R2 development validation: four literal inputs, two modes, three rules; no training."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graduation.data import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.metrics import calculate_total_tardiness
from src.graduation.rules import run_maintenance_rule_episode

CONFIG = {'modes': ('fixed', 'joint'), 'rules': ('EDD', 'SPT', 'Random'), 'seed': 42}
PURPOSE = 'r2_development_validation'
RESEARCH_STATUS = 'not_achieved'


def build_cases() -> dict[str, ParallelMaintenanceInstance]:
    return {
        'one_machine': ParallelMaintenanceInstance((ProductionTask(0, 2, 2), ProductionTask(1, 2, 4)), 1,
            (MaintenanceRequirement(0, 2, 0, 6, 0),)),
        'two_machines': ParallelMaintenanceInstance(tuple(ProductionTask(j, 2, d) for j, d in enumerate((2, 2, 4))), 2,
            tuple(MaintenanceRequirement(m, 2, 0, 6, 0) for m in range(2))),
        'idle_machine': ParallelMaintenanceInstance((ProductionTask(0, 2, 2),), 2,
            tuple(MaintenanceRequirement(m, 2, 0, 2, 0) for m in range(2))),
        'late_maintenance': ParallelMaintenanceInstance((ProductionTask(0, 1, 1),), 1,
            (MaintenanceRequirement(0, 1, 3, 4, 3),)),
    }


def _encoded(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _run_row(name, data, mode, rule):
    row = {'case': name, 'mode': mode, 'rule': rule, 'seed': CONFIG['seed'],
           'validation_status': 'FAIL', 'schedule_accepted': False, 'actions': None,
           'total_reward': None, 'total_tardiness': None, 'recomputed_total_tardiness': None,
           'makespan': None, 'plan': None, 'g1_check': {'accepted': False, 'issues': []}, 'error': ''}
    try:
        episode = run_maintenance_rule_episode(data, mode=mode, rule=rule, seed=CONFIG['seed'])
        result = episode.result
        accepted, issues = check_parallel_maintenance_feasibility(result, data, mode=mode)
        row['g1_check'] = {'accepted': accepted, 'issues': [asdict(issue) for issue in issues]}
        if not accepted:
            raise ValueError(f'G1 rejected rule plan: {issues}')
        recomputed = calculate_total_tardiness(data, result)
        # Serialize only after both production and maintenance have passed G1.
        plan = {'records': [asdict(record) for record in result.records],
                'maintenance_records': [asdict(record) for record in result.maintenance_records],
                'solver_status': result.solver_status, 'solver_objective_value': result.solver_objective_value,
                'solver_objective_bound': result.solver_objective_bound, 'solver_gap': result.solver_gap,
                'solver_wall_time': result.solver_wall_time}
        if any(plan[field] is not None for field in ('solver_status', 'solver_objective_value',
                'solver_objective_bound', 'solver_gap', 'solver_wall_time')):
            raise ValueError('Rule plans must not carry solver certificates')
        candidate = dict(row, validation_status='PASS', schedule_accepted=True, actions=list(episode.actions),
            total_reward=episode.total_reward, total_tardiness=result.total_tardiness,
            recomputed_total_tardiness=recomputed, makespan=result.makespan, plan=plan)
        _encoded(candidate)  # Reject NaN and malformed payloads before accepting any metrics.
        return candidate
    except Exception as exc:
        row['error'] = f'{type(exc).__name__}: {str(exc)[:1000]}'
        return row


def run_experiment(output_dir: Path):
    """Write a fresh, bounded 24-row development matrix and retain failed rows."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    cases = build_cases()
    inputs = {name: asdict(data) for name, data in cases.items()}
    rows = [_run_row(name, data, mode, rule) for name, data in cases.items()
            for mode in CONFIG['modes'] for rule in CONFIG['rules']]
    evidence = {'purpose': PURPOSE, 'research_status': RESEARCH_STATUS, 'inputs': inputs,
                'config': CONFIG, 'rows': rows}
    results_bytes = _encoded(evidence)
    (output_dir / 'results.json').write_bytes(results_bytes)
    # Bind deterministic evidence only: no paths, timing, Git revision or runtime.
    outcome = {'inputs': inputs, 'config': CONFIG, 'rows': [
        {key: value for key, value in row.items() if key != 'error'} for row in rows]}
    paths = [ROOT / relative for relative in (
        'src/graduation/__init__.py', 'src/graduation/data.py', 'src/graduation/result.py', 'src/graduation/metrics.py',
        'src/graduation/feasibility.py', 'src/graduation/_production.py',
        'src/graduation/rl_environment.py', 'src/graduation/rules.py',
        'src/scheduling/encoding.py', 'src/scheduling/feasibility.py', 'src/data/instance.py',
        'experiments/exp_022_graduation_rule_smoke.py')]
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                              capture_output=True, text=True, check=False).stdout.strip()
    accepted_count = sum(row['schedule_accepted'] for row in rows)
    manifest = {'version': 1, 'purpose': PURPOSE, 'research_status': RESEARCH_STATUS,
        'status': 'COMPLETED' if accepted_count == 24 and len(rows) == 24 else 'FAILED',
        'expected_runs': 24, 'accepted_runs': accepted_count, 'config': CONFIG,
        'outcome_digest': _sha(_encoded(outcome)),
        'runtime': {'git_head': revision, 'python': sys.version,
            'source_hashes': {path.relative_to(ROOT).as_posix(): _sha(path.read_bytes()) for path in paths}},
        'artifacts': {'results.json': _sha(results_bytes)}}
    manifest_bytes = _encoded(manifest)
    (output_dir / 'manifest.json').write_bytes(manifest_bytes)
    # Match the JSON representation also for sequence fields in the returned manifest.
    return json.loads(manifest_bytes)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = args.output_dir or ROOT / 'experiments/runs/graduation_r2' / stamp
    try:
        manifest = run_experiment(output)
    except (ValueError, OSError) as exc:
        print(f'R2 development validation stopped: {exc}')
        return 1
    print(f"{manifest['status']}: {manifest['accepted_runs']}/{manifest['expected_runs']}; {output / 'manifest.json'}")
    print(f"Development evidence only; research_status={RESEARCH_STATUS}; digest={manifest['outcome_digest']}")
    return 0 if manifest['status'] == 'COMPLETED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
