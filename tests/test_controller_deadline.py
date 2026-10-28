"""Fine-grained deadline checks must not repeatedly reopen the durable ledger."""
import sqlite3

import pytest

from src.ai_workflow import research_controller as controller, research_tasks as tasks
from src.ai_workflow.runtime_budget import BudgetExceeded


def test_checkpoint_uses_one_reservation_snapshot_and_real_elapsed_time(monkeypatch):
    clock = [0.]
    reads = []
    monkeypatch.setattr(controller.time, 'monotonic', lambda: clock[0])
    class Budget:
        def remaining_seconds(self):
            reads.append(True)
            return 10.
    check = controller._deadline_checkpoint(Budget())
    clock[0] = 9.
    for _ in range(1000):
        assert check() == 1.
    assert len(reads) == 1
    clock[0] = 10.
    with pytest.raises(BudgetExceeded):
        check()


def test_snapshot_io_time_cannot_extend_the_deadline(monkeypatch):
    clock = [0.]
    monkeypatch.setattr(controller.time, 'monotonic', lambda: clock[0])
    class Budget:
        def remaining_seconds(self):
            clock[0] = 3.
            return 10.
    check = controller._deadline_checkpoint(Budget())
    assert check() == 7.


def test_durable_budget_is_rechecked_before_accepting_a_task(tmp_path, monkeypatch):
    folder = tmp_path/'budget-changed'
    original = controller.validate_task_result
    def validate(*args, **kwargs):
        original(*args, **kwargs)
        with sqlite3.connect(folder/'budget.sqlite') as db:
            db.execute('UPDATE workflow_budget SET active_seconds=120 WHERE id=1')
    def worker(script, payload, timeout):
        return tasks.execute_task(payload['task_id'], payload['reference_archive'], payload['paper_archive'],
            expected_inputs=payload['expected_inputs'], batch_dir=payload['batch_dir'])
    monkeypatch.setattr(controller, 'validate_task_result', validate)
    monkeypatch.setattr(controller, 'supervised_json_process', worker)
    result = controller.run_controller(folder, steps=1)
    assert result['stop_reason'] == 'active_time_budget'
    assert result['tasks'][0]['status'] == 'FAILED'
    assert not (folder/'task_01.json').exists()


def test_slow_ledger_read_cannot_dispatch_after_the_local_deadline(tmp_path, monkeypatch):
    from src.ai_workflow.runtime_budget import RunBudget
    folder = tmp_path/'slow-ledger'
    real_clock, original = controller.time.monotonic, RunBudget.remaining_seconds
    offset, dispatched = [0.], []
    monkeypatch.setattr(controller.time, 'monotonic', lambda: real_clock()+offset[0])
    def remaining(budget):
        value = original(budget)
        state = folder/'state.json'
        if offset[0] == 0 and state.exists() and tasks.read_json(state)['status'] == 'RUNNING':
            offset[0] = 121.  # The database read returned a value measured before blocking.
        return value
    def forbidden(*args, **kwargs):
        dispatched.append(True)
        raise AssertionError('Expired reservation must not dispatch work')
    monkeypatch.setattr(RunBudget, 'remaining_seconds', remaining)
    monkeypatch.setattr(controller, 'supervised_json_process', forbidden)
    result = controller.run_controller(folder, steps=1)
    assert not dispatched
    assert result['stop_reason'] == 'active_time_budget'
