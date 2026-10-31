"""Shared local/CI experiment checks; --heavy also builds fresh benchmark evidence."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--heavy', action='store_true')
    parser.add_argument('--max-files', type=int)
    args = parser.parse_args(argv)
    if args.max_files is not None and args.max_files <= 0:
        parser.error('--max-files must be positive')
    output = (args.output_dir or ROOT / 'experiments/runs' / ('checks-' + uuid.uuid4().hex)).resolve()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error('Use a new output directory; existing evidence is never overwritten')
    print(f'Python: {sys.executable}\nOutput: {output}', flush=True)
    commands = [
        ('exp_001_toy_instance.py', ['--output-dir', output]),
        ('exp_002_solver_check.py', ['--output-dir', output]),
        ('exp_003_dispatching_rules.py', ['--output-dir', output]),
        ('exp_004_benchmark_smoke.py', ['--output-dir', output]),
        ('exp_012_benchmark_metadata_audit.py', ['--output', output / 'metadata.csv']),
        ('exp_014_dynamic_reschedule_smoke.py', ['--output-dir', output]),
        ('exp_015_dynamic_event_file_check.py', ['--output', output / 'exp_015_dynamic_event_file_check.csv']),
        ('exp_016_dynamic_event_file_reschedule.py', ['--output-dir', output]),
        ('exp_017_phase2a_dynamic_report.py', [
            '--smoke-input', output / 'exp_014_dynamic_reschedule_smoke.csv',
            '--audit-input', output / 'exp_015_dynamic_event_file_check.csv',
            '--replay-input', output / 'exp_016_dynamic_event_file_reschedule.csv',
            '--output', output / 'exp_017_phase2a_dynamic_report.md']),
    ]
    if args.heavy:
        # Keep instance IDs relative to the same root as the tracked BKS table.
        inputs = ['--input-dir', ROOT / 'instances/fjsplib']
        if args.max_files is not None:
            inputs += ['--max-files', str(args.max_files)]
        reference = ROOT / 'instances/fjsplib_bks.csv'
        if args.max_files is not None:
            benchmark_root = ROOT / 'instances/fjsplib'
            selected = sorted(benchmark_root.rglob('*.fjs'), key=lambda p: p.as_posix())[:args.max_files]
            expected = {p.relative_to(benchmark_root).as_posix() for p in selected}
            with reference.open(encoding='utf-8-sig', newline='') as f:
                reader = csv.DictReader(f)
                fields = reader.fieldnames
                rows = [r for r in reader if r['instance_name'] in expected]
            if {r['instance_name'] for r in rows} != expected:
                parser.error('Declared benchmark subset is missing BKS references')
            reference = output / 'reference_scope.csv'
            with reference.open('x', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            # Bind the declared subset before any run; never filter by successful results.
            (output / 'input_scope.json').write_text(json.dumps({
                p.relative_to(benchmark_root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in selected}, indent=2) + '\n', encoding='utf-8')
        commands += [
            ('exp_005_benchmark_batch.py', inputs + ['--skip-cp-sat', '--output', output / 'batch.csv']),
            ('exp_009_cpsat_benchmark_matrix.py', inputs + [
                '--worker-counts', '1', '--repeats', '1', '--time-limit', '3',
                '--runs-output', output / 'cpsat_runs.csv', '--summary-output', output / 'cpsat_summary.csv']),
            ('exp_010_heuristic_benchmark_matrix.py', inputs + [
                '--runs-output', output / 'heuristic_runs.csv', '--summary-output', output / 'heuristic_summary.csv']),
            ('exp_011_heuristic_quality_report.py', [
                '--summary-input', output / 'heuristic_summary.csv',
                '--bks-input', reference,
                '--quality-output', output / 'quality_rows.csv', '--family-output', output / 'quality_families.csv']),
            ('exp_013_cpsat_report.py', [
                '--bks-input', reference,
                '--summary-input', output / 'cpsat_summary.csv', '--output', output / 'cpsat_report.md']),
        ]
    receipt = {'version': 1, 'status': 'RUNNING', 'heavy': args.heavy,
               'python': sys.executable, 'created_utc': datetime.now(timezone.utc).isoformat(),
               'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'commands': []}

    def save():
        (output / 'checks.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')

    save()
    for script, arguments in commands:
        command = [sys.executable, str(ROOT / 'experiments' / script), *map(str, arguments)]
        started = time.monotonic()
        entry = {'script': script, 'arguments': list(map(str, arguments)), 'exit_code': None}
        with (output / (script + '.log')).open('w', encoding='utf-8') as log:
            try:
                code = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                      timeout=300).returncode
            except (OSError, subprocess.TimeoutExpired) as exc:
                code = 124 if isinstance(exc, subprocess.TimeoutExpired) else 1
                entry['error_type'] = type(exc).__name__
        entry.update(exit_code=code, wall_seconds=time.monotonic() - started)
        receipt['commands'].append(entry)
        print(f'{script}: exit {code}', flush=True)
        if code:
            receipt['status'] = 'FAILED'
            save()
            return 1
        save()
    receipt['status'] = 'COMPLETED'
    save()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
