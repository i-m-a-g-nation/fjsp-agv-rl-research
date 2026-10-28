"""The approved preparation ledger remains the only cumulative main budget."""
import importlib
import json
import sqlite3

import pytest

from src.ai_workflow import graduation_main_scope as scope
from src.ai_workflow.research_controller import _exclusive_lock
from src.ai_workflow.runtime_budget import BudgetExceeded, RunBudget


def test_main_budget_api_exposes_reader_and_phase_runner():
    module = importlib.import_module('src.ai_workflow.graduation_main_budget')
    assert callable(module.read_main_budget)
    assert callable(module.run_main_phase)


@pytest.fixture
def prepared(tmp_path):
    folder = tmp_path / 'scope'
    scope.prepare_main_scope(folder)
    return folder


@pytest.fixture
def main():
    return importlib.import_module('src.ai_workflow.graduation_main_budget')


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock(main, monkeypatch):
    result = Clock()
    monkeypatch.setattr(main.time, 'monotonic', result)
    return result


def contents(folder):
    return {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}


def sql(folder, statement, parameters=()):
    with sqlite3.connect(folder / 'budget.sqlite') as db:
        db.execute(statement, parameters)


def test_read_preserves_the_complete_prepared_prefix_without_sidecars(prepared, main):
    before = contents(prepared)
    frozen = json.loads((prepared / 'budget_snapshot.json').read_text(encoding='utf-8'))
    snapshot = main.read_main_budget(prepared)
    assert snapshot['segments'] == frozen['segments']
    assert snapshot['limits'] == {'max_active_seconds': 600, 'max_provider_calls': 0,
                                  'max_output_tokens': 0}
    assert snapshot['active_seconds'] == frozen['active_seconds']
    assert snapshot['active_seconds_charged'] == frozen['active_seconds']
    assert snapshot['active_seconds_reserved'] == 0
    assert snapshot['provider_calls'] == snapshot['output_tokens_reserved'] == 0
    assert snapshot['remaining_active_seconds'] == 600 - frozen['active_seconds']
    assert contents(prepared) == before


def test_repeated_phases_append_to_original_budget_and_preserve_scope(prepared, main, clock, tmp_path):
    before = contents(prepared)
    original = main.read_main_budget(prepared)
    receipts = []

    def finalize(value, snapshot, check_final):
        assert check_final() > 0
        receipts.append(snapshot)
        clock.advance(0.5)
        return 'saved:' + value

    for duration in (2, 3):
        def work(handle):
            assert handle.check() > 0
            assert handle.remaining() > 0
            assert handle.snapshot()['active_seconds_reserved'] > 0
            clock.advance(duration)
            return str(duration)
        assert main.run_main_phase(prepared, tmp_path / 'control', work, finalize) == f'saved:{duration}'
    final = main.read_main_budget(prepared)
    assert final['active_seconds'] == pytest.approx(original['active_seconds'] + 15)
    assert [s['finished_seconds'] for s in final['segments'][2:]] == [2, 5, 3, 5]
    assert receipts[-1] == final
    assert {k: v for k, v in contents(prepared).items() if k != 'budget.sqlite'} == {
        k: v for k, v in before.items() if k != 'budget.sqlite'}
    assert set(contents(prepared)) == set(before)
    assert not (tmp_path / 'control' / 'budget.sqlite').exists()
    assert (tmp_path / 'control' / 'controller.lock').is_file()


def test_checkpoint_uses_fixed_monotonic_deadline_without_reading_database(prepared, main, clock, tmp_path, monkeypatch):
    original = main.read_main_budget(prepared)
    real_read = main.read_main_budget

    def forbidden(*args):
        pytest.fail('A cheap checkpoint must not reread the ledger or scope')

    def work(handle):
        monkeypatch.setattr(main, 'read_main_budget', forbidden)
        assert handle.remaining() == pytest.approx(original['remaining_active_seconds'] - 5)
        clock.advance(601)
        with pytest.raises(BudgetExceeded):
            handle.check()
        monkeypatch.setattr(main, 'read_main_budget', real_read)
        handle.check()

    with pytest.raises(BudgetExceeded):
        main.run_main_phase(prepared, tmp_path / 'control', work, lambda *_: pytest.fail('late finalize'))
    assert main.read_main_budget(prepared)['remaining_active_seconds'] == 0


def test_preflight_source_hashing_is_charged_from_entry(prepared, main, clock, tmp_path, monkeypatch):
    original = scope._sources
    delayed = [False]

    def slow_sources():
        result = original()
        if not delayed[0]:
            delayed[0] = True
            clock.advance(601)
        return result

    monkeypatch.setattr(scope, '_sources', slow_sources)
    with pytest.raises(BudgetExceeded):
        main.run_main_phase(prepared, tmp_path / 'control', lambda _: pytest.fail('late work'), lambda *_: None)
    snapshot = main.read_main_budget(prepared)
    assert snapshot['segments'][2]['finished_seconds'] >= 601
    assert snapshot['remaining_active_seconds'] == 0


@pytest.mark.parametrize('caller_preflight', [12, 601])
def test_caller_preflight_origin_is_charged_and_can_expire_work(prepared, main, clock, tmp_path, caller_preflight):
    previous = main.read_main_budget(prepared)
    started_at = clock()
    clock.advance(caller_preflight)
    def work(handle):
        assert caller_preflight == 12
        assert handle.remaining() == pytest.approx(previous['remaining_active_seconds'] - 12 - 5)
        clock.advance(3)
        return 'done'
    if caller_preflight == 601:
        with pytest.raises(BudgetExceeded):
            main.run_main_phase(prepared, tmp_path / 'control', work,
                                lambda *_: pytest.fail('expired finalization'), started_at=started_at)
        snapshot = main.read_main_budget(prepared)
        assert snapshot['segments'][2]['finished_seconds'] == 601
        assert snapshot['remaining_active_seconds'] == 0
    else:
        assert main.run_main_phase(prepared, tmp_path / 'control', work,
                                   lambda value, snapshot, check: value, started_at=started_at) == 'done'
        snapshot = main.read_main_budget(prepared)
        assert snapshot['segments'][2]['finished_seconds'] == 15
        assert snapshot['active_seconds'] == pytest.approx(previous['active_seconds'] + 20)


@pytest.mark.parametrize('started_at', [True, False, '1000', float('nan'), float('inf'),
                                      -float('inf'), 1001])
def test_invalid_caller_origin_never_mutates_original_ledger(prepared, main, clock, tmp_path, started_at):
    before = contents(prepared)
    with pytest.raises(ValueError):
        main.run_main_phase(prepared, tmp_path / 'control', lambda _: pytest.fail('invalid origin'),
                            lambda *_: None, started_at=started_at)
    assert contents(prepared) == before


@pytest.mark.parametrize('delay', ['callback', 'settlement', 'receipt_read', 'final_reserve'])
def test_every_finalization_step_shares_the_same_five_second_window(prepared, main, clock, tmp_path, monkeypatch, delay):
    finalized = []
    if delay == 'settlement':
        original = RunBudget.finish_active_segment
        def slow_finish(self, segment_id, seconds):
            original(self, segment_id, seconds)
            if segment_id == 3:
                clock.advance(500)
        monkeypatch.setattr(RunBudget, 'finish_active_segment', slow_finish)
    elif delay == 'receipt_read':
        original = main.read_main_budget
        def slow_read(*args):
            result = original(*args)
            if len(result['segments']) == 4:
                clock.advance(500)
            return result
        monkeypatch.setattr(main, 'read_main_budget', slow_read)
    elif delay == 'final_reserve':
        original = RunBudget.reserve_active_segment
        def slow_reserve(self):
            result = original(self)
            if result[0] == 4:
                clock.advance(500)
            return result
        monkeypatch.setattr(RunBudget, 'reserve_active_segment', slow_reserve)

    def finalize(value, snapshot, check_final):
        finalized.append(snapshot)
        clock.advance(500)
        return 'must not escape'

    with pytest.raises(BudgetExceeded):
        main.run_main_phase(prepared, tmp_path / 'control', lambda _: 'value', finalize)
    assert bool(finalized) is (delay == 'callback')
    assert main.read_main_budget(prepared)['remaining_active_seconds'] == 0


def test_work_exception_is_charged_without_calling_finalize(prepared, main, clock, tmp_path):
    before = main.read_main_budget(prepared)
    def work(handle):
        clock.advance(7)
        raise LookupError('work failed')
    with pytest.raises(LookupError, match='work failed'):
        main.run_main_phase(prepared, tmp_path / 'control', work, lambda *_: pytest.fail('failed work finalized'))
    snapshot = main.read_main_budget(prepared)
    assert len(snapshot['segments']) == 3
    assert snapshot['segments'][-1]['finished_seconds'] == 7
    assert snapshot['active_seconds'] == pytest.approx(before['active_seconds'] + 7)


def test_finalizer_exception_after_deadline_reports_budget_exhaustion(prepared, main, clock, tmp_path):
    def finalize(value, snapshot, check_final):
        clock.advance(500)
        raise LookupError('late callback failure')
    with pytest.raises(BudgetExceeded):
        main.run_main_phase(prepared, tmp_path / 'control', lambda _: 'value', finalize)
    assert main.read_main_budget(prepared)['remaining_active_seconds'] == 0


def test_finalizer_exception_before_deadline_preserves_error_and_blocks_retry(prepared, main, clock, tmp_path):
    def finalize(value, snapshot, check_final):
        raise LookupError('persistence failed')
    with pytest.raises(LookupError, match='persistence failed'):
        main.run_main_phase(prepared, tmp_path / 'control', lambda _: 'value', finalize)
    snapshot = main.read_main_budget(prepared)
    assert snapshot['segments'][3]['finished_seconds'] == 5
    assert snapshot['segments'][-1]['finished_seconds'] is None
    with pytest.raises(BudgetExceeded):
        main.run_main_phase(prepared, tmp_path / 'control', lambda _: None, lambda *_: None)


@pytest.mark.parametrize('damage', ['reservation', 'refund', 'negative', 'gap', 'nonzero_tokens'])
def test_later_cumulative_segments_are_validated_too(prepared, main, damage):
    budget = RunBudget(prepared / 'budget.sqlite', scope.LIMITS)
    identifier, _ = budget.reserve_active_segment()
    budget.finish_active_segment(identifier, 10)
    if damage == 'reservation':
        sql(prepared, 'UPDATE workflow_segments SET reserved_seconds=1 WHERE id=?', (identifier,))
    elif damage == 'refund':
        sql(prepared, 'UPDATE workflow_budget SET active_seconds=active_seconds-0.0000000001')
    elif damage == 'negative':
        sql(prepared, 'UPDATE workflow_segments SET finished_seconds=-1 WHERE id=?', (identifier,))
    elif damage == 'gap':
        sql(prepared, 'UPDATE workflow_segments SET id=id+1 WHERE id=?', (identifier,))
    else:
        sql(prepared, 'UPDATE workflow_budget SET output_tokens_reserved=1')
    with pytest.raises(ValueError):
        main.read_main_budget(prepared)


def test_ordinary_phase_does_not_call_solver_or_provider(prepared, main, clock, tmp_path, monkeypatch):
    from src.graduation import solver
    def forbidden(*args, **kwargs):
        pytest.fail('The budget helper must not execute a solver or provider')
    monkeypatch.setattr(solver, 'solve_parallel_maintenance', forbidden)
    monkeypatch.setattr(RunBudget, 'reserve_provider_call', forbidden)
    assert main.run_main_phase(prepared, tmp_path / 'control', lambda _: 17,
                               lambda value, snapshot, check: value) == 17


@pytest.mark.parametrize('damage', ['missing', 'corrupt', 'wal', 'sidecar', 'reset', 'refund',
                                   'prefix', 'reservation', 'gap', 'nonzero_calls', 'typed_limits'])
def test_invalid_existing_ledger_is_rejected_before_initializer(prepared, main, tmp_path, damage):
    path = prepared / 'budget.sqlite'
    if damage == 'missing':
        path.unlink()
    elif damage == 'corrupt':
        path.write_bytes(b'not sqlite')
    elif damage == 'wal':
        with sqlite3.connect(path) as db:
            db.execute('PRAGMA journal_mode=WAL').fetchone()
    elif damage == 'sidecar':
        (prepared / 'budget.sqlite-journal').write_bytes(b'interrupted')
    elif damage == 'reset':
        sql(prepared, 'DELETE FROM workflow_segments')
        sql(prepared, 'UPDATE workflow_budget SET active_seconds=0')
    elif damage == 'refund':
        sql(prepared, 'UPDATE workflow_budget SET active_seconds=active_seconds-1')
    elif damage == 'prefix':
        sql(prepared, 'UPDATE workflow_segments SET finished_seconds=finished_seconds+1 WHERE id=1')
        sql(prepared, 'UPDATE workflow_budget SET active_seconds=active_seconds+1')
    elif damage == 'reservation':
        sql(prepared, 'UPDATE workflow_segments SET reserved_seconds=1 WHERE id=2')
    elif damage == 'gap':
        sql(prepared, 'UPDATE workflow_segments SET id=3 WHERE id=2')
    elif damage == 'nonzero_calls':
        sql(prepared, 'UPDATE workflow_budget SET provider_calls=1')
    else:
        sql(prepared, 'UPDATE workflow_budget SET limits_json=?',
            (json.dumps({'max_active_seconds': 600.0, 'max_provider_calls': 0, 'max_output_tokens': 0}, sort_keys=True),))
    before = contents(prepared)
    with pytest.raises(ValueError):
        main.read_main_budget(prepared)
    with pytest.raises(ValueError):
        main.run_main_phase(prepared, tmp_path / 'control', lambda _: None, lambda *_: None)
    assert contents(prepared) == before


def test_unfinished_tail_is_exhausted_and_never_resumed(prepared, main, tmp_path):
    budget = RunBudget(prepared / 'budget.sqlite', scope.LIMITS)
    budget.reserve_active_segment()
    before = contents(prepared)
    snapshot = main.read_main_budget(prepared)
    assert snapshot['active_seconds_charged'] == 600
    assert snapshot['active_seconds_reserved'] > 0
    assert snapshot['remaining_active_seconds'] == 0
    with pytest.raises(BudgetExceeded):
        main.run_main_phase(prepared, tmp_path / 'control', lambda _: pytest.fail('resumed'), lambda *_: None)
    assert contents(prepared) == before


def test_no_segment_can_follow_an_unsettled_segment(prepared, main):
    budget = RunBudget(prepared / 'budget.sqlite', scope.LIMITS)
    identifier, _ = budget.reserve_active_segment()
    sql(prepared, 'INSERT INTO workflow_segments(id,reserved_seconds,finished_seconds) VALUES (?,?,?)',
        (identifier + 1, 1, 0))
    with pytest.raises(ValueError):
        main.read_main_budget(prepared)


def test_insufficient_finalization_budget_never_starts_work(prepared, main, clock, tmp_path):
    budget = RunBudget(prepared / 'budget.sqlite', scope.LIMITS)
    identifier, remaining = budget.reserve_active_segment()
    budget.finish_active_segment(identifier, remaining - 4)
    with pytest.raises(BudgetExceeded):
        main.run_main_phase(prepared, tmp_path / 'control', lambda _: pytest.fail('insufficient work'), lambda *_: None)


def test_nonblocking_lock_rejects_concurrent_phase(prepared, main, tmp_path):
    control = tmp_path / 'control'
    control.mkdir()
    before = contents(prepared)
    with _exclusive_lock(control):
        with pytest.raises(ValueError, match='already running'):
            main.run_main_phase(prepared, control, lambda _: pytest.fail('concurrent work'), lambda *_: None)
    assert contents(prepared) == before


@pytest.mark.parametrize('suffix', ['', 'nested'])
def test_control_files_cannot_be_created_inside_scope(prepared, main, suffix):
    before = contents(prepared)
    with pytest.raises(ValueError):
        main.run_main_phase(prepared, prepared / suffix, lambda _: None, lambda *_: None)
    assert contents(prepared) == before
    assert not (prepared / 'nested').exists()
