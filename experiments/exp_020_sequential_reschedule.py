"""Hand-checkable sequential Phase 2A replay; no new optimizer or AI calls."""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.instance import FJSPInstance
from src.dynamic import JobArrival, MachineBreakdown, MachineRepair, ProcessingTimeChange, replay_events


@dataclass(frozen=True)
class StreamScenario:
    name: str
    jobs: list
    events: tuple
    num_machines: int | None = None


def build_scenarios():
    return [
        StreamScenario('repair_releases_work', [[[(0, 4)]]], (
            MachineBreakdown(time=0, machine_id=0, repair_time=20), MachineRepair(time=5, machine_id=0)), 1),
        StreamScenario('arrival_then_duration', [[[(0, 3)], [(1, 4)], [(0, 2)]]], (
            MachineBreakdown(time=1, machine_id=1, repair_time=5), JobArrival(time=4, operations=(((0, 2),),)),
            ProcessingTimeChange(time=6, job_id=0, op_id=2, machine_id=0, new_processing_time=4)), 2),
        StreamScenario('simultaneous_updates', [[[(0, 3)], [(0, 2)]]], (
            MachineBreakdown(time=0, machine_id=0, repair_time=2),
            ProcessingTimeChange(time=0, job_id=0, op_id=0, machine_id=0, new_processing_time=7),
            JobArrival(time=0, operations=(((0, 1),),))), 1),
    ]


def _encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8')


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _event_spec(event):
    names = {MachineBreakdown: 'machine_breakdown', MachineRepair: 'machine_repair',
             JobArrival: 'job_arrival', ProcessingTimeChange: 'processing_time_change'}
    return {'type': names[type(event)], **asdict(event)}


def _schedule(result):
    if result is None:
        return None
    return {'makespan': result.makespan, 'records': [asdict(r) for r in sorted(result.records, key=lambda r: (r.job_id, r.op_id))]}


def _episode_data(episode):
    steps = []
    for step in episode.steps:
        state = step.state
        steps.append({'time': step.time, 'events': [_event_spec(e) for e in step.events],
            'frozen_records': [asdict(r) for r in step.frozen_records], 'result': _schedule(step.result),
            'state': {'jobs': [[list(op.machine_options) for op in job.operations] for job in state.instance.jobs],
                      'num_machines': state.instance.num_machines, 'current_time': state.current_time,
                      'job_release_times': state.job_release_times, 'machine_unavailable_until': state.machine_unavailable_until}})
    return {'initial': _schedule(episode.initial), 'steps': steps, 'final_result': _schedule(episode.final_result),
            'failed_events': [_event_spec(e) for e in episode.failed_events], 'error': episode.error}


def _report(manifest, rows, traces):
    lines = ['<!-- fjsp-generated-report track=foundation -->', '# Phase 2A Sequential Replay Validation', '',
        f"Status: **{manifest['status']}**; passed episodes {manifest['passed_episodes']}/{manifest['expected_episodes']}; completed timestamp groups {manifest['completed_steps']}.",
        '', '| Scenario | Rule | Status | Final makespan | Completed groups |', '|---|---|---|---:|---:|']
    for row in rows:
        makespan = '' if row['final_makespan'] is None else row['final_makespan']
        lines.append(f"| {row['scenario']} | {row['rule']} | {row['status']} | {makespan} | {row['completed_steps']} |")
    lines.extend(['', '## Chronological trace', '',
        '| Episode | Time | Current event batch | Frozen operations | Planned makespan |', '|---|---:|---|---|---:|'])
    for name, trace in traces.items():
        for step in trace['steps']:
            events = ', '.join(event['type'] for event in step['events'])
            frozen = ', '.join(f"J{r['job_id']}O{r['op_id']}" for r in step['frozen_records']) or 'none'
            lines.append(f"| {name} | {step['time']} | {events} | {frozen} | {step['result']['makespan']} |")
    lines.extend(['', '## Scope and interpretation', '',
        'Every episode uses the same initial FIFO plan and its own chronological execution history. Each rule receives only the current state, frozen records and current event batch.',
        'Equal-time events occur before dispatch. Completed and in-process records freeze from the immediately preceding validated schedule, including newly arrived jobs.',
        'Breakdowns are idle-only; processing interruption, transport, AGV, reinforcement learning and maintenance optimization are not modeled.',
        'Unsupported or failed batches stop an episode. Successful prefix traces remain diagnostic and are never accepted as a final result.',
        'These small hand-checkable streams test temporal correctness; they do not establish statistical superiority, dynamic optimality or real-world model fidelity.',
        'Innovation and graduation research goals remain NOT ACHIEVED. No human approval is implied by this development experiment.', ''])
    return '\n'.join(lines)


def run_experiment(output_dir: Path):
    scenarios, rules = build_scenarios(), ('fifo', 'spt', 'eft')
    if not scenarios or len({scenario.name for scenario in scenarios}) != len(scenarios):
        raise ValueError('Scenarios must be nonempty with unique names')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / 'inputs').mkdir()
    (output_dir / 'episodes').mkdir()
    rows, traces, case_hashes = [], {}, {}
    for scenario in scenarios:
        source = {'jobs': scenario.jobs, 'num_machines': scenario.num_machines, 'events': [_event_spec(e) for e in scenario.events]}
        data = _encoded(source)
        (output_dir / 'inputs' / f'{scenario.name}.json').write_bytes(data)
        case_hashes[scenario.name] = _sha(data)
        for rule in rules:
            started = time.perf_counter()
            try:
                instance = FJSPInstance.from_jobs_array(scenario.jobs, scenario.num_machines)
                episode = replay_events(instance, scenario.events, rule)
                trace = _episode_data(episode)
            except Exception as exc:
                trace = {'initial': None, 'steps': [], 'final_result': None, 'failed_events': source['events'],
                         'error': f'{type(exc).__name__}: {str(exc)[:500]}'}
            elapsed = time.perf_counter() - started
            accepted = not trace['error'] and trace['final_result'] is not None
            name = f'{scenario.name}-{rule}'
            traces[name] = trace
            (output_dir / 'episodes' / f'{name}.json').write_bytes(_encoded(trace))
            rows.append({'scenario': scenario.name, 'rule': rule, 'status': 'PASS' if accepted else 'FAIL',
                         'completed_steps': len(trace['steps']), 'final_makespan': trace['final_result']['makespan'] if accepted else None,
                         'runtime_s': elapsed, 'error': trace['error']})
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    (output_dir / 'raw.csv').write_bytes(stream.getvalue().encode('utf-8'))
    passed = sum(row['status'] == 'PASS' for row in rows)
    trace_hashes = {name: _sha(_encoded(trace)) for name, trace in traces.items()}
    source_paths = [*sorted((ROOT / 'src').rglob('*.py')), Path(__file__).resolve(), ROOT / 'pyproject.toml']
    source_hashes = {path.relative_to(ROOT).as_posix(): _sha(path.read_bytes()) for path in source_paths}
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
    manifest = {'version': 1, 'status': 'COMPLETED' if passed == len(rows) else 'FAILED',
                'expected_episodes': len(scenarios) * len(rules), 'passed_episodes': passed, 'failed_episodes': len(rows) - passed,
                'completed_steps': sum(row['completed_steps'] for row in rows), 'case_hashes': case_hashes,
                'trace_hashes': trace_hashes, 'deterministic_digest': _sha(_encoded({'cases': case_hashes, 'traces': trace_hashes})),
                'runtime': {'python': sys.version, 'git_head': revision, 'source_hashes': source_hashes}}
    (output_dir / 'report.md').write_bytes(_report(manifest, rows, traces).encode('utf-8'))
    manifest['artifacts'] = {path.relative_to(output_dir).as_posix(): _sha(path.read_bytes())
                             for path in sorted(output_dir.rglob('*')) if path.is_file() and path.name != 'manifest.json'}
    (output_dir / 'manifest.json').write_bytes(_encoded(manifest))
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = args.output_dir or ROOT / 'experiments/runs/sequential_replay' / stamp
    try:
        manifest = run_experiment(output)
    except (ValueError, OSError) as exc:
        print(f'Sequential validation stopped: {exc}')
        return 1
    print(f"{manifest['status']}: {manifest['passed_episodes']}/{manifest['expected_episodes']} episodes, {manifest['completed_steps']} timestamp groups; {output / 'report.md'}")
    print(f"Trace digest: {manifest['deterministic_digest']}")
    return 0 if manifest['status'] == 'COMPLETED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
