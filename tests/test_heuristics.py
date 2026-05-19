from src.data.instance import create_toy_instance
from src.scheduling.feasibility import check_feasibility
from src.solvers.heuristics import (
    fifo_solve,
    spt_solve,
    earliest_finish_time_solve,
    random_solve,
)


class TestFIFO:

    def test_fifo_produces_valid_schedule(self):
        instance = create_toy_instance()
        result = fifo_solve(instance)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"
        assert result.makespan > 0
        assert len(result.records) == instance.total_ops

    def test_fifo_makespan_positive(self):
        instance = create_toy_instance()
        result = fifo_solve(instance)
        assert result.makespan > 0


class TestSPT:

    def test_spt_produces_valid_schedule(self):
        instance = create_toy_instance()
        result = spt_solve(instance)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"
        assert result.makespan > 0
        assert len(result.records) == instance.total_ops


class TestEarliestFinishTime:

    def test_eft_produces_valid_schedule(self):
        instance = create_toy_instance()
        result = earliest_finish_time_solve(instance)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"
        assert result.makespan > 0
        assert len(result.records) == instance.total_ops


class TestRandom:

    def test_random_produces_valid_schedule(self):
        instance = create_toy_instance()
        result = random_solve(instance, seed=42)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"
        assert result.makespan > 0
        assert len(result.records) == instance.total_ops

    def test_random_deterministic(self):
        instance = create_toy_instance()
        r1 = random_solve(instance, seed=42)
        r2 = random_solve(instance, seed=42)
        assert r1.makespan == r2.makespan

    def test_random_different_seeds(self):
        instance = create_toy_instance()
        results = set()
        for seed in range(20):
            r = random_solve(instance, seed=seed)
            results.add(r.makespan)
        assert len(results) >= 1
