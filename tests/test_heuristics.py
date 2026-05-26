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
# 旧 baseline 测试（保留，不修改）
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
# 严格 dispatching rule 测试
# ============================================================

class TestDispatchFIFO:

    def test_dispatch_fifo_feasible(self):
        """严格 FIFO 必须通过 feasibility checker"""
        instance = create_toy_instance()
        result = dispatch_fifo_solve(instance)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"
        assert result.makespan > 0
        assert len(result.records) == instance.total_ops

    def test_dispatch_fifo_ready_order(self):
        """FIFO 选择 ready queue 中最早入队的工序"""
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
        """makespan 在合理范围内"""
        instance = create_toy_instance()
        result = dispatch_fifo_solve(instance)
        assert 1 <= result.makespan <= 50


class TestDispatchSPT:

    def test_dispatch_spt_feasible(self):
        """严格 SPT 必须通过 feasibility checker"""
        instance = create_toy_instance()
        result = dispatch_spt_solve(instance)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"
        assert result.makespan > 0
        assert len(result.records) == instance.total_ops

    def test_dispatch_spt_chooses_shortest_ready_pair(self):
        """SPT 第一步选择 ready operations 中 processing_time 最短的 pair"""
        # 构造实例：
        # Job0-Op0: M0(10), M1(5)  → 最短 pt=5
        # Job1-Op0: M0(1),  M1(20) → 最短 pt=1
        # SPT 第一步应选 Job1-Op0 on M0 (pt=1)
        jobs = [
            [[(0, 10), (1, 5)]],   # Job0
            [[(0, 1),  (1, 20)]],  # Job1
        ]
        instance = FJSPInstance.from_jobs_array(jobs, num_machines=2)
        result = dispatch_spt_solve(instance)

        first = result.records[0]
        assert (first.job_id, first.op_id, first.machine_id, first.processing_time) == (1, 0, 0, 1)

    def test_dispatch_spt_makespan_range(self):
        """makespan 在合理范围内"""
        instance = create_toy_instance()
        result = dispatch_spt_solve(instance)
        assert 1 <= result.makespan <= 50


class TestDispatchEFT:

    def test_dispatch_eft_feasible(self):
        """严格 EFT 必须通过 feasibility checker"""
        instance = create_toy_instance()
        result = dispatch_eft_solve(instance)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"
        assert result.makespan > 0
        assert len(result.records) == instance.total_ops

    def test_dispatch_eft_chooses_earliest_finish(self):
        """EFT 第一步选择 finish time 最早的 pair"""
        # 构造实例：
        # Job0-Op0: M0(10), M1(5)  → 最早 finish=5 (M1)
        # Job1-Op0: M0(1),  M1(20) → 最早 finish=1 (M0)
        # EFT 第一步应选 Job1-Op0 on M0 (finish=1)
        jobs = [
            [[(0, 10), (1, 5)]],   # Job0
            [[(0, 1),  (1, 20)]],  # Job1
        ]
        instance = FJSPInstance.from_jobs_array(jobs, num_machines=2)
        result = dispatch_eft_solve(instance)

        first = result.records[0]
        assert (first.job_id, first.op_id, first.machine_id, first.end) == (1, 0, 0, 1)

    def test_dispatch_eft_considers_machine_availability(self):
        """EFT 考虑机器空闲时间"""
        # 构造实例：两道工序争同一台机器
        # Job0-Op0: M0(10) → 占用 M0 到 t=10
        # Job1-Op0: M0(1), M1(3)
        # EFT 第一步：J0O0-M0 finish=10, J1O0-M0 finish=1, J1O0-M1 finish=3
        # 选 J1O0-M0 (finish=1)
        # 第二步：J0O0-M0 finish=1+10=11? 不对，J0O0 start=max(0,1)=1, finish=11
        # 但 J0O0 只有 M0 可选，所以 start=1, finish=11
        jobs = [
            [[(0, 10)]],           # Job0: 只能在 M0
            [[(0, 1), (1, 3)]],    # Job1: M0 或 M1
        ]
        instance = FJSPInstance.from_jobs_array(jobs, num_machines=2)
        result = dispatch_eft_solve(instance)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"

    def test_dispatch_eft_makespan_range(self):
        """makespan 在合理范围内"""
        instance = create_toy_instance()
        result = dispatch_eft_solve(instance)
        assert 1 <= result.makespan <= 50


class TestDispatchRandom:

    def test_dispatch_random_feasible(self):
        """严格 Random 必须通过 feasibility checker"""
        instance = create_toy_instance()
        result = dispatch_random_solve(instance, seed=42)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"
        assert result.makespan > 0
        assert len(result.records) == instance.total_ops

    def test_dispatch_random_deterministic(self):
        """同 seed 结果一致"""
        instance = create_toy_instance()
        r1 = dispatch_random_solve(instance, seed=42)
        r2 = dispatch_random_solve(instance, seed=42)
        assert r1.makespan == r2.makespan
        # 比较 assignment 顺序
        recs1 = sorted(r1.records, key=lambda r: (r.job_id, r.op_id))
        recs2 = sorted(r2.records, key=lambda r: (r.job_id, r.op_id))
        for a, b in zip(recs1, recs2):
            assert a.machine_id == b.machine_id

    def test_dispatch_random_different_seeds(self):
        """不同 seed 可能产生不同结果"""
        instance = create_toy_instance()
        results = set()
        for seed in range(30):
            r = dispatch_random_solve(instance, seed=seed)
            results.add(r.makespan)
        # 不同 seed 应该至少产生 2 种不同 makespan
        assert len(results) >= 2

    def test_dispatch_random_makespan_range(self):
        """makespan 在合理范围内"""
        instance = create_toy_instance()
        result = dispatch_random_solve(instance, seed=42)
        assert 1 <= result.makespan <= 50
