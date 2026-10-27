"""Exercise the shared check entry point through real child processes."""
from pathlib import Path
import csv
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'check_experiments.py'


def test_checks_run_static_dynamic_and_explicit_matrix_into_one_new_directory(tmp_path):
    output = tmp_path / 'checks'
    run = subprocess.run([sys.executable, str(SCRIPT), '--output-dir', str(output),
                          '--heavy', '--max-files', '1'],
                         capture_output=True, text=True, timeout=90)
    assert run.returncode == 0, run.stdout + run.stderr
    summary = json.loads((output / 'checks.json').read_text(encoding='utf-8'))
    assert summary['status'] == 'COMPLETED'
    for name in ['exp_001_toy_instance', 'exp_002_solver_check', 'exp_003_dispatching_rules',
                 'exp_004_benchmark_smoke', 'exp_014_dynamic_reschedule_smoke',
                 'exp_016_dynamic_event_file_reschedule']:
        assert (output / (name + '.evidence.json')).exists()
    assert (output / 'exp_017_phase2a_dynamic_report.md').exists()
    with (output / 'quality_families.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    assert any(row['algorithm_family'] == 'EarliestAvailableMachine' for row in rows)
    assert all(command['exit_code'] == 0 for command in summary['commands'])
    assert list(json.loads((output / 'input_scope.json').read_text())) == ['Brandimarte1993/mk01.fjs']
    with (output / 'reference_scope.csv').open(encoding='utf-8', newline='') as f:
        assert [r['instance_name'] for r in csv.DictReader(f)] == ['Brandimarte1993/mk01.fjs']


def test_checks_stop_on_child_failure_and_save_failure_receipt(tmp_path):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    experiments = tmp_path / 'experiments'
    experiments.mkdir()
    copied = scripts / SCRIPT.name
    copied.write_bytes(SCRIPT.read_bytes())
    (experiments / 'exp_001_toy_instance.py').write_text('raise SystemExit(7)\n')
    (experiments / 'exp_002_solver_check.py').write_text(
        "from pathlib import Path\nPath('should-not-run').write_text('bad')\n")
    output = tmp_path / 'failed'
    run = subprocess.run([sys.executable, str(copied), '--output-dir', str(output)],
                         capture_output=True, text=True, timeout=30)
    assert run.returncode != 0
    assert not (tmp_path / 'should-not-run').exists()
    summary = json.loads((output / 'checks.json').read_text(encoding='utf-8'))
    assert summary['status'] == 'FAILED'
    assert len(summary['commands']) == 1
    assert summary['commands'][0]['exit_code'] == 7


def test_checks_refuse_existing_output_before_running_any_experiment(tmp_path):
    marker = tmp_path / 'keep.txt'
    marker.write_text('original')
    run = subprocess.run([sys.executable, str(SCRIPT), '--output-dir', str(tmp_path)],
                         capture_output=True, text=True, timeout=30)
    assert run.returncode != 0
    assert 'Use a new output directory' in run.stderr
    assert marker.read_text() == 'original'
    assert list(tmp_path.iterdir()) == [marker]
