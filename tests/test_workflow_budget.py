import pytest


def test_reservations_persist_across_reopening(tmp_path):
    from src.ai_workflow.runtime_budget import BudgetLimits, RunBudget, BudgetExceeded
    path = tmp_path / "session.sqlite"
    limits = BudgetLimits(max_active_seconds=30, max_provider_calls=2, max_output_tokens=20)
    budget = RunBudget(path, limits)
    budget.reserve_provider_call(output_tokens=10)
    reopened = RunBudget(path, limits)
    reopened.reserve_provider_call(output_tokens=10)
    with pytest.raises(BudgetExceeded):
        reopened.reserve_provider_call(output_tokens=1)
    assert reopened.snapshot()["provider_calls"] == 2
    assert reopened.snapshot()["output_tokens_reserved"] == 20


def test_budget_cannot_be_changed_on_resume(tmp_path):
    from src.ai_workflow.runtime_budget import BudgetLimits, RunBudget
    RunBudget(tmp_path / "session.sqlite", BudgetLimits(max_provider_calls=1))
    with pytest.raises(ValueError, match="budget limits"):
        RunBudget(tmp_path / "session.sqlite", BudgetLimits(max_provider_calls=2))


def test_active_time_is_cumulative_and_exhaustion_is_terminal(tmp_path):
    from src.ai_workflow.runtime_budget import BudgetLimits, RunBudget, BudgetExceeded
    budget = RunBudget(tmp_path / "session.sqlite", BudgetLimits(max_active_seconds=1))
    budget.record_active_seconds(0.6)
    reopened = RunBudget(tmp_path / "session.sqlite", budget.limits)
    reopened.record_active_seconds(0.5)
    with pytest.raises(BudgetExceeded):
        reopened.remaining_seconds()


@pytest.mark.parametrize("kwargs", [{"max_active_seconds": float("nan")}, {"max_provider_calls": -1}, {"max_output_tokens": True}])
def test_invalid_budget_limits_fail(kwargs):
    from src.ai_workflow.runtime_budget import BudgetLimits
    with pytest.raises(ValueError):
        BudgetLimits(**kwargs)


def test_interrupted_active_segment_keeps_its_reserved_time(tmp_path):
    from src.ai_workflow.runtime_budget import BudgetLimits, RunBudget, BudgetExceeded
    path = tmp_path / "session.sqlite"
    budget = RunBudget(path, BudgetLimits(max_active_seconds=10))
    segment, allowance = budget.reserve_active_segment()
    assert allowance == pytest.approx(10)
    assert budget.snapshot()["active_seconds"] == 0
    assert budget.snapshot()["active_seconds_charged"] == pytest.approx(10)
    with pytest.raises(BudgetExceeded):
        RunBudget(path, budget.limits).remaining_seconds()
    worker = RunBudget(path, budget.limits)
    worker.start_segment(segment)
    assert worker.remaining_seconds() > 9
    budget.finish_active_segment(segment, 0.5)
    assert RunBudget(path, budget.limits).remaining_seconds() == pytest.approx(9.5)
