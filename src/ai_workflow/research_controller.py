"""Durable outer orchestration over a finite offline research tool registry."""

from contextlib import contextmanager
import importlib.metadata
import json
import math
import os
from pathlib import Path
import subprocess
import sqlite3
import sys
import time

from src.ai_workflow.contracts import get_research_contract
from src.ai_workflow.process_supervisor import supervised_json_process
from src.ai_workflow.runtime_budget import BudgetExceeded, BudgetLimits, RunBudget
from src.ai_workflow.research_tasks import (ROOT, DEFAULT_REFERENCE, DEFAULT_PAPER, encoded,
    sha, read_json, input_hashes, inspect_inputs, choose_next, validate_task_result)


def _write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(encoded(value))
    temporary.replace(path)


@contextmanager
def _exclusive_lock(folder):
    with (folder / 'controller.lock').open('a+b') as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError('Controller is already running') from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _source_hashes():
    files = sorted((ROOT / 'src').rglob('*.py')) + [ROOT / 'pyproject.toml']
    files += [ROOT / 'experiments' / name for name in ('exp_025_neural_policy_pilot.py',
              'exp_026_validation_iteration.py', 'exp_027_research_controller.py')]
    return {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in files}


def read_controller_status(folder):
    folder = Path(folder)
    state = read_json(folder / 'state.json')
    state['budget'] = RunBudget.read_snapshot(folder / 'budget.sqlite')
    return state


def _validate_results(folder, state, expected_inputs, check_budget=lambda: None):
    completed = {}
    for index, task in enumerate(state['tasks'], 1):
        check_budget()
        if task['status'] == 'COMPLETED':
            path = folder / f'task_{index:02d}.json'
            if sha(path.read_bytes()) != task['result_sha256']:
                raise ValueError('Saved task result identity changed')
            result = read_json(path)
            validate_task_result(task['id'], result, expected_inputs, folder, check_budget=check_budget)
            completed[task['id']] = result
    return completed


def _existing_budget(path, limits):
    """Validate before RunBudget's create-if-missing initializer can repair/reset it."""
    try:
        if not path.is_file():
            raise ValueError('Missing controller budget ledger')
        snapshot = RunBudget.read_snapshot(path)
        if snapshot['limits'] != {'max_active_seconds': limits.max_active_seconds,
                                  'max_provider_calls': 0, 'max_output_tokens': 0}:
            raise ValueError('Controller budget identity/configuration changed')
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        try:
            rows = db.execute('SELECT id FROM workflow_budget').fetchall()
            segments = db.execute('SELECT reserved_seconds, finished_seconds FROM workflow_segments').fetchall()
        finally:
            db.close()
        if (rows != [(1,)] or snapshot['provider_calls'] != 0 or snapshot['output_tokens_reserved'] != 0
                or not math.isfinite(snapshot['active_seconds']) or snapshot['active_seconds'] < 0
                or any(not math.isfinite(r) or r <= 0 or (f is not None and
                       (not math.isfinite(f) or f < 0)) for r, f in segments)
                or not math.isclose(snapshot['active_seconds'], math.fsum(f for _, f in segments if f is not None),
                                    abs_tol=1e-8, rel_tol=1e-12)):
            raise ValueError('Inconsistent controller budget ledger')
        return RunBudget(path, limits)
    except (sqlite3.Error, TypeError, IndexError) as exc:
        raise ValueError('Invalid controller budget ledger') from exc


def _deadline_checkpoint(budget):
    """Cheap checkpoints within the exclusively owned active reservation.

    Snapshot I/O is included conservatively. The caller still reads the durable
    ledger at dispatch/acceptance boundaries; this does not grant another segment.
    """
    started = time.monotonic()
    deadline = started + budget.remaining_seconds()
    def check():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BudgetExceeded('Active execution time budget exhausted')
        return remaining
    return check


def run_controller(folder, *, reference_archive=None, paper_archive=None, max_active_seconds=120,
                   max_tasks=None, steps=None, track='graduation', profile='audit_v1'):
    """Start/resume an immutable batch; steps limits this invocation, not its budget."""
    if track not in ('graduation', 'innovation'):
        raise ValueError('Unknown research track')
    if profile not in ('audit_v1', 'shared_scorer_v1', 'shared_scorer_feedback_v1'):
        raise ValueError('Unknown controller profile')
    ceiling = {'audit_v1': 2, 'shared_scorer_v1': 5, 'shared_scorer_feedback_v1': 7}[profile]
    max_tasks = ceiling if max_tasks is None else max_tasks
    steps = ceiling if steps is None else steps
    if (type(max_tasks) is not int or not 1 <= max_tasks <= ceiling
            or type(steps) is not int or not 1 <= steps <= ceiling):
        raise ValueError('Task/step limits exceed the declared profile')
    limits = BudgetLimits(max_active_seconds, 0, 0)
    if profile == 'shared_scorer_feedback_v1' and limits.max_active_seconds > 120:
        raise ValueError('Feedback profile is limited to 120 cumulative active seconds')
    folder = Path(folder).resolve()
    reference, paper = Path(reference_archive or DEFAULT_REFERENCE).resolve(), Path(paper_archive or DEFAULT_PAPER).resolve()
    if any(folder.is_relative_to(p) or p.is_relative_to(folder) for p in (reference, paper)):
        raise ValueError('Controller output and input archives must not overlap')
    folder.mkdir(parents=True, exist_ok=True)
    with _exclusive_lock(folder):
        spec_path, state_path = folder / 'spec.json', folder / 'state.json'
        initialization = {'track': track, 'profile': profile, 'max_tasks': max_tasks, 'max_active_seconds': max_active_seconds,
                          'reference_archive': str(reference), 'paper_archive': str(paper)}
        existing = spec_path.exists()
        if existing:
            spec, state = read_json(spec_path), read_json(state_path)
            budget = _existing_budget(folder / 'budget.sqlite', limits)
            if spec.get('identity') is None:
                if spec.get('initialization') != initialization:
                    raise ValueError('Controller initialization identity/configuration changed')
                if state['status'] != 'STOPPED':
                    state.update(status='STOPPED', stop_reason='initialization_incomplete')
                    _write(state_path, state)
                return read_controller_status(folder)
        else:
            if any(p.name != 'controller.lock' for p in folder.iterdir()):
                raise ValueError('A new controller batch requires an empty folder')
            budget = RunBudget(folder / 'budget.sqlite', limits)
            state = {'version': 1, 'status': 'READY', 'stop_reason': None, 'tasks': [], 'decisions': [],
                'next_task': None, 'skipped_candidates': [], 'research_status': 'not_achieved', 'tracks': {},
                'capability_boundary': 'Finite offline registry; optional exact-template training; no arbitrary patching or paper discovery.'}
            _write(state_path, state)
            _write(spec_path, {'identity': None, 'initialization': initialization})
        terminal = state['status'] == 'STOPPED'
        started = time.monotonic()
        segment = None
        if not terminal:
            try:
                segment, _ = budget.reserve_active_segment()
            except BudgetExceeded:
                state.update(status='STOPPED', stop_reason='interrupted_task' if state['status'] == 'RUNNING'
                             else 'active_time_budget')
                _write(state_path, state)
                return read_controller_status(folder)
            budget.start_segment(segment)
        try:
            _run_reserved(folder, state, spec if existing else None, budget, terminal, steps,
                          track, max_tasks, max_active_seconds, reference, paper, profile)
        except Exception:
            if not existing and read_json(spec_path).get('identity') is None:
                state.update(status='STOPPED', stop_reason='initialization_failed')
            raise
        finally:
            if segment is not None:
                budget.finish_active_segment(segment, time.monotonic() - started)
            _write(state_path, state)
        return read_controller_status(folder)


def _run_reserved(folder, state, spec, budget, terminal, steps, track, max_tasks,
                  max_active_seconds, reference, paper, profile):
    """All nonterminal identity checks and dispatch happen inside the reservation."""
    preflight_done = False
    try:
        check = (lambda: None) if terminal else _deadline_checkpoint(budget)
        check()
        contracts = {name: get_research_contract(name).to_dict() for name in ('graduation', 'innovation')}
        identity = {'version': 2, 'track': track, 'profile': profile, 'max_tasks': max_tasks,
            'max_active_seconds': max_active_seconds, 'provider_calls': 0, 'output_tokens': 0,
            'reference_archive': str(reference), 'paper_archive': str(paper),
            'source_hashes': _source_hashes(), 'contracts': contracts,
            'runtime': {'python': sys.version, 'numpy': importlib.metadata.version('numpy'),
                        'ortools': importlib.metadata.version('ortools')}}
        # Dataclass contracts contain tuples; persist and compare one JSON shape.
        identity = json.loads(encoded(identity))
        check()
        current_inputs = input_hashes(reference, paper, check)
        if spec is not None:
            if spec['identity'] != identity:
                raise ValueError('Controller identity/configuration changed; use a new batch')
            if spec['input_hashes'] != current_inputs:
                raise ValueError('Controller input identity changed; use a new batch')
        else:
            spec = {'identity': identity, 'input_hashes': current_inputs}
            _write(folder / 'spec.json', spec)
            state['tracks'] = {name: {'research_status': 'not_achieved', 'contract_hash': contract['contract_hash'],
                'required_capabilities': contract['required_capabilities']} for name, contract in contracts.items()}
        completed = _validate_results(folder, state, spec['input_hashes'], check)
        if not terminal:
            budget.remaining_seconds()
            check()
        preflight_done = True
        if state['status'] == 'RUNNING':
            state.update(status='STOPPED', stop_reason='interrupted_task')
        if state['status'] != 'STOPPED':
            observation = inspect_inputs(reference, paper, check)
            state['skipped_candidates'] = observation['rejected_candidates']
            performed = 0
            while True:
                budget.remaining_seconds()
                check()
                choice = choose_next(observation, completed, track=track, profile=profile)
                state['decisions'].append(choice)
                if 'stop_reason' in choice:
                    state.update(status='STOPPED', stop_reason=choice['stop_reason'], next_task=choice['next_task'])
                    break
                if len(state['tasks']) >= max_tasks:
                    state.update(status='STOPPED', stop_reason='task_count_budget', next_task=choice)
                    break
                if performed >= steps:
                    state.update(status='YIELDED', stop_reason='invocation_slice', next_task=choice)
                    break
                task_id = choice['task_id']
                task = {'id': task_id, 'status': 'RUNNING', 'reason': choice['reason']}
                state['tasks'].append(task)
                state.update(status='RUNNING', stop_reason=None, next_task=None)
                _write(folder / 'state.json', state)
                timeout = min(budget.remaining_seconds(), check())
                result = supervised_json_process(Path(__file__).with_name('research_worker.py'),
                    {'task_id': task_id, 'reference_archive': str(reference), 'paper_archive': str(paper),
                     'expected_inputs': spec['input_hashes'], 'batch_dir': str(folder)}, timeout=timeout)
                budget.remaining_seconds()
                check()
                if type(result) is dict and result.get('status') == 'FAILED':
                    task['worker_error_type'] = str(result.get('error_type', 'Unknown'))[:80]
                validate_task_result(task_id, result, spec['input_hashes'], folder, check_budget=check)
                budget.remaining_seconds()
                if input_hashes(reference, paper, check) != spec['input_hashes']:
                    raise ValueError('Input identity changed during worker execution')
                budget.remaining_seconds()  # Never accept a receipt against a stale ledger snapshot.
                check()  # The preceding database read may itself have consumed the remaining time.
                index = len(state['tasks'])
                _write(folder / f'task_{index:02d}.json', result)
                task.update(status='COMPLETED', result_sha256=sha(encoded(result)))
                completed[task_id] = result
                state['status'] = 'READY'
                _write(folder / 'state.json', state)
                performed += 1
    except Exception as exc:
        if not preflight_done and not isinstance(exc, BudgetExceeded):
            raise
        if state['tasks'] and state['tasks'][-1]['status'] == 'RUNNING':
            state['tasks'][-1].update(status='FAILED', error_type=type(exc).__name__)
        reason = ('active_time_budget' if isinstance(exc, BudgetExceeded) else
                  'task_timeout' if isinstance(exc, subprocess.TimeoutExpired) else 'task_failed')
        state.update(status='STOPPED', stop_reason=reason)
    # Caller settles the active reservation before constructing the returned snapshot.
    return state
