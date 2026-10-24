from pathlib import Path

import pytest

from src.ai_workflow.sandbox import evaluate_generated_rule, validate_generated_code_ast


VALID = "def ai_select_candidate(candidates, instance, rng=None):\n    return candidates[0]\n"


def test_required_missing_benchmark_fails(tmp_path: Path):
    result = evaluate_generated_rule(VALID, [tmp_path / "missing.fjs"])
    assert not result.passed
    assert "missing" in result.error_message.lower()


@pytest.mark.parametrize("body", ["instance.num_jobs = 1", "instance.jobs.clear()", "while True:\n        pass"])
def test_unsafe_constructs_are_rejected_before_execution(body):
    code = "def ai_select_candidate(candidates, instance, rng=None):\n    " + body + "\n    return candidates[0]\n"
    with pytest.raises(ValueError, match="Disallowed"):
        validate_generated_code_ast(code)


def test_generated_selector_is_deadline_bounded():
    code = "def ai_select_candidate(candidates, instance, rng=None):\n    for i in range(10**15):\n        pass\n    return candidates[0]\n"
    result = evaluate_generated_rule(code, [], timeout_seconds=2.0)
    assert not result.passed
    assert result.execution_status == "timeout"


def test_worker_rejects_non_candidate_output():
    code = "def ai_select_candidate(candidates, instance, rng=None):\n    return (999, 0, 0, 0, 0, 0, 0)\n"
    result = evaluate_generated_rule(code, [])
    assert not result.passed
    assert "candidate" in result.error_message.lower()


def test_valid_worker_result_has_resource_limits_and_quality_status():
    result = evaluate_generated_rule(VALID, [])
    assert result.passed
    assert result.execution_status == "completed"
    assert result.resource_limits_applied
    assert result.performance_status in {"better_on_evaluated_instances", "not_better_on_evaluated_instances"}


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_invalid_deadline_fails(timeout):
    with pytest.raises(ValueError, match="timeout_seconds"):
        evaluate_generated_rule(VALID, [], timeout_seconds=timeout)
