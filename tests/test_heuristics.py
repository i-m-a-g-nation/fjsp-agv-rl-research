from src.data.instance import FJSPInstance, create_toy_instance
from src.scheduling.feasibility import check_feasibility
from src.solvers.heuristics import (
    fifo_solve,
    spt_solve,
    earliest_finish_time_solve,
    random_solve,
    dispatch_fifo_solve,
    dispatch_spt_solve,
    dispatch_eft_solve,
    dispatch_random_solve,
)


# ============================================================
# Legacy baseline tests
# ============================================================

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


# ============================================================
# Strict dispatching-rule tests
# ============================================================

class TestDispatchFIFO:

    def test_dispatch_fifo_feasible(self):
        """Strict FIFO must pass the feasibility checker."""
        instance = create_toy_instance()
        result = dispatch_fifo_solve(instance)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"
        assert result.makespan > 0
        assert len(result.records) == instance.total_ops

    def test_dispatch_fifo_ready_order(self):
        """FIFO selects the earliest ready operation."""
        # Job0O1 becomes ready at t=10, while Job1O0 has been ready since t=0.
        # Both can only start at t=10 on the single shared machine, so this
        # catches implementations that incorrectly sort FIFO by machine start.
        jobs = [
            [[(0, 10)], [(0, 1)]],
            [[(0, 1)]],
        ]
        instance = FJSPInstance.from_jobs_array(jobs, num_machines=1)
        result = dispatch_fifo_solve(instance)

        assert [(r.job_id, r.op_id) for r in result.records[:3]] == [
            (0, 0),
            (1, 0),
            (0, 1),
        ]

    def test_dispatch_fifo_makespan_range(self):
        """Makespan stays in a reasonable range."""
        instance = create_toy_instance()
        result = dispatch_fifo_solve(instance)
        assert 1 <= result.makespan <= 50


class TestDispatchSPT:

    def test_dispatch_spt_feasible(self):
        """Strict SPT must pass the feasibility checker."""
        instance = create_toy_instance()
        result = dispatch_spt_solve(instance)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"
        assert result.makespan > 0
        assert len(result.records) == instance.total_ops

    def test_dispatch_spt_chooses_shortest_ready_pair(self):
        """SPT first selects the ready pair with shortest processing time."""
        # Job0-Op0: M0(10), M1(5) has best pt=5.
        # Job1-Op0: M0(1), M1(20) has best pt=1.
        # SPT should first select Job1-Op0 on M0.
        jobs = [
            [[(0, 10), (1, 5)]],   # Job0
            [[(0, 1),  (1, 20)]],  # Job1
        ]
        instance = FJSPInstance.from_jobs_array(jobs, num_machines=2)
        result = dispatch_spt_solve(instance)

        first = result.records[0]
        assert (first.job_id, first.op_id, first.machine_id, first.processing_time) == (1, 0, 0, 1)

    def test_dispatch_spt_makespan_range(self):
        """Makespan stays in a reasonable range."""
        instance = create_toy_instance()
        result = dispatch_spt_solve(instance)
        assert 1 <= result.makespan <= 50


class TestDispatchEFT:

    def test_dispatch_eft_feasible(self):
        """Strict EFT must pass the feasibility checker."""
        instance = create_toy_instance()
        result = dispatch_eft_solve(instance)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"
        assert result.makespan > 0
        assert len(result.records) == instance.total_ops

    def test_dispatch_eft_chooses_earliest_finish(self):
        """EFT first selects the ready pair with earliest finish time."""
        # Job0-Op0: M0(10), M1(5) has earliest finish=5 on M1.
        # Job1-Op0: M0(1), M1(20) has earliest finish=1 on M0.
        # EFT should first select Job1-Op0 on M0.
        jobs = [
            [[(0, 10), (1, 5)]],   # Job0
            [[(0, 1),  (1, 20)]],  # Job1
        ]
        instance = FJSPInstance.from_jobs_array(jobs, num_machines=2)
        result = dispatch_eft_solve(instance)

        first = result.records[0]
        assert (first.job_id, first.op_id, first.machine_id, first.end) == (1, 0, 0, 1)

    def test_dispatch_eft_considers_machine_availability(self):
        """EFT considers machine availability."""
        # Two ready operations compete for M0.
        # Job1-Op0: M0(1), M1(3)
        # The first EFT choice is J1O0-M0 with finish=1.
        # Then J0O0 can only use M0, so it starts at 1 and finishes at 11.
        jobs = [
            [[(0, 10)]],           # Job0: only M0
            [[(0, 1), (1, 3)]],    # Job1: M0 or M1
        ]
        instance = FJSPInstance.from_jobs_array(jobs, num_machines=2)
        result = dispatch_eft_solve(instance)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"

    def test_dispatch_eft_makespan_range(self):
        """Makespan stays in a reasonable range."""
        instance = create_toy_instance()
        result = dispatch_eft_solve(instance)
        assert 1 <= result.makespan <= 50


class TestDispatchRandom:

    def test_dispatch_random_feasible(self):
        """Strict Random must pass the feasibility checker."""
        instance = create_toy_instance()
        result = dispatch_random_solve(instance, seed=42)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"
        assert result.makespan > 0
        assert len(result.records) == instance.total_ops

    def test_dispatch_random_deterministic(self):
        """Same seed produces the same selected machines."""
        instance = create_toy_instance()
        r1 = dispatch_random_solve(instance, seed=42)
        r2 = dispatch_random_solve(instance, seed=42)
        assert r1.makespan == r2.makespan
        # Compare selected machines in job-operation order.
        recs1 = sorted(r1.records, key=lambda r: (r.job_id, r.op_id))
        recs2 = sorted(r2.records, key=lambda r: (r.job_id, r.op_id))
        for a, b in zip(recs1, recs2):
            assert a.machine_id == b.machine_id

    def test_dispatch_random_different_seeds(self):
        """Different seeds can produce different makespans."""
        instance = create_toy_instance()
        results = set()
        for seed in range(30):
            r = dispatch_random_solve(instance, seed=seed)
            results.add(r.makespan)
        # At least two distinct makespans should appear across these seeds.
        assert len(results) >= 2

    def test_dispatch_random_makespan_range(self):
        """Makespan stays in a reasonable range."""
        instance = create_toy_instance()
        result = dispatch_random_solve(instance, seed=42)
        assert 1 <= result.makespan <= 50
