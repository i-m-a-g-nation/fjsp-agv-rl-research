from src.data.instance import create_toy_instance, FJSPInstance
from src.scheduling.feasibility import check_feasibility
from src.scheduling.encoding import ScheduleResult
from src.solvers.ortools_solver import ortools_solve, OrtoolsSolverError


class TestOrtoolsSolver:

    def test_solve_toy_instance_returns_valid_schedule(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=30.0)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"
        assert result.makespan > 0
        assert len(result.records) == instance.total_ops

    def test_solve_toy_instance_makespan_positive(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=30.0)
        assert result.makespan > 0

    def test_solve_toy_instance_all_ops_scheduled(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=30.0)
        scheduled = set((r.job_id, r.op_id) for r in result.records)
        expected = set()
        for j in range(instance.num_jobs):
            for o in range(instance.jobs[j].num_ops):
                expected.add((j, o))
        assert scheduled == expected

    def test_solve_toy_instance_no_overlap_on_machines(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=30.0)
        for m_id in range(instance.num_machines):
            ops = [r for r in result.records if r.machine_id == m_id]
            ops.sort(key=lambda r: r.start)
            for i in range(len(ops) - 1):
                assert ops[i].end <= ops[i + 1].start, \
                    f"Machine {m_id}: overlap between J{ops[i].job_id}O{ops[i].op_id} and J{ops[i+1].job_id}O{ops[i+1].op_id}"

    def test_solve_toy_instance_precedence_respected(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=30.0)
        for j_id in range(instance.num_jobs):
            job_ops = sorted(
                [r for r in result.records if r.job_id == j_id],
                key=lambda r: r.op_id,
            )
            for i in range(len(job_ops) - 1):
                assert job_ops[i].end <= job_ops[i + 1].start, \
                    f"Job {j_id}: precedence violation O{job_ops[i].op_id} -> O{job_ops[i+1].op_id}"

    def test_toy_instance_optimal_or_feasible(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=60.0)
        assert result.makespan >= 1
        assert result.makespan <= 50

    def test_solver_status_set(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=30.0)
        assert result.solver_status in ("OPTIMAL", "FEASIBLE"), \
            f"Expected OPTIMAL or FEASIBLE, got {result.solver_status}"

    def test_solver_status_feasible_after_check(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=30.0)
        feasible, _ = check_feasibility(result)
        assert feasible
        assert result.solver_status in ("OPTIMAL", "FEASIBLE")

    def test_end_equals_start_plus_pt(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=30.0)
        for rec in result.records:
            assert rec.end == rec.start + rec.processing_time, \
                f"Job {rec.job_id} Op {rec.op_id}: end={rec.end} != start={rec.start} + pt={rec.processing_time}"

    def test_single_job_single_op(self):
        jobs = [[[(0, 5)]]]
        instance = FJSPInstance.from_jobs_array(jobs)
        result = ortools_solve(instance, time_limit=10.0)
        feasible, _ = check_feasibility(result)
        assert feasible
        assert result.makespan == 5

    def test_single_job_multiple_ops(self):
        jobs = [[[(0, 2)], [(0, 3)], [(0, 4)]]]
        instance = FJSPInstance.from_jobs_array(jobs, num_machines=1)
        result = ortools_solve(instance, time_limit=30.0)
        feasible, _ = check_feasibility(result)
        assert feasible
        assert len(result.records) == 3
        assert result.makespan == 9

    def test_two_parallel_jobs(self):
        jobs = [
            [[(0, 5)], [(1, 3)]],
            [[(0, 3)], [(1, 5)]],
        ]
        instance = FJSPInstance.from_jobs_array(jobs, num_machines=2)
        result = ortools_solve(instance, time_limit=30.0)
        feasible, _ = check_feasibility(result)
        assert feasible

    def test_time_limit_short_returns_result(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=0.5)
        feasible, _ = check_feasibility(result)
        assert feasible
        assert result.makespan > 0


class TestSolverStatusDoesNotBreakHeuristics:

    def test_heuristic_result_has_no_solver_status_by_default(self):
        from src.data.instance import create_toy_instance as toy
        from src.scheduling.encoding import ScheduleResult
        result = ScheduleResult(instance=toy())
        assert result.solver_status is None

    def test_fifo_result_has_status_none(self):
        from src.data.instance import create_toy_instance as toy
        from src.solvers.heuristics import fifo_solve
        result = fifo_solve(toy())
        assert result.solver_status is None

    def test_spt_result_has_status_none(self):
        from src.data.instance import create_toy_instance as toy
        from src.solvers.heuristics import spt_solve
        result = spt_solve(toy())
        assert result.solver_status is None
