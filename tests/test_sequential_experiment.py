import csv
import hashlib
import json

import pytest


def test_native_streams_export_all_episodes_and_timestamp_groups(tmp_path):
    from experiments.exp_020_sequential_reschedule import run_experiment
    result = run_experiment(tmp_path / 'run')
    assert result['status'] == 'COMPLETED'
    assert (result['expected_episodes'], result['passed_episodes'], result['completed_steps']) == (9, 9, 18)
    with (tmp_path / 'run' / 'raw.csv').open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    expected = {'repair_releases_work': '9', 'arrival_then_duration': '13', 'simultaneous_updates': '12'}
    assert len(rows) == 9
    assert all(row['final_makespan'] == expected[row['scenario']] for row in rows)
    assert len(list((tmp_path / 'run' / 'episodes').glob('*.json'))) == 9
    for relative, digest in result['artifacts'].items():
        assert hashlib.sha256((tmp_path / 'run' / relative).read_bytes()).hexdigest() == digest


def test_replay_digest_covers_same_events_frozen_history_and_schedules(tmp_path):
    from experiments.exp_020_sequential_reschedule import run_experiment
    first = run_experiment(tmp_path / 'a')
    second = run_experiment(tmp_path / 'b')
    assert first['deterministic_digest'] == second['deterministic_digest']
    assert first['trace_hashes'] == second['trace_hashes']
    trace = json.loads((tmp_path / 'a' / 'episodes' / 'arrival_then_duration-eft.json').read_text(encoding='utf-8'))
    assert [step['time'] for step in trace['steps']] == [1, 4, 6]
    assert trace['steps'][0]['state']['machine_unavailable_until'] == [0, 5]
    assert len(trace['steps'][2]['frozen_records']) == 3


def test_failed_episode_preserves_prefix_but_has_no_final_makespan_and_cli_fails(tmp_path, monkeypatch):
    from experiments import exp_020_sequential_reschedule as experiment
    from src.dynamic import MachineBreakdown, MachineRepair, ProcessingTimeChange
    scenario = experiment.StreamScenario('invalid_frozen_change', [[[(0, 4)]]], (
        MachineBreakdown(time=0, machine_id=0, repair_time=20), MachineRepair(time=5, machine_id=0),
        ProcessingTimeChange(time=6, job_id=0, op_id=0, machine_id=0, new_processing_time=8)), 1)
    monkeypatch.setattr(experiment, 'build_scenarios', lambda: [scenario])
    assert experiment.main(['--output-dir', str(tmp_path / 'failed')]) == 1
    manifest = json.loads((tmp_path / 'failed' / 'manifest.json').read_text(encoding='utf-8'))
    assert (manifest['passed_episodes'], manifest['failed_episodes'], manifest['completed_steps']) == (0, 3, 6)
    trace = json.loads((tmp_path / 'failed' / 'episodes' / 'invalid_frozen_change-eft.json').read_text(encoding='utf-8'))
    assert trace['final_result'] is None
    assert trace['error'] and len(trace['steps']) == 2 and len(trace['failed_events']) == 1
    with (tmp_path / 'failed' / 'raw.csv').open(encoding='utf-8', newline='') as handle:
        assert all(row['final_makespan'] == '' for row in csv.DictReader(handle))


def test_existing_output_is_preserved(tmp_path):
    from experiments.exp_020_sequential_reschedule import run_experiment
    output = tmp_path / 'existing'
    output.mkdir()
    (output / 'sentinel').write_text('keep', encoding='utf-8')
    with pytest.raises(FileExistsError):
        run_experiment(output)
    assert [p.name for p in output.iterdir()] == ['sentinel']


def test_cli_success_reports_trace_output(tmp_path):
    from experiments.exp_020_sequential_reschedule import main
    assert main(['--output-dir', str(tmp_path / 'cli')]) == 0
    assert (tmp_path / 'cli' / 'report.md').is_file()
